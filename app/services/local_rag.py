from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from sqlmodel import select
from sqlmodel import Session

from app.config import load_runtime_care_context
from app.models import DailyReport, Event
from app.services.events import (
    get_latest_event_by_type,
    get_latest_light_context,
    get_today_stats,
    list_alerts_for_date,
    list_events_for_date,
    list_recent_alerts,
    list_recent_events,
)
from app.services.incidents import get_incidents_for_date, get_latest_incident, get_today_incidents
from app.services.reports import list_reports_for_mode
from app.services.utils import (
    LIVE_SENSOR_SOURCE,
    age_seconds_now,
    current_date,
    humanize_age_seconds,
    parse_floatish,
)


VITAL_EVENT_TYPES = {"heart_rate", "respiration_rate"}
CURRENT_VITAL_MAX_AGE_SECONDS = 120


def build_scope_snapshot(
    session: Session,
    *,
    source_filter: str | None,
) -> dict[str, Any]:
    mode = "live" if source_filter == LIVE_SENSOR_SOURCE else "demo"
    today_stats = get_today_stats(session, source_filter=source_filter)
    latest_person = get_latest_event_by_type(session, "person_present", source_filter=source_filter)
    latest_fall = get_latest_event_by_type(session, "fall_detected", source_filter=source_filter)
    latest_light = _polish_light_context(get_latest_light_context(session, source_filter=source_filter))
    latest_incident = _polish_incident(get_latest_incident(session, source_filter=source_filter))
    vitals = _latest_vitals(session, source_filter=source_filter)
    care_context = _polish_care_context(load_runtime_care_context())

    return {
        "mode": mode,
        "date": current_date(),
        "care_context": care_context,
        "today_stats": {
            "total_events_today": today_stats.total_events_today,
            "fall_events_today": today_stats.fall_events_today,
        },
        "latest_person": _serialize_event(latest_person),
        "latest_fall": _serialize_event(latest_fall),
        "latest_light": latest_light,
        "latest_incident": latest_incident,
        "latest_vitals": vitals,
    }


def retrieve_local_context(
    session: Session,
    *,
    question: str,
    source_filter: str | None,
    limit: int = 6,
) -> dict[str, Any]:
    snapshot = build_scope_snapshot(session, source_filter=source_filter)
    mode = snapshot["mode"]
    question_tokens = _tokenize(question)
    candidates = _build_candidates(session, snapshot=snapshot, source_filter=source_filter, mode=mode)

    scored: list[tuple[float, int, dict[str, Any]]] = []
    for index, candidate in enumerate(candidates):
        score = _score_candidate(question_tokens, candidate)
        if score <= 0 and candidate["kind"] != "summary":
            continue
        scored.append((score, -index, candidate))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    evidence = [candidate for _, _, candidate in scored[:limit]]

    if not evidence:
        evidence = [candidate for candidate in candidates if candidate["kind"] == "summary"][:1]

    return {
        "snapshot": snapshot,
        "evidence": evidence,
        "tools_used": ["events", "alerts", "incidents", "reports", "light_context", "vitals", "care_context"],
    }


