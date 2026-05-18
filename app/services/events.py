from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.models import Alert, Event
from app.schemas import TodayStats
from app.services.alerts import handle_event_alerts
from app.services.utils import (
    DEMO_MODE_SOURCE_FILTER,
    DEMO_SOURCES,
    LIVE_SENSOR_SOURCE,
    categorize_illuminance,
    current_date,
    current_timestamp,
    normalize_metadata,
    normalize_value,
    parse_boolish,
    parse_floatish,
)


def _apply_event_source_filter(statement, model: type[Event], source_filter: str | None):
    if source_filter is None:
        return statement
    if source_filter == DEMO_MODE_SOURCE_FILTER:
        return statement.where(model.source.in_(DEMO_SOURCES))
    return statement.where(model.source == source_filter)


def _apply_sensor_filter(statement, model: type[Event], sensor_id_filter: str | None):
    if sensor_id_filter is None:
        return statement
    return statement.where(model.sensor_id == sensor_id_filter)


def create_event(
    session: Session,
    *,
    sensor_id: str,
    room: str,
    event_type: str,
    value: Any,
    source: str,
    metadata_json: Any = None,
    trigger_alerts: bool = True,
) -> Event:
    event = Event(
        timestamp=current_timestamp(),
        sensor_id=sensor_id,
        room=room,
        event_type=event_type,
        value=normalize_value(value),
        source=source,
        metadata_json=normalize_metadata(metadata_json),
    )
    session.add(event)
    session.commit()
    session.refresh(event)

    if trigger_alerts:
        handle_event_alerts(session, event)

    return event


def list_recent_events(
    session: Session,
    *,
    limit: int = 50,
    source_filter: str | None = None,
) -> list[Event]:
    statement = select(Event)
    statement = _apply_event_source_filter(statement, Event, source_filter)
    statement = statement.order_by(Event.id.desc()).limit(limit)
    return list(session.exec(statement))


def list_latest_events_by_sensor_type(
    session: Session,
    *,
    source_filter: str | None = None,
    scan_limit: int = 5000,
) -> list[Event]:
    statement = select(Event)
    statement = _apply_event_source_filter(statement, Event, source_filter)
    statement = statement.order_by(Event.id.desc()).limit(max(1, scan_limit))

    latest: dict[tuple[str, str], Event] = {}
    for event in session.exec(statement):
        key = (event.sensor_id, event.event_type)
        if key not in latest:
            latest[key] = event

    return sorted(latest.values(), key=lambda event: event.id, reverse=True)


def list_recent_alerts(
    session: Session,
    *,
    limit: int = 20,
    live_only: bool = False,
    source_filter: str | None = None,
) -> list[Alert]:
    # `live_only` is the legacy boolean; `source_filter` is the generic param.
    statement = select(Alert)
    effective_filter = source_filter or (LIVE_SENSOR_SOURCE if live_only else None)
    if effective_filter is not None:
        statement = statement.join(Event, Alert.event_id == Event.id)
        statement = _apply_event_source_filter(statement, Event, effective_filter)
    statement = statement.order_by(Alert.id.desc()).limit(limit)
    return list(session.exec(statement))


def get_latest_live_event(session: Session) -> Event | None:
    """Latest event with source='live_sensor' regardless of type.

    Used by the topnav "Last live" indicator to detect ingestion staleness.
    """
    statement = (
        select(Event)
        .where(Event.source == LIVE_SENSOR_SOURCE)
        .order_by(Event.id.desc())
        .limit(1)
    )
    return session.exec(statement).first()


def get_latest_event_by_type(
    session: Session,
    event_type: str,
    source_filter: str | None = None,
    sensor_id_filter: str | None = None,
) -> Event | None:
    statement = select(Event).where(Event.event_type == event_type)
    statement = _apply_event_source_filter(statement, Event, source_filter)
    statement = _apply_sensor_filter(statement, Event, sensor_id_filter)
    statement = statement.order_by(Event.id.desc()).limit(1)
    return session.exec(statement).first()


def get_latest_fall_event(
    session: Session,
    source_filter: str | None = None,
    sensor_id_filter: str | None = None,
) -> Event | None:
    return get_latest_event_by_type(
        session,
        "fall_detected",
        source_filter,
        sensor_id_filter=sensor_id_filter,
    )


def get_latest_true_fall_event(
    session: Session,
    source_filter: str | None = None,
    sensor_id_filter: str | None = None,
) -> Event | None:
    statement = (
        select(Event)
        .where(Event.event_type == "fall_detected")
        .where(Event.value == "true")
    )
    statement = _apply_event_source_filter(statement, Event, source_filter)
    statement = _apply_sensor_filter(statement, Event, sensor_id_filter)
    statement = statement.order_by(Event.id.desc()).limit(1)
    return session.exec(statement).first()


