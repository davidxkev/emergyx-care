"""Incident reconstruction service.

Builds a structured before/event/after timeline for a fall_detected event using
only locally stored data. This is part of the structured local context that Gemma
can use when explaining incidents, generating reports, scanning patterns, or
making Gemma-first notification decisions when that setting is enabled.

A `source_filter` of "live_sensor" restricts every helper query to real sensor
data so the dashboard's Live mode is never polluted by simulated rows.
"""
from __future__ import annotations

from typing import Any

from sqlmodel import Session

from app.models import Event
from app.services.events import (
    get_alert_for_event,
    get_event_after,
    get_event_before,
    get_latest_illuminance_event,
    get_latest_true_fall_event,
)
from app.services.utils import (
    categorize_illuminance,
    parse_floatish,
    parse_iso_to_datetime,
    seconds_between,
)


def _event_to_dict(event: Event | None) -> dict[str, Any] | None:
    if event is None:
        return None
    return {
        "id": event.id,
        "timestamp": event.timestamp,
        "sensor_id": event.sensor_id,
        "room": event.room,
        "event_type": event.event_type,
        "value": event.value,
        "source": event.source,
    }


def _light_context_for(
    session: Session,
    around_timestamp: str,
    source_filter: str | None = None,
    sensor_id_filter: str | None = None,
) -> dict[str, Any] | None:
    latest = get_latest_illuminance_event(
        session,
        source_filter,
        sensor_id_filter=sensor_id_filter,
    )
    if latest is None:
        return None

    light_event = latest
    candidate = get_event_before(
        session,
        timestamp=around_timestamp,
        event_type="illuminance",
        source_filter=source_filter,
        sensor_id_filter=sensor_id_filter,
    )
    if candidate is not None:
        light_event = candidate

    lux = parse_floatish(light_event.value)
    return {
        "lux": lux,
        "category": categorize_illuminance(lux),
        "timestamp": light_event.timestamp,
        "room": light_event.room,
        "source": light_event.source,
        "sensor_id": light_event.sensor_id,
    }


def get_incident_context(
    session: Session,
    event_id: int,
    source_filter: str | None = None,
) -> dict[str, Any] | None:
    """Reconstruct the local timeline around a fall_detected event.

    `source_filter` filters the *surrounding* before/after/light queries; the
    incident event itself is always returned (you might want to inspect a
    simulated event even while in Live mode for debugging). The dashboard never
    surfaces an incident whose own source does not match the filter, so this
    is safe in practice.
    """
    event = session.get(Event, event_id)
    if event is None:
        return None

    is_fall = event.event_type == "fall_detected"
    is_fall_true = is_fall and event.value == "true"

    person_before = get_event_before(
        session,
        timestamp=event.timestamp,
        event_type="person_present",
        source_filter=source_filter,
        sensor_id_filter=event.sensor_id,
    )
    fall_clear_after = (
        get_event_after(
            session,
            timestamp=event.timestamp,
            event_type="fall_detected",
            value_filter="false",
            source_filter=source_filter,
            sensor_id_filter=event.sensor_id,
        )
        if is_fall_true
        else None
    )
    person_after = get_event_after(
        session,
        timestamp=event.timestamp,
        event_type="person_present",
        source_filter=source_filter,
        sensor_id_filter=event.sensor_id,
    )
    light_context = _light_context_for(
        session,
        event.timestamp,
        source_filter=source_filter,
        sensor_id_filter=event.sensor_id,
    )
    alert = get_alert_for_event(session, event.id) if event.id is not None else None

    duration_seconds = None
    if fall_clear_after is not None:
        duration_seconds = seconds_between(event.timestamp, fall_clear_after.timestamp)

    summary = _human_summary(
        event=event,
        person_before=person_before,
        fall_clear_after=fall_clear_after,
        person_after=person_after,
        light_context=light_context,
        alert=alert,
        duration_seconds=duration_seconds,
    )

    return {
        "event": _event_to_dict(event),
        "is_fall_true": is_fall_true,
        "person_before": _event_to_dict(person_before),
        "fall_clear_after": _event_to_dict(fall_clear_after),
        "person_after": _event_to_dict(person_after),
        "light_context": light_context,
        "alert": {
            "id": alert.id,
            "timestamp": alert.timestamp,
            "severity": alert.severity,
            "alert_type": alert.alert_type,
            "sent_channel": alert.sent_channel,
            "sent_success": alert.sent_success,
        }
        if alert is not None
        else None,
        "duration_seconds": duration_seconds,
        "source": event.source,
        "sensor_id": event.sensor_id,
        "room": event.room,
        "summary": summary,
        "filter": {"source_filter": source_filter},
    }


