from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlmodel import Session, select

from app.models import Event
from app.services.events import list_alerts_for_date, list_events_for_date
from app.services.utils import (
    DEMO_MODE_SOURCE_FILTER,
    DEMO_SOURCES,
    LIVE_SENSOR_SOURCE,
    age_seconds_now,
    categorize_illuminance,
    current_date,
    humanize_age_seconds,
    parse_boolish,
    parse_floatish,
    parse_iso_to_datetime,
    staleness_category,
)


DEFAULT_NIGHT_START_HOUR = 22
DEFAULT_NIGHT_END_HOUR = 6


@dataclass
class DayMetrics:
    event_count: int
    fall_count: int
    alerts_sent: int
    nighttime_movement_count: int
    average_light_lux: float | None
    average_light_category: str


def _resolve_night_hours(
    night_start_hour: int | None,
    night_end_hour: int | None,
) -> tuple[int, int]:
    start = (
        night_start_hour
        if isinstance(night_start_hour, int) and 0 <= night_start_hour <= 23
        else DEFAULT_NIGHT_START_HOUR
    )
    end = (
        night_end_hour
        if isinstance(night_end_hour, int) and 0 <= night_end_hour <= 23
        else DEFAULT_NIGHT_END_HOUR
    )
    return (start, end)


def _hour_in_window(hour: int, *, start: int, end: int) -> bool:
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def _baseline_dates_for(today_date: date) -> list[str]:
    return [
        (today_date - timedelta(days=offset)).isoformat()
        for offset in reversed(range(1, 8))
    ]


def _weekly_dates_for(today_date: date) -> list[str]:
    return [
        (today_date - timedelta(days=offset)).isoformat()
        for offset in reversed(range(0, 8))
    ]


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _metric_block(*, today_value: int, baseline_total: int, baseline_days: int = 7) -> dict[str, Any]:
    baseline_average = round(baseline_total / max(baseline_days, 1), 2)
    delta = round(today_value - baseline_average, 2)
    direction = "flat"
    if delta > 0:
        direction = "up"
    elif delta < 0:
        direction = "down"
    delta_percent: float | None = None
    if baseline_average > 0:
        delta_percent = round((delta / baseline_average) * 100, 1)
    elif today_value > 0:
        delta_percent = 100.0
    return {
        "today": today_value,
        "baseline_total": baseline_total,
        "baseline_average": baseline_average,
        "delta": delta,
        "delta_percent": delta_percent,
        "direction": direction,
    }


def _day_metrics(
    session: Session,
    *,
    date_str: str,
    source_filter: str | None,
    night_start_hour: int,
    night_end_hour: int,
) -> DayMetrics:
    events = list_events_for_date(session, date_str, source_filter=source_filter)
    alerts = list_alerts_for_date(session, date_str, source_filter=source_filter)
    falls = sum(
        1
        for event in events
        if event.event_type == "fall_detected" and parse_boolish(event.value)
    )
    alerts_sent = sum(1 for alert in alerts if alert.sent_success)

    night_moves = 0
    light_values: list[float] = []
    for event in events:
        if event.event_type == "person_present" and parse_boolish(event.value):
            dt = parse_iso_to_datetime(event.timestamp)
            if dt and _hour_in_window(dt.hour, start=night_start_hour, end=night_end_hour):
                night_moves += 1
        if event.event_type == "illuminance":
            lux = parse_floatish(event.value)
            if lux is not None:
                light_values.append(lux)

    avg_light_lux = _avg(light_values)
    return DayMetrics(
        event_count=len(events),
        fall_count=falls,
        alerts_sent=alerts_sent,
        nighttime_movement_count=night_moves,
        average_light_lux=avg_light_lux,
        average_light_category=categorize_illuminance(avg_light_lux),
    )


def _latest_activity(session: Session, *, source_filter: str | None) -> Event | None:
    statement = select(Event)
    if source_filter == DEMO_MODE_SOURCE_FILTER:
        statement = statement.where(Event.source.in_(DEMO_SOURCES))
    elif source_filter is not None:
        statement = statement.where(Event.source == source_filter)
    statement = statement.order_by(Event.id.desc()).limit(1)
    return session.exec(statement).first()


def _latest_sensor_rows(
    session: Session,
    *,
    source_filter: str | None,
) -> list[Event]:
    statement = select(Event)
    if source_filter == DEMO_MODE_SOURCE_FILTER:
        statement = statement.where(Event.source.in_(DEMO_SOURCES))
    elif source_filter is not None:
        statement = statement.where(Event.source == source_filter)
    statement = statement.order_by(Event.id.desc()).limit(2000)
    rows = list(session.exec(statement))
    latest_by_sensor: dict[str, Event] = {}
    for row in rows:
        if row.sensor_id not in latest_by_sensor:
            latest_by_sensor[row.sensor_id] = row
    return sorted(
        latest_by_sensor.values(),
        key=lambda row: row.sensor_id,
    )