def _build_candidates(
    session: Session,
    *,
    snapshot: dict[str, Any],
    source_filter: str | None,
    mode: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    recent_events = list_recent_events(session, limit=20, source_filter=source_filter)
    recent_alerts = list_recent_alerts(session, limit=10, source_filter=source_filter)
    incidents = [
        _polish_incident(incident)
        for incident in get_today_incidents(session, source_filter=source_filter)
    ]
    reports = list_reports_for_mode(session, mode=mode, limit=4)
    week_summary = _weekly_summary(session, source_filter=source_filter)
    care_context = snapshot.get("care_context") or {}

    candidates.append(_summary_candidate(snapshot))
    candidates.append(_weekly_candidate(week_summary, mode=mode))
    candidates.extend(_care_context_candidates(care_context, mode=mode))
    vitals = snapshot.get("latest_vitals") or {}
    if vitals:
        candidates.append(_vitals_candidate(vitals, mode=mode))

    for incident in incidents[:4]:
        event = incident.get("event") or {}
        summary_lines = incident.get("summary") or []
        room = _format_room_name(incident.get("room"))
        candidates.append(
            {
                "kind": "incident",
                "label": f"Likely fall in {room}",
                "timestamp": event.get("timestamp"),
                "text": " ".join(summary_lines[:4]),
                "search_text": " ".join(summary_lines + [room, "likely fall incident"]),
                "related_event_id": event.get("id"),
                "metadata": {
                    "room": room,
                    "raw_room": incident.get("room"),
                    "source": incident.get("source"),
                    "duration_seconds": incident.get("duration_seconds"),
                },
            }
        )

    latest_incident = snapshot.get("latest_incident")
    if latest_incident and latest_incident not in incidents:
        event = latest_incident.get("event") or {}
        summary_lines = latest_incident.get("summary") or []
        room = _format_room_name(latest_incident.get("room"))
        candidates.append(
            {
                "kind": "incident",
                "label": f"Latest likely fall in {room}",
                "timestamp": event.get("timestamp"),
                "text": " ".join(summary_lines[:4]),
                "search_text": " ".join(summary_lines + ["latest likely fall incident"]),
                "related_event_id": event.get("id"),
                "metadata": {
                    "room": room,
                    "raw_room": latest_incident.get("room"),
                    "source": latest_incident.get("source"),
                    "duration_seconds": latest_incident.get("duration_seconds"),
                },
            }
        )

    for alert in recent_alerts[:5]:
        candidates.append(
            {
                "kind": "alert",
                "label": alert.alert_type.replace("_", " ").title(),
                "timestamp": alert.timestamp,
                "text": alert.message,
                "search_text": f"{alert.alert_type} {alert.message} {alert.severity} telegram alert caregiver",
                "related_event_id": alert.event_id,
                "metadata": {
                    "severity": alert.severity,
                    "sent_channel": alert.sent_channel,
                    "sent_success": alert.sent_success,
                    "source": LIVE_SENSOR_SOURCE if mode == "live" else "simulated",
                },
            }
        )

    light = snapshot.get("latest_light")
    if light:
        room = _format_room_name(light.get("room"))
        candidates.append(
            {
                "kind": "light",
                "label": "Latest light context",
                "timestamp": light.get("timestamp"),
                "text": (
                    f"{light.get('category', 'unknown')} at "
                    f"{light.get('lux', 'unknown')} lux in {room}"
                ),
                "search_text": (
                    f"light lux illuminance {light.get('category', '')} "
                    f"{light.get('lux', '')} {room}"
                ),
                "related_event_id": None,
                "metadata": {**light, "room": room, "raw_room": light.get("room")},
            }
        )

    for event in recent_events[:18]:
        if event.event_type == "illuminance":
            continue
        if event.event_type in VITAL_EVENT_TYPES:
            # Vitals are represented by the dedicated candidate above so transient
            # zero/settling readings do not get mistaken for the current value.
            continue
        candidates.append(
            {
                "kind": "event",
                "label": f"{event.event_type.replace('_', ' ').title()}",
                "timestamp": event.timestamp,
                "text": f"{event.event_type}={event.value} in {_format_room_name(event.room)}",
                "search_text": (
                    f"{event.event_type} {event.value} {_format_room_name(event.room)} "
                    f"{event.sensor_id} presence person fall room current latest"
                ),
                "related_event_id": event.id,
                "metadata": {
                    "sensor_id": event.sensor_id,
                    "room": _format_room_name(event.room),
                    "raw_room": event.room,
                    "source": event.source,
                },
            }
        )

    for report in reports:
        candidates.append(_report_candidate(report, mode=mode))

    return candidates


def _summary_candidate(snapshot: dict[str, Any]) -> dict[str, Any]:
    light = snapshot.get("latest_light") or {}
    person = snapshot.get("latest_person") or {}
    fall = snapshot.get("latest_fall") or {}
    stats = snapshot.get("today_stats") or {}
    text = (
        f"{stats.get('total_events_today', 0)} events today, "
        f"{stats.get('fall_events_today', 0)} likely-fall events. "
        f"Latest person state: {person.get('value', 'unknown')}. "
        f"Latest fall state: {fall.get('value', 'unknown')}. "
        f"Light: {light.get('category', 'unknown')}."
    )
    return {
        "kind": "summary",
        "label": "Today summary",
        "timestamp": snapshot.get("date"),
        "text": text,
        "search_text": (
            f"today summary overview totals {text} "
            f"{snapshot.get('mode', 'demo')} caregiver status"
        ),
        "related_event_id": None,
        "metadata": {
            "mode": snapshot.get("mode"),
            "source": LIVE_SENSOR_SOURCE if snapshot.get("mode") == "live" else "simulated",
        },
    }


def _latest_vitals(session: Session, *, source_filter: str | None) -> dict[str, Any]:
    return {
        "heart_rate": _latest_vital_reading(
            session,
            event_type="heart_rate",
            source_filter=source_filter,
            min_value=25,
            max_value=220,
        ),
        "respiration_rate": _latest_vital_reading(
            session,
            event_type="respiration_rate",
            source_filter=source_filter,
            min_value=6,
            max_value=60,
        ),
    }


def _latest_vital_reading(
    session: Session,
    *,
    event_type: str,
    source_filter: str | None,
    min_value: float,
    max_value: float,
) -> dict[str, Any]:
    statement = select(Event).where(Event.event_type == event_type)
    if source_filter is not None:
        statement = statement.where(Event.source == source_filter)
    statement = statement.order_by(Event.id.desc()).limit(500)
    rows = list(session.exec(statement))
    latest_raw = rows[0] if rows else None
    latest_raw_value = parse_floatish(latest_raw.value) if latest_raw else None
    latest_valid: Event | None = None
    latest_valid_value: float | None = None
    invalid_recent_count = 0
    for row in rows:
        value = parse_floatish(row.value)
        if value is None:
            invalid_recent_count += 1
            continue
        if min_value <= value <= max_value:
            latest_valid = row
            latest_valid_value = value
            break
        invalid_recent_count += 1

    latest_valid_payload = _serialize_vital_event(latest_valid, latest_valid_value)
    latest_raw_payload = _serialize_vital_event(latest_raw, latest_raw_value)
    current_valid_payload = (
        latest_valid_payload
        if latest_valid_payload
        and isinstance(latest_valid_payload.get("age_seconds"), int)
        and latest_valid_payload["age_seconds"] <= CURRENT_VITAL_MAX_AGE_SECONDS
        else None
    )

    return {
        "event_type": event_type,
        "label": "heart rate" if event_type == "heart_rate" else "breathing rate",
        "unit": "bpm" if event_type == "heart_rate" else "breaths/min",
        "latest_raw": latest_raw_payload,
        "latest_valid": latest_valid_payload,
        "current_valid": current_valid_payload,
        "invalid_recent_count": invalid_recent_count,
        "status": (
            "current"
            if current_valid_payload
            else "stale" if latest_valid_payload else "unstable_or_unavailable"
        ),
    }


def _serialize_vital_event(event: Event | None, value: float | None) -> dict[str, Any] | None:
    if event is None:
        return None
    age_seconds = age_seconds_now(event.timestamp)
    return {
        "timestamp": event.timestamp,
        "sensor_id": event.sensor_id,
        "room": _format_room_name(event.room),
        "raw_room": event.room,
        "source": event.source,
        "value": value,
        "age_seconds": age_seconds,
        "age_human": humanize_age_seconds(age_seconds),
    }


def _polish_light_context(light: dict[str, Any] | None) -> dict[str, Any] | None:
    if not light:
        return None
    raw_room = light.get("room")
    return {**light, "room": _format_room_name(raw_room), "raw_room": raw_room}


def _polish_incident(incident: dict[str, Any] | None) -> dict[str, Any] | None:
    if not incident:
        return None
    raw_room = incident.get("room")
    room = _format_room_name(raw_room)
    polished = {**incident, "room": room, "raw_room": raw_room}
    for key in ("event", "person_before", "before_person", "person_after", "after_person", "fall_clear_after", "after_fall_clear"):
        value = polished.get(key)
        if isinstance(value, dict) and value.get("room"):
            polished[key] = {**value, "room": _format_room_name(value.get("room")), "raw_room": value.get("room")}
    light = polished.get("light_context")
    if isinstance(light, dict):
        polished["light_context"] = _polish_light_context(light)
    summaries = []
    for line in polished.get("summary") or []:
        summaries.append(_replace_auto_room_labels(str(line)))
    polished["summary"] = summaries
    return polished


def _replace_auto_room_labels(text: str) -> str:
    return re.sub(
        r"\bauto_room_(\d+)\b",
        lambda match: f"Sensor Area {match.group(1)}",
        text,
    )


def _vitals_candidate(vitals: dict[str, Any], *, mode: str) -> dict[str, Any]:
    heart_info = vitals.get("heart_rate") or {}
    breathing_info = vitals.get("respiration_rate") or {}
    heart = heart_info.get("current_valid")
    breathing = breathing_info.get("current_valid")
    stale_heart = heart_info.get("latest_valid") if not heart else None
    stale_breathing = breathing_info.get("latest_valid") if not breathing else None
    pieces: list[str] = []
    if heart:
        pieces.append(
            f"Heart rate {heart.get('value')} bpm at {heart.get('timestamp')} in {heart.get('room')}"
        )
    elif stale_heart:
        pieces.append(
            f"Heart rate has no current fresh reading; latest valid reading was {stale_heart.get('value')} bpm "
            f"at {stale_heart.get('timestamp')} in {stale_heart.get('room')} ({stale_heart.get('age_human')})"
        )
    else:
        pieces.append("Heart rate is not currently available as a valid live reading")
    if breathing:
        pieces.append(
            f"Breathing rate {breathing.get('value')} breaths/min at {breathing.get('timestamp')} in {breathing.get('room')}"
        )
    elif stale_breathing:
        pieces.append(
            f"Breathing rate has no current fresh reading; latest valid reading was {stale_breathing.get('value')} breaths/min "
            f"at {stale_breathing.get('timestamp')} in {stale_breathing.get('room')} ({stale_breathing.get('age_human')})"
        )
    else:
        pieces.append("Breathing rate is not currently available as a stable live reading")
    latest_ts = None
    for item in (heart, breathing, stale_heart, stale_breathing):
        if item and (latest_ts is None or str(item.get("timestamp")) > latest_ts):
            latest_ts = str(item.get("timestamp"))
    text = ". ".join(pieces) + ". Zero or out-of-range vital readings are treated as sensor settling/no-target values, not as caregiver-facing vital signs."
    return {
        "kind": "vitals",
        "label": "Current vital signs",
        "timestamp": latest_ts or current_date(),
        "text": text,
        "search_text": (
            "current latest now heart rate breathing rate respiration rate vitals bpm "
            f"breaths respiration pulse {text}"
        ),
        "related_event_id": None,
        "metadata": {
            "source": LIVE_SENSOR_SOURCE if mode == "live" else "simulated",
            "vitals": vitals,
        },
    }


def _polish_care_context(raw: dict[str, Any]) -> dict[str, Any]:
    room_display_names = raw.get("room_display_names") if isinstance(raw.get("room_display_names"), dict) else {}
    sensor_assignments = raw.get("sensor_assignments") if isinstance(raw.get("sensor_assignments"), dict) else {}
    sensor_names = raw.get("sensor_names") if isinstance(raw.get("sensor_names"), dict) else {}
    sensor_contexts = raw.get("sensor_contexts") if isinstance(raw.get("sensor_contexts"), dict) else {}
    residents = raw.get("residents") if isinstance(raw.get("residents"), list) else []

    def room_label(room: str | None) -> str:
        if not room:
            return "Unassigned room"
        display = room_display_names.get(room)
        if isinstance(display, str) and display.strip():
            return display.strip()
        return _format_room_name(room)

    clean_residents: list[dict[str, Any]] = []
    for resident in residents:
        if not isinstance(resident, dict):
            continue
        name = str(resident.get("name") or "").strip()
        if not name:
            continue
        rooms = [room for room in resident.get("rooms") or [] if isinstance(room, str) and room.strip()]
        clean_residents.append(
            {
                "id": str(resident.get("id") or "").strip(),
                "name": name,
                "rooms": rooms,
                "room_labels": [room_label(room) for room in rooms],
                "context": str(resident.get("context") or "").strip(),
                "updated_at": str(resident.get("updated_at") or "").strip(),
            }
        )

    clean_sensors: list[dict[str, Any]] = []
    for sensor_id, room in sensor_assignments.items():
        if not isinstance(sensor_id, str) or not isinstance(room, str):
            continue
        clean_sensors.append(
            {
                "sensor_id": sensor_id,
                "name": str(sensor_names.get(sensor_id) or "").strip(),
                "room": room,
                "room_label": room_label(room),
                "context": str(sensor_contexts.get(sensor_id) or "").strip(),
            }
        )

    return {
        "residents": clean_residents,
        "sensors": sorted(clean_sensors, key=lambda item: (item["room_label"], item["sensor_id"])),
        "room_display_names": room_display_names,
    }


def _care_context_candidates(care_context: dict[str, Any], *, mode: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for resident in care_context.get("residents") or []:
        rooms = resident.get("room_labels") or []
        context = resident.get("context") or ""
        name = resident.get("name") or "Resident"
        text = (
            f"{name} is assigned to {', '.join(rooms) if rooms else 'no monitored rooms yet'}."
            + (f" Caregiver context: {context}" if context else "")
        )
        candidates.append(
            {
                "kind": "care_context",
                "label": f"Resident profile: {name}",
                "timestamp": resident.get("updated_at") or current_date(),
                "text": text,
                "search_text": f"resident profile person caregiver context rooms {' '.join(rooms)} {name} {context}",
                "related_event_id": None,
                "metadata": {
                    "source": LIVE_SENSOR_SOURCE if mode == "live" else "simulated",
                    "resident_id": resident.get("id"),
                    "rooms": resident.get("rooms") or [],
                    "room_labels": rooms,
                },
            }
        )
    for sensor in care_context.get("sensors") or []:
        text = (
            f"{sensor.get('name') or sensor.get('sensor_id')} is assigned to {sensor.get('room_label')}."
            + (f" Sensor context: {sensor.get('context')}" if sensor.get("context") else "")
        )
        candidates.append(
            {
                "kind": "care_context",
                "label": f"Sensor context: {sensor.get('name') or sensor.get('sensor_id')}",
                "timestamp": current_date(),
                "text": text,
                "search_text": (
                    f"sensor context assignment room configured room {sensor.get('sensor_id')} "
                    f"{sensor.get('name')} {sensor.get('room_label')} {sensor.get('context')}"
                ),
                "related_event_id": None,
                "metadata": {
                    "source": LIVE_SENSOR_SOURCE if mode == "live" else "simulated",
                    "sensor_id": sensor.get("sensor_id"),
                    "room": sensor.get("room_label"),
                    "raw_room": sensor.get("room"),
                },
            }
        )
    return candidates


def _report_candidate(report: DailyReport, *, mode: str) -> dict[str, Any]:
    report_text = report.report_text or ""
    preview = " ".join(report_text.split())[:220]
    return {
        "kind": "report",
        "label": f"Daily report for {report.date}",
        "timestamp": report.created_at,
        "text": preview,
        "search_text": f"daily report digest summary overnight caregiver {preview}",
        "related_event_id": None,
        "metadata": {
            "report_id": report.id,
            "date": report.date,
            "source": LIVE_SENSOR_SOURCE if mode == "live" else "simulated",
        },
    }


def _weekly_summary(session: Session, *, source_filter: str | None) -> dict[str, Any]:
    end_date = date.fromisoformat(current_date())
    start_date = end_date - timedelta(days=6)
    total_events = 0
    total_alerts = 0
    total_incidents = 0

    for offset in range(7):
        day = (start_date + timedelta(days=offset)).isoformat()
        total_events += len(list_events_for_date(session, day, source_filter=source_filter))
        total_alerts += len(list_alerts_for_date(session, day, source_filter=source_filter))
        total_incidents += len(get_incidents_for_date(session, day, source_filter=source_filter))

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "events": total_events,
        "alerts": total_alerts,
        "incidents": total_incidents,
    }


def _weekly_candidate(summary: dict[str, Any], *, mode: str) -> dict[str, Any]:
    text = (
        f"Last 7 days: {summary['incidents']} likely-fall incidents, "
        f"{summary['alerts']} alerts, and {summary['events']} local timeline events "
        f"between {summary['start_date']} and {summary['end_date']}."
    )
    return {
        "kind": "summary",
        "label": "Weekly safety summary",
        "timestamp": summary["end_date"],
        "text": text,
        "search_text": f"week weekly last 7 days likely falls alerts events {text}",
        "related_event_id": None,
        "metadata": {
            "source": LIVE_SENSOR_SOURCE if mode == "live" else "simulated",
            "range_start": summary["start_date"],
            "range_end": summary["end_date"],
        },
    }


def _score_candidate(question_tokens: set[str], candidate: dict[str, Any]) -> float:
    score = 0.2
    search_tokens = _tokenize(candidate.get("search_text", ""))
    overlap = len(question_tokens & search_tokens)
    score += overlap * 1.8

    kind = candidate.get("kind")
    if kind == "summary":
        score += 1.2
    if {"fall", "incident", "alert", "check"} & question_tokens and kind in {"incident", "alert"}:
        score += 4.5
    if {"light", "lux", "dark", "bright", "illuminance"} & question_tokens and kind == "light":
        score += 6
    if {"heart", "rate", "breathing", "breath", "respiration", "respiratory", "vitals", "pulse"} & question_tokens and kind == "vitals":
        score += 9
    if {"resident", "residents", "david", "person", "profile", "context", "rooms", "room"} & question_tokens and kind == "care_context":
        score += 8
    if {"person", "presence", "present", "room"} & question_tokens and kind == "event":
        score += 3
    if {"report", "digest", "summary", "overnight", "today"} & question_tokens and kind in {"summary", "report", "incident"}:
        score += 3.2
    if {"latest", "recent", "current", "now"} & question_tokens:
        score += 1.5
        if kind in {"event", "light", "incident"}:
            score += 1.5

    timestamp = candidate.get("timestamp") or ""
    if isinstance(timestamp, str):
        if timestamp.startswith(current_date()):
            score += 1.2
        if "T" in timestamp:
            score += 0.2
    return score


def _serialize_event(event: Any) -> dict[str, Any] | None:
    if event is None:
        return None
    return {
        "id": event.id,
        "timestamp": event.timestamp,
        "event_type": event.event_type,
        "value": event.value,
        "sensor_id": event.sensor_id,
        "room": event.room,
        "room_label": _format_room_name(event.room),
        "source": event.source,
    }


def _format_room_name(room: str | None) -> str:
    if not room:
        return "Unassigned room"
    match = re.fullmatch(r"auto_room_(\d+)", room)
    if match:
        return f"Sensor Area {match.group(1)}"
    if room == "demo_room":
        return "Demo Room"
    return " ".join(part.capitalize() for part in re.split(r"[_\s-]+", room) if part)


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_]+", text.lower()) if len(token) > 1}
