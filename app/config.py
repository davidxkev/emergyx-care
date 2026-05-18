from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FDA2SensorSettings(BaseModel):
    sensor_id: str
    room: str
    host: str
    port: int = 6053
    api_password: str | None = None
    sensor_family: str = "fall_fda2"
    person_key: int | None = None
    fall_key: int | None = None
    light_key: int | None = None
    rgb_light_key: int | None = None
    heart_rate_key: int | None = None
    respiration_rate_key: int | None = None
    distance_key: int | None = None
    target_number_key: int | None = None
    enable_illuminance: bool = True


class Settings(BaseSettings):
    app_name: str = "Emergyx Care"
    app_env: str = "development"
    database_url: str = "sqlite:///data/emergyx_care.db"

    # Backward-compatible single-sensor settings. Prefer FDA2_SENSORS when
    # adding more than one MR60FDA2.
    fda2_sensor_ip: str = "192.168.1.100"
    fda2_sensor_id: str = "fda2_main"
    fda2_room: str = "demo_room"
    fda2_port: int = 6053
    fda2_api_password: str | None = None
    enable_legacy_fda2_sensor: bool = True
    fda2_person_key: int = 111111111
    fda2_fall_key: int = 222222222
    fda2_light_key: int = 333333333
    fda2_rgb_light_key: int | None = None
    enable_illuminance: bool = True
    fda2_sensors: list[FDA2SensorSettings] = Field(default_factory=list)
    illuminance_min_interval_seconds: int = 5
    sensor_reconnect_delay_seconds: int = 5

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    telegram_send_gemma_explanations: bool = False
    telegram_poll_timeout_seconds: int = 25
    telegram_poll_interval_seconds: int = 2
    mock_alert_channel: bool = False
    emergyx_demo_profile: str = "local"

    gemma_enabled: bool = False
    ollama_base_url: str = "http://localhost:11434"
    gemma_model: str = "gemma4:e2b"
    gemma_first_notifications: bool = False

    dashboard_refresh_seconds: int = 10
    public_dashboard_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def configured_fda2_sensors(self) -> list[FDA2SensorSettings]:
        base_sensors: list[FDA2SensorSettings]
        if self.fda2_sensors:
            base_sensors = list(self.fda2_sensors)
        elif self.enable_legacy_fda2_sensor:
            base_sensors = [
                FDA2SensorSettings(
                    sensor_id=self.fda2_sensor_id,
                    room=self.fda2_room,
                    host=self.fda2_sensor_ip,
                    port=self.fda2_port,
                    api_password=self.fda2_api_password or None,
                    person_key=self.fda2_person_key,
                    fall_key=self.fda2_fall_key,
                    light_key=self.fda2_light_key,
                    rgb_light_key=self.fda2_rgb_light_key,
                    enable_illuminance=self.enable_illuminance,
                )
            ]
        else:
            base_sensors = []

        by_sensor_id = {sensor.sensor_id: sensor for sensor in base_sensors}
        known_hosts = {sensor.host for sensor in base_sensors}
        for runtime_sensor in load_runtime_fda2_sensors():
            if runtime_sensor.sensor_id in by_sensor_id:
                continue
            if runtime_sensor.host in known_hosts:
                continue
            by_sensor_id[runtime_sensor.sensor_id] = runtime_sensor
        return sorted(by_sensor_id.values(), key=lambda sensor: sensor.sensor_id)


RUNTIME_FDA2_SENSORS_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "runtime_fda2_sensors.json"
)
RUNTIME_TELEGRAM_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "runtime_telegram_config.json"
)
RUNTIME_GEMMA_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "runtime_gemma_config.json"
)
RUNTIME_REPORT_SCHEDULE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "runtime_report_schedule.json"
)
RUNTIME_CARE_CONTEXT_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "runtime_care_context.json"
)


def load_runtime_fda2_sensors() -> list[FDA2SensorSettings]:
    try:
        if not RUNTIME_FDA2_SENSORS_PATH.exists():
            return []
        payload = json.loads(RUNTIME_FDA2_SENSORS_PATH.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return []
        sensors: list[FDA2SensorSettings] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                sensors.append(FDA2SensorSettings.model_validate(item))
            except Exception:
                continue
        return sensors
    except Exception:
        return []


def save_runtime_fda2_sensors(sensors: list[FDA2SensorSettings]) -> None:
    RUNTIME_FDA2_SENSORS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        json.loads(sensor.model_dump_json(exclude_none=True))
        for sensor in sorted(sensors, key=lambda item: item.sensor_id)
    ]
    RUNTIME_FDA2_SENSORS_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def upsert_runtime_fda2_sensor(sensor: FDA2SensorSettings) -> bool:
    runtime_sensors = load_runtime_fda2_sensors()
    updated = False
    for index, current in enumerate(runtime_sensors):
        if current.sensor_id == sensor.sensor_id or current.host == sensor.host:
            runtime_sensors[index] = sensor
            updated = True
            break
    if not updated:
        runtime_sensors.append(sensor)
    save_runtime_fda2_sensors(runtime_sensors)
    return not updated