def _notable_changes(
    *,
    fall_metric: dict[str, Any],
    alert_metric: dict[str, Any],
    night_metric: dict[str, Any],
    sensor_rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []

    def maybe_spike(
        *,
        code: str,
        label: str,
        metric: dict[str, Any],
        minimum_jump: int,
    ) -> None:
        today_value = int(metric["today"])
        baseline_average = float(metric["baseline_average"])
        if today_value >= max(minimum_jump, int(baseline_average) + minimum_jump) and today_value >= baseline_average * 1.5:
            changes.append(
                {
                    "code": code,
                    "severity": "warning",
                    "title": f"Higher {label} than baseline",
                    "detail": (
                        f"Today has {today_value} {label} vs a 7-day average of "
                        f"{baseline_average:.2f}."
                    ),
                }
            )

    maybe_spike(
        code="fall_spike",
        label="likely-fall events",
        metric=fall_metric,
        minimum_jump=2,
    )
    maybe_spike(
        code="alert_spike",
        label="alerts sent",
        metric=alert_metric,
        minimum_jump=2,
    )
    maybe_spike(
        code="night_movement_spike",
        label="nighttime movement events",
        metric=night_metric,
        minimum_jump=3,
    )

    stale_sensors = [row for row in sensor_rows if row["staleness"] in {"warn", "stale"}]
    if stale_sensors:
        stale_preview = ", ".join(row["sensor_id"] for row in stale_sensors[:3])
        changes.append(
            {
                "code": "sensor_freshness_warning",
                "severity": "warning",
                "title": "Sensor freshness warning",
                "detail": (
                    f"{len(stale_sensors)} sensor(s) have older data than expected "
                    f"({stale_preview})."
                ),
            }
        )

    if not changes:
        changes.append(
            {
                "code": "no_clear_change",
                "severity": "info",
                "title": "No unusual pattern detected",
                "detail": "Today is within expected variation vs the previous 7 days.",
            }
        )

    return changes


def _daily_light_series(
    session: Session,
    *,
    dates: list[str],
    source_filter: str | None,
) -> dict[str, list[float]]:
    by_day: dict[str, list[float]] = defaultdict(list)
    for date_str in dates:
        for event in list_events_for_date(session, date_str, source_filter=source_filter):
            if event.event_type != "illuminance":
                continue
            lux = parse_floatish(event.value)
            if lux is None:
                continue
            by_day[date_str].append(lux)
    return by_day


def get_today_trends(
    session: Session,
    *,
    mode: str,
    source_filter: str | None,
    night_start_hour: int | None = None,
    night_end_hour: int | None = None,
) -> dict[str, Any]:
    start_hour, end_hour = _resolve_night_hours(night_start_hour, night_end_hour)
    today_date = date.fromisoformat(current_date())
    today_str = today_date.isoformat()
    baseline_dates = _baseline_dates_for(today_date)

    today_metrics = _day_metrics(
        session,
        date_str=today_str,
        source_filter=source_filter,
        night_start_hour=start_hour,
        night_end_hour=end_hour,
    )
    baseline_metrics = [
        _day_metrics(
            session,
            date_str=baseline_date,
            source_filter=source_filter,
            night_start_hour=start_hour,
            night_end_hour=end_hour,
        )
        for baseline_date in baseline_dates
    ]
    baseline_totals = {
        "events": sum(item.event_count for item in baseline_metrics),
        "falls": sum(item.fall_count for item in baseline_metrics),
        "alerts_sent": sum(item.alerts_sent for item in baseline_metrics),
        "night_moves": sum(item.nighttime_movement_count for item in baseline_metrics),
    }
    baseline_light_values = [
        item.average_light_lux for item in baseline_metrics if item.average_light_lux is not None
    ]
    baseline_average_lux = _avg([float(value) for value in baseline_light_values])

    latest_activity = _latest_activity(session, source_filter=source_filter)
    latest_activity_age = age_seconds_now(latest_activity.timestamp) if latest_activity else None

    sensor_rows: list[dict[str, Any]] = []
    for row in _latest_sensor_rows(session, source_filter=source_filter):
        age_seconds = age_seconds_now(row.timestamp)
        sensor_rows.append(
            {
                "sensor_id": row.sensor_id,
                "room": row.room,
                "source": row.source,
                "last_event_timestamp": row.timestamp,
                "age_seconds": age_seconds,
                "age_human": humanize_age_seconds(age_seconds),
                "staleness": staleness_category(age_seconds),
                "offline": staleness_category(age_seconds) in {"warn", "stale"},
            }
        )

    fall_metric = _metric_block(
        today_value=today_metrics.fall_count,
        baseline_total=baseline_totals["falls"],
    )
    alert_metric = _metric_block(
        today_value=today_metrics.alerts_sent,
        baseline_total=baseline_totals["alerts_sent"],
    )
    night_metric = _metric_block(
        today_value=today_metrics.nighttime_movement_count,
        baseline_total=baseline_totals["night_moves"],
    )

    changes = _notable_changes(
        fall_metric=fall_metric,
        alert_metric=alert_metric,
        night_metric=night_metric,
        sensor_rows=sensor_rows,
    )
    unusual_detected = any(change["severity"] == "warning" for change in changes)

    latest_light = None
    for event in list_events_for_date(session, today_str, source_filter=source_filter):
        if event.event_type == "illuminance":
            latest_light = event
    if latest_light is None and latest_activity is not None and latest_activity.event_type == "illuminance":
        latest_light = latest_activity

    latest_lux = parse_floatish(latest_light.value) if latest_light else None

    return {
        "mode": mode,
        "window": {
            "today": today_str,
            "baseline_start": baseline_dates[0],
            "baseline_end": baseline_dates[-1],
        },
        "night_window": {
            "start_hour": start_hour,
            "end_hour": end_hour,
        },
        "metrics": {
            "fall_count": fall_metric,
            "alerts_sent": alert_metric,
            "nighttime_movement_count": night_metric,
            "event_count": _metric_block(
                today_value=today_metrics.event_count,
                baseline_total=baseline_totals["events"],
            ),
        },
        "light": {
            "latest_category": categorize_illuminance(latest_lux),
            "latest_lux": latest_lux,
            "latest_timestamp": latest_light.timestamp if latest_light else None,
            "today_average_category": today_metrics.average_light_category,
            "today_average_lux": today_metrics.average_light_lux,
            "baseline_average_category": categorize_illuminance(baseline_average_lux),
            "baseline_average_lux": baseline_average_lux,
        },
        "activity": {
            "last_activity_timestamp": latest_activity.timestamp if latest_activity else None,
            "last_activity_age_seconds": latest_activity_age,
            "last_activity_age_human": humanize_age_seconds(latest_activity_age),
            "last_activity_staleness": staleness_category(latest_activity_age),
        },
        "freshness": {
            "offline": any(row["offline"] for row in sensor_rows),
            "stale_sensor_count": sum(1 for row in sensor_rows if row["offline"]),
            "sensors": sensor_rows,
        },
        "notable_changes": changes,
        "unusual_detected": unusual_detected,
        "generated_from": "sqlite_local_timeline",
        "model_hint": "gemma4:e2b",
    }


def get_week_trends(
    session: Session,
    *,
    mode: str,
    source_filter: str | None,
    night_start_hour: int | None = None,
    night_end_hour: int | None = None,
) -> dict[str, Any]:
    start_hour, end_hour = _resolve_night_hours(night_start_hour, night_end_hour)
    today_date = date.fromisoformat(current_date())
    dates = _weekly_dates_for(today_date)
    light_by_day = _daily_light_series(session, dates=dates, source_filter=source_filter)

    rows: list[dict[str, Any]] = []
    for day_str in dates:
        metrics = _day_metrics(
            session,
            date_str=day_str,
            source_filter=source_filter,
            night_start_hour=start_hour,
            night_end_hour=end_hour,
        )
        day_date = date.fromisoformat(day_str)
        average_lux = _avg(light_by_day.get(day_str, []))
        rows.append(
            {
                "date": day_str,
                "label": day_date.strftime("%a"),
                "event_count": metrics.event_count,
                "fall_count": metrics.fall_count,
                "alerts_sent": metrics.alerts_sent,
                "nighttime_movement_count": metrics.nighttime_movement_count,
                "average_light_lux": average_lux,
                "average_light_category": categorize_illuminance(average_lux),
            }
        )

    return {
        "mode": mode,
        "window": {
            "start_date": dates[0],
            "end_date": dates[-1],
        },
        "night_window": {
            "start_hour": start_hour,
            "end_hour": end_hour,
        },
        "days": rows,
        "generated_from": "sqlite_local_timeline",
    }


def summarize_trends_for_humans(trends: dict[str, Any]) -> str:
    metrics = trends.get("metrics") or {}
    falls = (metrics.get("fall_count") or {}).get("today", 0)
    alerts = (metrics.get("alerts_sent") or {}).get("today", 0)
    night_moves = (metrics.get("nighttime_movement_count") or {}).get("today", 0)
    activity = trends.get("activity") or {}
    age_human = activity.get("last_activity_age_human", "unknown")
    unusual = bool(trends.get("unusual_detected"))
    status = "unusual changes detected" if unusual else "no unusual pattern detected"
    return (
        f"Today: {falls} likely-fall event(s), {alerts} alert(s) sent, "
        f"{night_moves} nighttime movement event(s). "
        f"Last activity: {age_human}. Trend status: {status}."
    )


def summarize_notable_changes(trends: dict[str, Any]) -> str:
    changes = trends.get("notable_changes") or []
    warnings = [item for item in changes if item.get("severity") == "warning"]
    if not warnings:
        return "No unusual trend changes were detected today."
    lines = ["Unusual trend changes:"]
    for item in warnings[:4]:
        lines.append(f"- {item.get('title')}: {item.get('detail')}")
    return "\n".join(lines)


def mode_source_for_trends(source_filter: str | None) -> str:
    return "live" if source_filter == LIVE_SENSOR_SOURCE else "demo"
