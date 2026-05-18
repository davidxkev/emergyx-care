from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlmodel import Session

from app.config import FDA2SensorSettings, get_settings
from app.db import engine, init_db
from app.sensor_ingestion.fda2_client import FDA2SensorClient, SensorStateUpdate
from app.services.events import create_event
from app.services.utils import categorize_illuminance, normalize_value, parse_floatish


LOGGER = logging.getLogger(__name__)


class FDA2IngestionManager:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._last_values: dict[str, dict[int, str]] = {}
        self._last_illuminance_saved_at: dict[str, datetime] = {}
        self._last_illuminance_category: dict[str, str] = {}
        self._sensor_tasks: dict[str, asyncio.Task[None]] = {}
        self._sensor_fingerprints: dict[str, tuple[object, ...]] = {}
        self._idle_logged = False

    def _map_update(
        self,
        sensor: FDA2SensorSettings,
        update: SensorStateUpdate,
    ) -> tuple[str, object] | None:
        sensor_family = (sensor.sensor_family or "fall_fda2").strip().lower()

        if sensor_family == "heart_breath_bha2":
            if sensor.respiration_rate_key is not None and update.key == sensor.respiration_rate_key:
                return ("respiration_rate", update.value)
            if sensor.heart_rate_key is not None and update.key == sensor.heart_rate_key:
                return ("heart_rate", update.value)
            if sensor.person_key is not None and update.key == sensor.person_key:
                return ("person_present", bool(update.value))
            if (
                sensor.enable_illuminance
                and sensor.light_key is not None
                and update.key == sensor.light_key
            ):
                return ("illuminance", update.value)
            if sensor.distance_key is not None and update.key == sensor.distance_key:
                return ("target_distance", update.value)
            if sensor.target_number_key is not None and update.key == sensor.target_number_key:
                return ("target_number", update.value)
            return None

        if sensor.person_key is not None and update.key == sensor.person_key:
            return ("person_present", bool(update.value))
        if sensor.fall_key is not None and update.key == sensor.fall_key:
            return ("fall_detected", bool(update.value))
        if (
            sensor.enable_illuminance
            and sensor.light_key is not None
            and update.key == sensor.light_key
        ):
            return ("illuminance", update.value)
        return None

    def _should_skip(
        self,
        sensor: FDA2SensorSettings,
        update: SensorStateUpdate,
        event_type: str,
        value: object,
    ) -> bool:
        normalized = normalize_value(value)
        last_values = self._last_values.setdefault(sensor.sensor_id, {})

        if event_type == "illuminance":
            now = datetime.now().astimezone()
            current_category = categorize_illuminance(parse_floatish(value))
            category_changed = current_category != self._last_illuminance_category.get(sensor.sensor_id)
            window = timedelta(seconds=self.settings.illuminance_min_interval_seconds)
            time_window_passed = (
                sensor.sensor_id not in self._last_illuminance_saved_at
                or (now - self._last_illuminance_saved_at[sensor.sensor_id]) >= window
            )

            # Save when the category changes (immediate signal) OR throttle window passes.
            # This avoids spamming the DB with every tiny lux fluctuation.
            if not category_changed and not time_window_passed:
                return True

            self._last_illuminance_saved_at[sensor.sensor_id] = now
            self._last_illuminance_category[sensor.sensor_id] = current_category
            last_values[update.key] = normalized
            return False

        previous = last_values.get(update.key)
        if previous == normalized:
            return True

        last_values[update.key] = normalized
        return False

    async def _handle_update(
        self,
        sensor: FDA2SensorSettings,
        update: SensorStateUpdate,
    ) -> None:
        mapped = self._map_update(sensor, update)
        if mapped is None:
            return

        event_type, value = mapped
        if self._should_skip(sensor, update, event_type, value):
            return

        metadata: dict[str, object] = {
            "entity_key": update.key,
            "entity_name": update.name,
            "sensor_host": sensor.host,
            "sensor_family": sensor.sensor_family,
        }
        if event_type == "illuminance":
            lux = parse_floatish(value)
            metadata["lux"] = lux
            metadata["category"] = categorize_illuminance(lux)

        with Session(engine) as session:
            event = create_event(
                session,
                sensor_id=sensor.sensor_id,
                room=sensor.room,
                event_type=event_type,
                value=value,
                source="live_sensor",
                metadata_json=metadata,
                trigger_alerts=True,
            )

        LOGGER.info("[%s] %s=%s saved", event.timestamp, event.event_type, event.value)
        if event.event_type == "fall_detected" and event.value == "true":
            LOGGER.info("[alert] Immediate fall alert path executed")

    async def _run_sensor(self, sensor: FDA2SensorSettings) -> None:
        while True:
            try:
                LOGGER.info(
                    "Starting sensor ingestion for sensor_id=%s room=%s host=%s:%s",
                    sensor.sensor_id,
                    sensor.room,
                    sensor.host,
                    sensor.port,
                )
                client = FDA2SensorClient(
                    host=sensor.host,
                    port=sensor.port,
                    password=sensor.api_password,
                )
                await client.listen(lambda update: self._handle_update(sensor, update))
            except asyncio.CancelledError:
                LOGGER.info("Sensor ingestion cancelled for sensor_id=%s", sensor.sensor_id)
                raise
            except KeyboardInterrupt:
                LOGGER.info("Sensor ingestion interrupted by user")
                return
            except Exception as exc:
                LOGGER.warning(
                    "Sensor ingestion connection failed for sensor_id=%s host=%s: %s. Retrying in %s seconds.",
                    sensor.sensor_id,
                    sensor.host,
                    exc,
                    self.settings.sensor_reconnect_delay_seconds,
                )
                await asyncio.sleep(self.settings.sensor_reconnect_delay_seconds)

    @staticmethod
    def _fingerprint(sensor: FDA2SensorSettings) -> tuple[object, ...]:
        return (
            sensor.sensor_id,
            sensor.room,
            sensor.host,
            sensor.port,
            sensor.api_password,
            sensor.sensor_family,
            sensor.person_key,
            sensor.fall_key,
            sensor.light_key,
            sensor.rgb_light_key,
            sensor.heart_rate_key,
            sensor.respiration_rate_key,
            sensor.distance_key,
            sensor.target_number_key,
            sensor.enable_illuminance,
        )

    async def _cancel_sensor_task(self, sensor_id: str) -> None:
        task = self._sensor_tasks.pop(sensor_id, None)
        self._sensor_fingerprints.pop(sensor_id, None)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            LOGGER.warning("Sensor task %s ended with error during cancel: %s", sensor_id, exc)

    async def _reconcile_sensors(self) -> None:
        sensors = self.settings.configured_fda2_sensors()
        desired_by_id = {sensor.sensor_id: sensor for sensor in sensors}

        for sensor_id in list(self._sensor_tasks.keys()):
            if sensor_id not in desired_by_id:
                LOGGER.info("Removing sensor ingestion task for sensor_id=%s", sensor_id)
                await self._cancel_sensor_task(sensor_id)

        for sensor in sensors:
            sensor_id = sensor.sensor_id
            fingerprint = self._fingerprint(sensor)
            current_fingerprint = self._sensor_fingerprints.get(sensor_id)

            if sensor_id not in self._sensor_tasks:
                LOGGER.info("Adding sensor ingestion task for sensor_id=%s", sensor_id)
                task = asyncio.create_task(
                    self._run_sensor(sensor),
                    name=f"fda2-ingest-{sensor_id}",
                )
                self._sensor_tasks[sensor_id] = task
                self._sensor_fingerprints[sensor_id] = fingerprint
                continue

            if current_fingerprint != fingerprint:
                LOGGER.info("Reloading sensor ingestion task for sensor_id=%s", sensor_id)
                await self._cancel_sensor_task(sensor_id)
                task = asyncio.create_task(
                    self._run_sensor(sensor),
                    name=f"fda2-ingest-{sensor_id}",
                )
                self._sensor_tasks[sensor_id] = task
                self._sensor_fingerprints[sensor_id] = fingerprint

    async def run(self) -> None:
        init_db()
        LOGGER.info("Sensor ingestion manager started (dynamic sensor reconciliation enabled).")
        try:
            while True:
                await self._reconcile_sensors()
                if not self._sensor_tasks:
                    if not self._idle_logged:
                        LOGGER.warning("No sensors configured; ingestion manager is idle.")
                        self._idle_logged = True
                else:
                    self._idle_logged = False
                await asyncio.sleep(max(2, self.settings.sensor_reconnect_delay_seconds))
        except asyncio.CancelledError:
            LOGGER.info("Sensor ingestion manager cancelled")
            raise
        finally:
            for sensor_id in list(self._sensor_tasks.keys()):
                await self._cancel_sensor_task(sensor_id)