def delete_runtime_fda2_sensor(sensor_id: str) -> bool:
    runtime_sensors = load_runtime_fda2_sensors()
    next_sensors = [sensor for sensor in runtime_sensors if sensor.sensor_id != sensor_id]
    if len(next_sensors) == len(runtime_sensors):
        return False
    save_runtime_fda2_sensors(next_sensors)
    return True


def runtime_fda2_sensors_as_dicts() -> list[dict[str, Any]]:
    return [
        json.loads(sensor.model_dump_json(exclude_none=True))
        for sensor in load_runtime_fda2_sensors()
    ]


def load_runtime_telegram_config() -> dict[str, Any]:
    try:
        if not RUNTIME_TELEGRAM_CONFIG_PATH.exists():
            return {}
        payload = json.loads(RUNTIME_TELEGRAM_CONFIG_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def save_runtime_telegram_config(config: dict[str, Any]) -> None:
    RUNTIME_TELEGRAM_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    allowed = {
        "telegram_bot_token",
        "telegram_chat_id",
        "telegram_send_gemma_explanations",
        "telegram_poll_timeout_seconds",
        "telegram_poll_interval_seconds",
    }
    clean = {key: value for key, value in config.items() if key in allowed}
    RUNTIME_TELEGRAM_CONFIG_PATH.write_text(
        json.dumps(clean, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    get_settings.cache_clear()


def load_runtime_gemma_config() -> dict[str, Any]:
    try:
        if not RUNTIME_GEMMA_CONFIG_PATH.exists():
            return {}
        payload = json.loads(RUNTIME_GEMMA_CONFIG_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def save_runtime_gemma_config(config: dict[str, Any]) -> None:
    RUNTIME_GEMMA_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    allowed = {"gemma_enabled", "gemma_model", "ollama_base_url", "gemma_first_notifications"}
    clean = {key: value for key, value in config.items() if key in allowed}
    RUNTIME_GEMMA_CONFIG_PATH.write_text(
        json.dumps(clean, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    get_settings.cache_clear()


def load_runtime_report_schedule() -> dict[str, Any]:
    try:
        if not RUNTIME_REPORT_SCHEDULE_PATH.exists():
            return {}
        payload = json.loads(RUNTIME_REPORT_SCHEDULE_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def save_runtime_report_schedule(config: dict[str, Any]) -> None:
    RUNTIME_REPORT_SCHEDULE_PATH.parent.mkdir(parents=True, exist_ok=True)
    allowed = {
        "daily_enabled",
        "daily_time",
        "daily_send_telegram",
        "weekly_enabled",
        "weekly_day",
        "weekly_time",
        "weekly_send_telegram",
        "pattern_enabled",
        "pattern_interval_minutes",
        "pattern_send_telegram",
        "last_daily_run_date",
        "last_weekly_run_key",
        "last_pattern_run_at",
        "last_pattern_summary",
        "last_error",
        "last_run_at",
    }
    clean = {key: value for key, value in config.items() if key in allowed}
    RUNTIME_REPORT_SCHEDULE_PATH.write_text(
        json.dumps(clean, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def load_runtime_care_context() -> dict[str, Any]:
    try:
        if not RUNTIME_CARE_CONTEXT_PATH.exists():
            return {}
        payload = json.loads(RUNTIME_CARE_CONTEXT_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def save_runtime_care_context(config: dict[str, Any]) -> None:
    RUNTIME_CARE_CONTEXT_PATH.parent.mkdir(parents=True, exist_ok=True)
    allowed = {
        "residents",
        "manual_rooms",
        "deleted_rooms",
        "sensor_assignments",
        "sensor_names",
        "sensor_contexts",
        "sensor_led_colors",
        "room_display_names",
        "updated_at",
    }
    clean = {key: value for key, value in config.items() if key in allowed}
    RUNTIME_CARE_CONTEXT_PATH.write_text(
        json.dumps(clean, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _settings_with_runtime_overrides(settings: Settings) -> Settings:
    runtime = {**load_runtime_telegram_config(), **load_runtime_gemma_config()}
    if not runtime:
        return settings
    update: dict[str, Any] = {}
    for key in (
        "telegram_bot_token",
        "telegram_chat_id",
        "telegram_send_gemma_explanations",
        "telegram_poll_timeout_seconds",
        "telegram_poll_interval_seconds",
        "gemma_enabled",
        "gemma_model",
        "ollama_base_url",
        "gemma_first_notifications",
    ):
        if key in runtime:
            update[key] = runtime[key]
    return settings.model_copy(update=update) if update else settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return _settings_with_runtime_overrides(Settings())
