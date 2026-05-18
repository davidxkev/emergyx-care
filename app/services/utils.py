from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Any


LIVE_SENSOR_SOURCE = "live_sensor"
DEMO_MODE_SOURCE_FILTER = "__demo_simulated__"
DEMO_SOURCES = {"simulated", "simulated_seed"}


def current_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def current_date() -> str:
    return datetime.now().astimezone().date().isoformat()


def normalize_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return value
    return json.dumps(json_safe_value(value), sort_keys=True, allow_nan=False, default=str)


def json_safe_value(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {
            str(key): json_safe_value(item)
            for key, item in value.items()
            if isinstance(key, (str, int, float, bool)) or key is None
        }
    if isinstance(value, (list, tuple, set)):
        return [json_safe_value(item) for item in value]
    return value


def normalize_metadata(metadata_json: Any) -> str | None:
    if metadata_json is None:
        return None
    if isinstance(metadata_json, str):
        return metadata_json
    return json.dumps(
        json_safe_value(metadata_json),
        sort_keys=True,
        allow_nan=False,
        default=str,
    )


def parse_boolish(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return value.strip().lower() in {"true", "1", "yes", "on", "detected"}


def parse_floatish(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def categorize_illuminance(lux: float | None) -> str:
    if lux is None:
        return "unknown"
    if lux < 10:
        return "dark"
    if lux < 50:
        return "dim"
    if lux < 200:
        return "low_indoor"
    if lux < 500:
        return "normal_indoor"
    return "bright"


def parse_iso_to_datetime(timestamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(timestamp)
    except (TypeError, ValueError):
        return None


def seconds_between(start_iso: str, end_iso: str) -> int | None:
    start = parse_iso_to_datetime(start_iso)
    end = parse_iso_to_datetime(end_iso)
    if start is None or end is None:
        return None
    return int((end - start).total_seconds())


def parse_mode(mode: str | None) -> tuple[str, str | None]:
    """Map a public 'mode' query param to a normalized name + source_filter.

    Returns (normalized_mode, source_filter) where:
    - live mode => only source="live_sensor"
    - demo mode => only simulated/demo-baseline sources
    """
    normalized = (mode or "demo").strip().lower()
    if normalized == "live":
        return ("live", LIVE_SENSOR_SOURCE)
    return ("demo", DEMO_MODE_SOURCE_FILTER)


def source_matches_filter(source: str | None, source_filter: str | None) -> bool:
    if source_filter is None:
        return True
    if source_filter == DEMO_MODE_SOURCE_FILTER:
        return source in DEMO_SOURCES
    return source == source_filter


def source_label(source: str | None) -> str:
    if source == LIVE_SENSOR_SOURCE:
        return "Live sensor"
    if source == "simulated":
        return "Demo run"
    if source == "simulated_seed":
        return "Demo baseline"
    if source == "manual":
        return "Manual"
    if not source:
        return "Unknown"
    return source.replace("_", " ").title()


def source_tone(source: str | None) -> str:
    if source == LIVE_SENSOR_SOURCE:
        return "live"
    if source in {"simulated", "simulated_seed"}:
        return "demo"
    if source == "manual":
        return "manual"
    return "neutral"


def severity_label(severity: str | None) -> str:
    normalized = (severity or "").strip().lower()
    if normalized == "high":
        return "Urgent"
    if normalized == "medium":
        return "Review"
    if normalized == "low":
        return "Normal"
    return "Unknown"


def severity_tone(severity: str | None) -> str:
    normalized = (severity or "").strip().lower()
    if normalized == "high":
        return "urgent"
    if normalized == "medium":
        return "warning"
    if normalized == "low":
        return "success"
    return "neutral"


def person_state_label(value: str | bool | None) -> str:
    return "Detected" if parse_boolish(value) else "Not detected"


def fall_state_label(value: str | bool | None) -> str:
    return "Likely fall detected" if parse_boolish(value) else "No active fall state"


def event_type_label(event_type: str | None) -> str:
    normalized = (event_type or "").strip().lower()
    mapping = {
        "fall_detected": "Likely fall detected",
        "person_present": "Person detected",
        "illuminance": "Light context",
    }
    if normalized in mapping:
        return mapping[normalized]
    if not normalized:
        return "Unknown event"
    return normalized.replace("_", " ").title()


def humanize_age_seconds(seconds: int | None) -> str:
    """Render an age in seconds as a short, human-friendly string."""
    if seconds is None:
        return "never"
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def staleness_category(seconds: int | None) -> str:
    """Bucketed staleness for the topnav 'Last live' indicator.

    fresh   — < 5 min   (data is flowing, pulsing green)
    recent  — < 1 h     (steady green)
    warn    — < 6 h     (yellow — long quiet period)
    stale   — ≥ 6 h     (red — likely a connection problem)
    none    — no live event has ever been recorded
    """
    if seconds is None:
        return "none"
    if seconds < 5 * 60:
        return "fresh"
    if seconds < 60 * 60:
        return "recent"
    if seconds < 6 * 60 * 60:
        return "warn"
    return "stale"


def age_seconds_now(timestamp: str | None) -> int | None:
    """Seconds between `timestamp` and now (timezone-aware), or None."""
    if not timestamp:
        return None
    dt = parse_iso_to_datetime(timestamp)
    if dt is None:
        return None
    now = datetime.now().astimezone()
    return int((now - dt).total_seconds())
