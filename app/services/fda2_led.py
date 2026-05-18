from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any

from aioesphomeapi import APIClient
from aioesphomeapi.model import ColorMode

from app.config import FDA2SensorSettings, get_settings


class SensorLedError(RuntimeError):
    """Raised when a sensor RGB LED command cannot be completed."""


@dataclass(slots=True)
class LedCommandResult:
    sensor: FDA2SensorSettings
    rgb_light_key: int
    discovered: bool
    hex_color: str | None
    turn_off: bool


async def _maybe_await(result: Any) -> Any:
    if inspect.isawaitable(result):
        return await result
    return result


async def _connect(client: APIClient) -> None:
    try:
        await _maybe_await(client.connect(login=True))
    except TypeError:
        await _maybe_await(client.connect())


async def _list_entities(client: APIClient) -> list[Any]:
    entities_services = await _maybe_await(client.list_entities_services())
    if isinstance(entities_services, tuple):
        return list(entities_services[0])
    if hasattr(entities_services, "entities"):
        return list(entities_services.entities)
    return list(entities_services)


def _entity_name(entity: Any) -> str:
    return str(getattr(entity, "name", None) or getattr(entity, "object_id", ""))


def _is_rgb_light_entity(entity: Any) -> bool:
    name = _entity_name(entity).lower()
    class_name = type(entity).__name__.lower()
    supported_modes = getattr(entity, "supported_color_modes", []) or []
    supports_rgb = any("RGB" in (getattr(mode, "name", "") or str(mode)) for mode in supported_modes)
    return "light" in class_name and supports_rgb and ("rgb" in name or "mr60fda2" in name)


async def _resolve_rgb_light_key(
    sensor: FDA2SensorSettings,
    client: APIClient,
) -> tuple[int, bool]:
    if sensor.rgb_light_key is not None:
        return sensor.rgb_light_key, False

    for entity in await _list_entities(client):
        if _is_rgb_light_entity(entity):
            key = getattr(entity, "key", None)
            if isinstance(key, int):
                return key, True

    raise SensorLedError(
        f"No RGB light entity was found on {sensor.room}. Add rgb_light_key to the sensor config."
    )


def _hex_to_rgb_tuple(hex_color: str) -> tuple[float, float, float]:
    value = hex_color.lstrip("#")
    return (
        int(value[0:2], 16) / 255,
        int(value[2:4], 16) / 255,
        int(value[4:6], 16) / 255,
    )


def _find_sensor(sensor_id: str) -> FDA2SensorSettings:
    for sensor in get_settings().configured_fda2_sensors():
        if sensor.sensor_id == sensor_id:
            return sensor
    raise SensorLedError(f"No configured sensor found for sensor_id={sensor_id}.")


async def command_sensor_led(
    *,
    sensor_id: str,
    hex_color: str | None,
    brightness: float,
    flash_seconds: float | None = None,
    turn_off: bool = False,
) -> LedCommandResult:
    sensor = _find_sensor(sensor_id)
    client = APIClient(sensor.host, sensor.port, sensor.api_password)
    connected = False

    try:
        await _connect(client)
        connected = True
        rgb_light_key, discovered = await _resolve_rgb_light_key(sensor, client)

        if turn_off:
            client.light_command(rgb_light_key, state=False)
        else:
            if hex_color is None:
                raise SensorLedError("hex_color is required unless turn_off is true.")
            client.light_command(
                rgb_light_key,
                state=True,
                brightness=brightness,
                color_mode=ColorMode.RGB,
                color_brightness=1.0,
                rgb=_hex_to_rgb_tuple(hex_color),
                transition_length=0.15,
                flash_length=flash_seconds,
            )

        await asyncio.sleep(0.2)
        return LedCommandResult(
            sensor=sensor,
            rgb_light_key=rgb_light_key,
            discovered=discovered,
            hex_color=None if turn_off else hex_color,
            turn_off=turn_off,
        )
    finally:
        if connected:
            await _maybe_await(client.disconnect())
