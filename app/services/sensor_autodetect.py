from __future__ import annotations

import asyncio
import inspect
import ipaddress
import re
import socket
from typing import Any

from aioesphomeapi import APIClient

from app.config import FDA2SensorSettings, Settings, upsert_runtime_fda2_sensor
from app.services.fda2_led import _is_rgb_light_entity


def _safe_name(value: str | None, fallback: str) -> str:
    text = (value or "").strip()
    return text or fallback


def _slugify(text: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    normalized = normalized.strip("_")
    return normalized or "sensor"


def _infer_sensor_family(device_name: str, entity_names: list[str]) -> str:
    text = f"{device_name} {' '.join(entity_names)}".lower()
    if "mr60fda2" in text or ("person" in text and "fall" in text):
        return "fall_fda2"
    if (
        "mr60bha2" in text
        or "breath" in text
        or "respiration" in text
        or "heart" in text
    ):
        return "heart_breath_bha2"
    return "unknown"


def _normalize_entity_name(entity: Any) -> str:
    return str(getattr(entity, "name", None) or getattr(entity, "object_id", "")).strip()


def _mode_names(entity: Any) -> list[str]:
    modes = getattr(entity, "supported_color_modes", []) or []
    names: list[str] = []
    for mode in modes:
        mode_name = getattr(mode, "name", None)
        if mode_name:
            names.append(str(mode_name))
        else:
            names.append(str(mode))
    return names


def _extract_fda2_keys(entities: list[Any]) -> dict[str, int | None]:
    person_key: int | None = None
    fall_key: int | None = None
    light_key: int | None = None
    rgb_light_key: int | None = None
    heart_rate_key: int | None = None
    respiration_rate_key: int | None = None
    distance_key: int | None = None
    target_number_key: int | None = None

    for entity in entities:
        key = getattr(entity, "key", None)
        if not isinstance(key, int):
            continue
        lower = _normalize_entity_name(entity).lower()
        class_name = type(entity).__name__.lower()
        unit = str(getattr(entity, "unit_of_measurement", "") or "").lower()
        device_class = str(getattr(entity, "device_class", "") or "").lower()

        if person_key is None and (
            "person" in lower
            or "human" in lower
            or "presence" in lower
            or "occupancy" in lower
        ):
            person_key = key

        if fall_key is None and ("fall" in lower or "safety" in device_class):
            fall_key = key

        if light_key is None and (
            "illuminance" in lower
            or "lux" in lower
            or (unit == "lx" and "sensorinfo" in class_name)
        ):
            light_key = key

        if rgb_light_key is None and _is_rgb_light_entity(entity):
            rgb_light_key = key

        if heart_rate_key is None and (
            "heart" in lower
            or "heartrate" in lower
            or "heart_rate" in lower
            or lower.endswith(" hr")
            or lower.startswith("hr ")
            or "_hr" in lower
            or unit in {"bpm"}
        ):
            heart_rate_key = key

        if respiration_rate_key is None and (
            "breath" in lower
            or "respiration" in lower
            or "respiratory" in lower
            or "resp_rate" in lower
            or "breathing_rate" in lower
            or lower.endswith(" rr")
            or lower.startswith("rr ")
            or "_rr" in lower
            or unit in {"brpm", "rpm"}
        ):
            respiration_rate_key = key

        if distance_key is None and (
            "distance" in lower
            or "range" in lower
            or "target distance" in lower
            or "detection object" in lower
            or device_class == "distance"
            or unit in {"cm", "m", "mm"}
        ):
            distance_key = key

        if target_number_key is None and (
            "target number" in lower
            or "target count" in lower
            or "targets" in lower
        ):
            target_number_key = key

    return {
        "person_key": person_key,
        "fall_key": fall_key,
        "light_key": light_key,
        "rgb_light_key": rgb_light_key,
        "heart_rate_key": heart_rate_key,
        "respiration_rate_key": respiration_rate_key,
        "distance_key": distance_key,
        "target_number_key": target_number_key,
    }


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
    payload = await _maybe_await(client.list_entities_services())
    if isinstance(payload, tuple):
        return list(payload[0])
    if hasattr(payload, "entities"):
        return list(payload.entities)
    return list(payload)


async def _probe_host(
    *,
    host: str,
    port: int,
    api_password: str | None,
    timeout_seconds: float,
) -> dict[str, Any] | None:
    client = APIClient(host, port, api_password)
    connected = False
    try:
        await asyncio.wait_for(_connect(client), timeout=timeout_seconds)
        connected = True
        device_info = await asyncio.wait_for(
            _maybe_await(client.device_info()),
            timeout=timeout_seconds,
        )
        entities = await asyncio.wait_for(
            _list_entities(client),
            timeout=timeout_seconds,
        )
    except Exception:
        return None
    finally:
        if connected:
            try:
                await _maybe_await(client.disconnect())
            except Exception:
                pass

    entity_names = [_normalize_entity_name(entity) for entity in entities]
    keys = _extract_fda2_keys(entities)
    sensor_family = _infer_sensor_family(
        _safe_name(getattr(device_info, "name", None), host),
        entity_names,
    )
    if isinstance(keys["person_key"], int) and isinstance(keys["fall_key"], int):
        sensor_family = "fall_fda2"
    elif isinstance(keys["heart_rate_key"], int) or isinstance(keys["respiration_rate_key"], int):
        sensor_family = "heart_breath_bha2"
    return {
        "host": host,
        "port": port,
        "device_name": _safe_name(getattr(device_info, "name", None), host),
        "mac_address": _safe_name(getattr(device_info, "mac_address", None), ""),
        "entity_names": entity_names,
        "sensor_family": sensor_family,
        "person_key": keys["person_key"],
        "fall_key": keys["fall_key"],
        "light_key": keys["light_key"],
        "rgb_light_key": keys["rgb_light_key"],
        "heart_rate_key": keys["heart_rate_key"],
        "respiration_rate_key": keys["respiration_rate_key"],
        "distance_key": keys["distance_key"],
        "target_number_key": keys["target_number_key"],
    }


def _host_candidates_from_anchor(anchor_host: str) -> list[str]:
    try:
        ip = ipaddress.ip_address(anchor_host)
        if not isinstance(ip, ipaddress.IPv4Address):
            return [anchor_host]
    except ValueError:
        return [anchor_host]

    subnet = ipaddress.ip_network(f"{ip}/24", strict=False)
    hosts = [str(host) for host in subnet.hosts()]
    anchor = str(ip)
    if anchor in hosts:
        hosts.remove(anchor)
        hosts.insert(0, anchor)
    return hosts


def _local_ipv4_anchors() -> list[str]:
    anchors: list[str] = []
    try:
        hostnames = {socket.gethostname(), socket.getfqdn(), "localhost"}
        for host in hostnames:
            for family, _, _, _, sockaddr in socket.getaddrinfo(host, None):
                if family != socket.AF_INET:
                    continue
                ip = sockaddr[0]
                if ip.startswith("127."):
                    continue
                anchors.append(ip)
    except Exception:
        return []
    return anchors


def _candidate_hosts(
    *,
    settings: Settings,
    hosts: list[str] | None,
    include_subnet_scan: bool,
) -> list[str]:
    if hosts:
        return sorted({host.strip() for host in hosts if host.strip()})

    anchors = [sensor.host for sensor in settings.configured_fda2_sensors()]
    anchors.extend(_local_ipv4_anchors())
    if not anchors:
        return []

    if not include_subnet_scan:
        return sorted({host for host in anchors if host})

    candidates: set[str] = set()
    for anchor in anchors:
        candidates.update(_host_candidates_from_anchor(anchor))
    return sorted(candidates)


def _sensor_id_for_device(
    *,
    sensor_family: str,
    device_name: str,
    host: str,
    existing_ids: set[str],
) -> str:
    prefix = "sensor"
    if sensor_family == "fall_fda2":
        prefix = "fda2"
    elif sensor_family == "heart_breath_bha2":
        prefix = "bha2"
    base = f"{prefix}_{_slugify(device_name)}"
    if base not in existing_ids:
        return base

    host_suffix = host.split(".")[-1] if "." in host else _slugify(host)
    with_host = f"{base}_{host_suffix}"
    if with_host not in existing_ids:
        return with_host

    index = 2
    while True:
        candidate = f"{with_host}_{index}"
        if candidate not in existing_ids:
            return candidate
        index += 1


def _default_room_for_host(host: str) -> str:
    suffix = host.split(".")[-1] if "." in host else "sensor"
    return f"auto_room_{suffix}"


async def discover_and_configure_sensors(
    *,
    settings: Settings,
    hosts: list[str] | None = None,
    include_subnet_scan: bool = True,
    timeout_seconds: float = 1.5,
    concurrency: int = 24,
    room_hint: str | None = None,
) -> dict[str, Any]:
    candidates = _candidate_hosts(
        settings=settings,
        hosts=hosts,
        include_subnet_scan=include_subnet_scan,
    )
    if not candidates:
        return {
            "scanned_hosts": 0,
            "discovered": [],
        }

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def guarded_probe(host: str) -> dict[str, Any] | None:
        async with semaphore:
            return await _probe_host(
                host=host,
                port=settings.fda2_port,
                api_password=settings.fda2_api_password,
                timeout_seconds=timeout_seconds,
            )

    results = await asyncio.gather(*(guarded_probe(host) for host in candidates))
    probed = [result for result in results if result is not None]

    configured_by_host = {sensor.host: sensor for sensor in settings.configured_fda2_sensors()}
    existing_ids = {sensor.sensor_id for sensor in settings.configured_fda2_sensors()}
    discovered: list[dict[str, Any]] = []

    for item in probed:
        host = str(item["host"])
        sensor_family = str(item["sensor_family"])
        device_name = str(item["device_name"])
        configured_for_live_ingestion = False
        added_to_runtime = False
        sensor_id = ""
        note = ""

        if host in configured_by_host:
            existing = configured_by_host[host]
            configured_for_live_ingestion = True
            sensor_id = existing.sensor_id
            note = "Already configured in live ingestion."
        elif sensor_family == "fall_fda2":
            person_key = item.get("person_key")
            fall_key = item.get("fall_key")
            if isinstance(person_key, int) and isinstance(fall_key, int):
                sensor_id = _sensor_id_for_device(
                    sensor_family=sensor_family,
                    device_name=device_name,
                    host=host,
                    existing_ids=existing_ids,
                )
                existing_ids.add(sensor_id)
                room = room_hint.strip() if room_hint and room_hint.strip() else _default_room_for_host(host)
                sensor = FDA2SensorSettings(
                    sensor_id=sensor_id,
                    room=room,
                    host=host,
                    port=settings.fda2_port,
                    api_password=settings.fda2_api_password or None,
                    person_key=person_key,
                    fall_key=fall_key,
                    light_key=item.get("light_key"),
                    rgb_light_key=item.get("rgb_light_key"),
                    enable_illuminance=settings.enable_illuminance,
                )
                added_to_runtime = upsert_runtime_fda2_sensor(sensor)
                configured_for_live_ingestion = True
                note = "Configured for live ingestion."
            else:
                note = "Could not infer person/fall entity keys."
        elif sensor_family == "heart_breath_bha2":
            heart_rate_key = item.get("heart_rate_key")
            respiration_rate_key = item.get("respiration_rate_key")
            if isinstance(heart_rate_key, int) or isinstance(respiration_rate_key, int):
                sensor_id = _sensor_id_for_device(
                    sensor_family=sensor_family,
                    device_name=device_name,
                    host=host,
                    existing_ids=existing_ids,
                )
                existing_ids.add(sensor_id)
                room = room_hint.strip() if room_hint and room_hint.strip() else _default_room_for_host(host)
                sensor = FDA2SensorSettings(
                    sensor_id=sensor_id,
                    room=room,
                    host=host,
                    port=settings.fda2_port,
                    api_password=settings.fda2_api_password or None,
                    sensor_family="heart_breath_bha2",
                    person_key=None,
                    fall_key=None,
                    light_key=None,
                    rgb_light_key=item.get("rgb_light_key"),
                    distance_key=item.get("distance_key") if isinstance(item.get("distance_key"), int) else None,
                    target_number_key=(
                        item.get("target_number_key")
                        if isinstance(item.get("target_number_key"), int)
                        else None
                    ),
                    heart_rate_key=heart_rate_key if isinstance(heart_rate_key, int) else None,
                    respiration_rate_key=(
                        respiration_rate_key if isinstance(respiration_rate_key, int) else None
                    ),
                    enable_illuminance=False,
                )
                added_to_runtime = upsert_runtime_fda2_sensor(sensor)
                configured_for_live_ingestion = True
                note = "Configured for live ingestion (heart/respiration timeline only)."
            else:
                sensor_id = _sensor_id_for_device(
                    sensor_family=sensor_family,
                    device_name=device_name,
                    host=host,
                    existing_ids=existing_ids,
                )
                existing_ids.add(sensor_id)
                note = "Detected heart/respiration device, but could not infer measurement keys."
        else:
            sensor_id = _sensor_id_for_device(
                sensor_family=sensor_family,
                device_name=device_name,
                host=host,
                existing_ids=existing_ids,
            )
            note = "Detected device type is not recognized for live ingestion."
            existing_ids.add(sensor_id)

        discovered.append(
            {
                "sensor_id": sensor_id,
                "sensor_family": sensor_family,
                "device_name": device_name,
                "host": host,
                "port": item["port"],
                "configured_for_live_ingestion": configured_for_live_ingestion,
                "added_to_runtime": added_to_runtime,
                "person_key": item.get("person_key"),
                "fall_key": item.get("fall_key"),
                "light_key": item.get("light_key"),
                "rgb_light_key": item.get("rgb_light_key"),
                "heart_rate_key": item.get("heart_rate_key"),
                "respiration_rate_key": item.get("respiration_rate_key"),
                "distance_key": item.get("distance_key"),
                "target_number_key": item.get("target_number_key"),
                "note": note,
            }
        )

    return {
        "scanned_hosts": len(candidates),
        "discovered": discovered,
    }