def _human_summary(
    *,
    event: Event,
    person_before: Event | None,
    fall_clear_after: Event | None,
    person_after: Event | None,
    light_context: dict[str, Any] | None,
    alert: Any | None,
    duration_seconds: int | None,
) -> list[str]:
    """A neutral, factual bullet list — no diagnosis, just structured facts."""
    lines: list[str] = []
    when = event.timestamp.split("T")[-1][:5] if "T" in event.timestamp else event.timestamp
    headline = (
        f"Likely fall in {event.room} at {when}"
        if event.event_type == "fall_detected" and event.value == "true"
        else f"{event.event_type}={event.value} in {event.room} at {when}"
    )
    lines.append(headline)

    if person_before is not None:
        verb = "Person detected" if person_before.value == "true" else "Person not detected"
        lines.append(f"Before: {verb} at {person_before.timestamp}")
    else:
        lines.append("Before: no prior person_present event recorded")

    if duration_seconds is not None and fall_clear_after is not None:
        lines.append(
            f"After: fall_detected cleared at {fall_clear_after.timestamp}"
            f" — fall state lasted ~{duration_seconds} seconds"
        )
    elif fall_clear_after is None and event.value == "true":
        lines.append("After: fall_detected has not yet cleared in the local timeline")

    if person_after is not None:
        verb = "person detected" if person_after.value == "true" else "person not detected"
        lines.append(f"Person after: {verb} at {person_after.timestamp}")

    if light_context is not None:
        lux = light_context["lux"]
        cat = light_context["category"]
        lux_str = f"{lux:.1f} lux" if isinstance(lux, (int, float)) else "n/a"
        lines.append(f"Light context: {cat}, {lux_str}")
    else:
        lines.append("Light context: not available")

    if alert is not None:
        lines.append(
            f"Alert: {alert.alert_type} via {alert.sent_channel} (sent_success={alert.sent_success})"
        )
    elif event.event_type == "fall_detected" and event.value == "true":
        lines.append("Alert: no alert record linked yet")

    lines.append(f"Source: {event.source}")
    return lines


def get_latest_incident(
    session: Session,
    source_filter: str | None = None,
) -> dict[str, Any] | None:
    fall = get_latest_true_fall_event(session, source_filter)
    if fall is None or fall.id is None:
        return None
    return get_incident_context(session, fall.id, source_filter=source_filter)


def get_today_incidents(
    session: Session,
    source_filter: str | None = None,
) -> list[dict[str, Any]]:
    from app.services.events import list_today_events

    incidents: list[dict[str, Any]] = []
    for ev in list_today_events(session, source_filter=source_filter):
        if ev.event_type == "fall_detected" and ev.value == "true" and ev.id is not None:
            ctx = get_incident_context(session, ev.id, source_filter=source_filter)
            if ctx is not None:
                incidents.append(ctx)
    return incidents


def get_incidents_for_date(
    session: Session,
    date_str: str,
    source_filter: str | None = None,
) -> list[dict[str, Any]]:
    from app.services.events import list_events_for_date

    incidents: list[dict[str, Any]] = []
    for ev in list_events_for_date(session, date_str, source_filter=source_filter):
        if ev.event_type == "fall_detected" and ev.value == "true" and ev.id is not None:
            ctx = get_incident_context(session, ev.id, source_filter=source_filter)
            if ctx is not None:
                incidents.append(ctx)
    return incidents


__all__ = [
    "get_incident_context",
    "get_incidents_for_date",
    "get_latest_incident",
    "get_today_incidents",
]


_ = parse_iso_to_datetime  # kept importable for callers needing datetime parsing