def get_latest_illuminance_event(
    session: Session,
    source_filter: str | None = None,
    sensor_id_filter: str | None = None,
) -> Event | None:
    return get_latest_event_by_type(
        session,
        "illuminance",
        source_filter,
        sensor_id_filter=sensor_id_filter,
    )


def get_latest_light_context(
    session: Session,
    source_filter: str | None = None,
    sensor_id_filter: str | None = None,
) -> dict[str, Any] | None:
    event = get_latest_illuminance_event(
        session,
        source_filter,
        sensor_id_filter=sensor_id_filter,
    )
    if event is None:
        return None
    lux = parse_floatish(event.value)
    return {
        "lux": lux,
        "category": categorize_illuminance(lux),
        "timestamp": event.timestamp,
        "room": event.room,
        "source": event.source,
        "sensor_id": event.sensor_id,
    }


def get_event_before(
    session: Session,
    *,
    timestamp: str,
    event_type: str,
    value_filter: str | None = None,
    source_filter: str | None = None,
    sensor_id_filter: str | None = None,
) -> Event | None:
    statement = (
        select(Event)
        .where(Event.event_type == event_type)
        .where(Event.timestamp < timestamp)
    )
    if value_filter is not None:
        statement = statement.where(Event.value == value_filter)
    statement = _apply_event_source_filter(statement, Event, source_filter)
    statement = _apply_sensor_filter(statement, Event, sensor_id_filter)
    statement = statement.order_by(Event.id.desc()).limit(1)
    return session.exec(statement).first()


def get_event_after(
    session: Session,
    *,
    timestamp: str,
    event_type: str,
    value_filter: str | None = None,
    source_filter: str | None = None,
    sensor_id_filter: str | None = None,
) -> Event | None:
    statement = (
        select(Event)
        .where(Event.event_type == event_type)
        .where(Event.timestamp > timestamp)
    )
    if value_filter is not None:
        statement = statement.where(Event.value == value_filter)
    statement = _apply_event_source_filter(statement, Event, source_filter)
    statement = _apply_sensor_filter(statement, Event, sensor_id_filter)
    statement = statement.order_by(Event.id.asc()).limit(1)
    return session.exec(statement).first()


def get_alert_for_event(session: Session, event_id: int) -> Alert | None:
    statement = select(Alert).where(Alert.event_id == event_id).order_by(Alert.id.desc()).limit(1)
    return session.exec(statement).first()


def list_today_events(
    session: Session,
    source_filter: str | None = None,
) -> list[Event]:
    today = current_date()
    return list_events_for_date(session, today, source_filter=source_filter)


def list_events_for_date(
    session: Session,
    date_str: str,
    source_filter: str | None = None,
) -> list[Event]:
    statement = select(Event).where(Event.timestamp.like(f"{date_str}%"))
    statement = _apply_event_source_filter(statement, Event, source_filter)
    statement = statement.order_by(Event.id.asc())
    return list(session.exec(statement))


def list_alerts_for_date(
    session: Session,
    date_str: str,
    source_filter: str | None = None,
) -> list[Alert]:
    statement = select(Alert).where(Alert.timestamp.like(f"{date_str}%"))
    if source_filter is not None:
        statement = statement.join(Event, Alert.event_id == Event.id)
        statement = _apply_event_source_filter(statement, Event, source_filter)
    statement = statement.order_by(Alert.id.asc())
    return list(session.exec(statement))


def get_today_stats(
    session: Session,
    source_filter: str | None = None,
) -> TodayStats:
    today = current_date()
    statement = select(Event).where(Event.timestamp.like(f"{today}%"))
    statement = _apply_event_source_filter(statement, Event, source_filter)
    statement = statement.order_by(Event.id.desc())
    today_events = list(session.exec(statement))

    total_events_today = len(today_events)
    fall_events_today = sum(
        1
        for event in today_events
        if event.event_type == "fall_detected" and parse_boolish(event.value)
    )

    latest_person = next(
        (event for event in today_events if event.event_type == "person_present"),
        None,
    )
    latest_fall = next(
        (event for event in today_events if event.event_type == "fall_detected"),
        None,
    )

    return TodayStats(
        total_events_today=total_events_today,
        fall_events_today=fall_events_today,
        latest_person_present=latest_person,
        latest_fall_state=latest_fall,
    )
