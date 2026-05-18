from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Any

import httpx
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlmodel import Session

from app.config import get_settings
from app.config import load_runtime_care_context
from app.models import Alert, Event
from app.services.events import get_alert_for_event, list_alerts_for_date, list_events_for_date
from app.services.utils import (
    age_seconds_now,
    current_date,
    current_timestamp,
    humanize_age_seconds,
    parse_boolish,
    parse_floatish,
    parse_iso_to_datetime,
    staleness_category,
)


GEMMA_WEEKLY_MODEL = "gemma4:e2b"
GEMMA_WEEKLY_MODEL_LABEL = "Gemma 4 E2B"
DISCLAIMER = "Not a medical diagnosis."
FALL_CLUSTER_WINDOW_MINUTES = 10


class WeeklyReportGemmaError(RuntimeError):
    pass


@dataclass(slots=True)
class WeeklyReportResult:
    pdf_bytes: bytes
    filename: str
    model_name: str
    used_mock: bool
    context: dict[str, Any]
    gemma_text: str


def _date_range(start_date: str | None, end_date: str | None) -> tuple[date, date]:
    if end_date:
        end = date.fromisoformat(end_date)
    else:
        end = date.fromisoformat(current_date())
    if start_date:
        start = date.fromisoformat(start_date)
    else:
        start = end - timedelta(days=6)
    if start > end:
        raise ValueError("start_date must be on or before end_date")
    return start, end


def _dates_between(start: date, end: date) -> list[str]:
    days = (end - start).days
    return [(start + timedelta(days=offset)).isoformat() for offset in range(days + 1)]


def _event_rows_for_dates(
    session: Session,
    *,
    dates: list[str],
    source_filter: str | None,
) -> list[Event]:
    rows: list[Event] = []
    for day in dates:
        rows.extend(list_events_for_date(session, day, source_filter=source_filter))
    return rows


def _alert_rows_for_dates(
    session: Session,
    *,
    dates: list[str],
    source_filter: str | None,
) -> list[Alert]:
    rows: list[Alert] = []
    for day in dates:
        rows.extend(list_alerts_for_date(session, day, source_filter=source_filter))
    return rows


def _hour_in_window(hour: int, *, start: int, end: int) -> bool:
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _format_human_datetime(value: str | None) -> str:
    dt = parse_iso_to_datetime(value or "")
    if dt is None:
        return value or "Unknown time"
    return f"{dt.strftime('%B')} {dt.day}, {dt.year}, {dt.strftime('%H:%M')}"


def _format_time_only(value: str | None) -> str:
    dt = parse_iso_to_datetime(value or "")
    return dt.strftime("%H:%M") if dt else "unknown"


def _format_human_date_range(start: date, end: date) -> str:
    if start.year == end.year and start.month == end.month:
        return f"{start.strftime('%B')} {start.day}-{end.day}, {end.year}"
    if start.year == end.year:
        return f"{start.strftime('%B')} {start.day}-{end.strftime('%B')} {end.day}, {end.year}"
    return f"{start.strftime('%B')} {start.day}, {start.year}-{end.strftime('%B')} {end.day}, {end.year}"


def format_room_name(room_id: str | None, display_names: dict[str, str] | None = None) -> str:
    clean = (room_id or "").strip()
    if not clean:
        return "Unassigned Room"
    if display_names and display_names.get(clean):
        return display_names[clean].strip()
    auto_match = re.fullmatch(r"auto_room_(\d+)", clean)
    if auto_match:
        return f"Sensor Area {auto_match.group(1)}"
    if clean == "demo_room":
        return "Demo Room"
    readable = re.sub(r"[_-]+", " ", clean).strip()
    return readable.title() if readable else "Unassigned Room"


def _is_fall_like(event: Event) -> bool:
    return event.event_type == "fall_detected" and parse_boolish(event.value)


def _alert_status(successes: int, failures: int) -> str:
    if successes and failures:
        return "Partially sent"
    if successes:
        return "Sent"
    if failures:
        return "Failed"
    return "No alert recorded"


def _episode_confidence(count: int, incomplete: bool) -> str:
    if incomplete:
        return "Low"
    if count >= 3:
        return "High"
    return "Medium"


def _episode_interpretation(episode: dict[str, Any]) -> str:
    count = int(episode["raw_detection_count"])
    duration = episode.get("duration_minutes")
    if count >= 3:
        return (
            f"{count} fall-like detections occurred within approximately {duration or 0} minutes. "
            "This may represent one fall episode, repeated movement after a fall, or a false alarm caused "
            "by unusual motion. Caregiver confirmation is recommended."
        )
    if count == 2:
        return (
            "Two fall-like detections occurred close together in the same area. Treat this as one possible "
            "episode until a caregiver confirms whether it was a true fall or a false alarm."
        )
    return (
        "A single fall-like detection was recorded. This may be a true fall or unusual motion. Caregiver "
        "review is recommended before drawing conclusions."
    )


def _cluster_fall_episodes(session: Session, fall_events: list[Event]) -> list[dict[str, Any]]:
    sortable: list[tuple[datetime | None, Event]] = [
        (parse_iso_to_datetime(event.timestamp), event) for event in fall_events
    ]
    sortable.sort(key=lambda item: item[0] or datetime.min)
    grouped: list[list[Event]] = []
    for dt, event in sortable:
        placed = False
        for group in reversed(grouped):
            latest = group[-1]
            latest_dt = parse_iso_to_datetime(latest.timestamp)
            same_room = (latest.room or "") == (event.room or "")
            close = bool(
                dt
                and latest_dt
                and abs((dt - latest_dt).total_seconds()) <= FALL_CLUSTER_WINDOW_MINUTES * 60
            )
            if same_room and close:
                group.append(event)
                placed = True
                break
        if not placed:
            grouped.append([event])

    episodes: list[dict[str, Any]] = []
    for index, group in enumerate(grouped, start=1):
        dts = [parse_iso_to_datetime(event.timestamp) for event in group]
        complete = all(dt is not None for dt in dts)
        valid_dts = [dt for dt in dts if dt is not None]
        start_dt = min(valid_dts) if valid_dts else None
        end_dt = max(valid_dts) if valid_dts else None
        duration = int(round((end_dt - start_dt).total_seconds() / 60)) if start_dt and end_dt else None
        successes = 0
        failures = 0
        channels: set[str] = set()
        for event in group:
            alert = get_alert_for_event(session, event.id or -1) if event.id is not None else None
            if alert is None:
                continue
            if alert.sent_success:
                successes += 1
            else:
                failures += 1
            if alert.sent_channel:
                channels.add(alert.sent_channel)
        room_id = group[0].room or "unknown"
        episode = {
            "episode_number": index,
            "room_id": room_id,
            "location": format_room_name(room_id),
            "start_timestamp": start_dt.isoformat() if start_dt else group[0].timestamp,
            "end_timestamp": end_dt.isoformat() if end_dt and end_dt != start_dt else None,
            "raw_detection_count": len(group),
            "raw_detection_ids": [event.id for event in group],
            "raw_timestamps": [event.timestamp for event in group],
            "sensor_ids": sorted({event.sensor_id for event in group}),
            "alert_success_count": successes,
            "alert_failure_count": failures,
            "alert_status": _alert_status(successes, failures),
            "alert_channels": sorted(channels),
            "review_status": "Needs caregiver review",
            "confidence": _episode_confidence(len(group), not complete),
            "duration_minutes": duration,
        }
        episode["interpretation"] = _episode_interpretation(episode)
        episodes.append(episode)
    return episodes


def _sensor_reliability(events: list[Event]) -> list[dict[str, Any]]:
    by_sensor: dict[str, list[Event]] = defaultdict(list)
    for event in events:
        by_sensor[event.sensor_id].append(event)
    rows: list[dict[str, Any]] = []
    for sensor_id, sensor_events in sorted(by_sensor.items()):
        latest = max(sensor_events, key=lambda event: parse_iso_to_datetime(event.timestamp) or datetime.min)
        age = age_seconds_now(latest.timestamp)
        rows.append(
            {
                "sensor_id": sensor_id,
                "room_id": latest.room,
                "room": format_room_name(latest.room),
                "event_count": len(sensor_events),
                "last_seen": latest.timestamp,
                "age_human": humanize_age_seconds(age),
                "staleness": staleness_category(age),
            }
        )
    return rows


def _signal_source(type_counts: Counter[str]) -> str:
    vitals = sum(type_counts.get(key, 0) for key in ("heart_rate", "respiration_rate"))
    presence = sum(type_counts.get(key, 0) for key in ("person_present", "target_count", "target_distance"))
    if vitals or presence:
        return "heart/breathing/presence monitoring"
    if type_counts.get("illuminance"):
        return "light/presence monitoring"
    if not type_counts:
        return "unknown"
    return ", ".join(name.replace("_", " ") for name, _ in type_counts.most_common(2))


def _room_activity(events: list[Event], episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_room: dict[str, list[Event]] = defaultdict(list)
    for event in events:
        by_room[event.room or "unknown"].append(event)
    episode_counts = Counter(episode["room_id"] for episode in episodes)
    rows: list[dict[str, Any]] = []
    for room_id, room_events in by_room.items():
        fall_count = sum(1 for event in room_events if _is_fall_like(event))
        type_counts = Counter(event.event_type for event in room_events)
        note = (
            "Highest safety concern this week"
            if episode_counts.get(room_id, 0) and episode_counts.get(room_id, 0) == max(episode_counts.values() or [0])
            else "No fall-like detections"
            if fall_count == 0
            else "Fall-like detections recorded"
        )
        rows.append(
            {
                "room_id": room_id,
                "room_name": format_room_name(room_id),
                "sensor_readings": len(room_events),
                "raw_fall_like_detections": fall_count,
                "likely_fall_episodes": episode_counts.get(room_id, 0),
                "main_signal_source": _signal_source(type_counts),
                "safety_note": note,
            }
        )
    return sorted(rows, key=lambda row: (-row["likely_fall_episodes"], -row["sensor_readings"], row["room_name"]))


def _night_bathroom_activity(
    events: list[Event],
    episodes: list[dict[str, Any]],
    *,
    night_start_hour: int,
    night_end_hour: int,
) -> dict[str, Any]:
    night_events: list[Event] = []
    bathroom_events: list[Event] = []
    bathroom_tokens = ("bath", "bathroom", "toilet", "wc")
    for event in events:
        dt = parse_iso_to_datetime(event.timestamp)
        is_night = bool(dt and _hour_in_window(dt.hour, start=night_start_hour, end=night_end_hour))
        room_key = (event.room or "").lower()
        room_name = format_room_name(event.room).lower()
        is_bathroom = any(token in room_key or token in room_name for token in bathroom_tokens)
        if is_night:
            night_events.append(event)
        if is_night and is_bathroom:
            bathroom_events.append(event)
    nighttime_fall_episodes = 0
    for episode in episodes:
        dt = parse_iso_to_datetime(episode.get("start_timestamp") or "")
        if dt and _hour_in_window(dt.hour, start=night_start_hour, end=night_end_hour):
            nighttime_fall_episodes += 1
    return {
        "night_sensor_readings": len(night_events),
        "night_bathroom_events": len(bathroom_events),
        "nighttime_fall_episodes": nighttime_fall_episodes,
        "night_window": f"{night_start_hour:02d}:00-{night_end_hour:02d}:00",
    }


def _sleep_rest_pattern(events: list[Event]) -> dict[str, Any]:
    heart_values: list[float] = []
    respiration_values: list[float] = []
    presence_count = 0
    target_distances: list[float] = []
    for event in events:
        if event.event_type == "heart_rate":
            value = parse_floatish(event.value)
            if value is not None:
                heart_values.append(value)
        elif event.event_type == "respiration_rate":
            value = parse_floatish(event.value)
            if value is not None:
                respiration_values.append(value)
        elif event.event_type in {"person_present", "target_present"} and parse_boolish(event.value):
            presence_count += 1
        elif event.event_type == "target_distance":
            value = parse_floatish(event.value)
            if value is not None:
                target_distances.append(value)
    return {
        "heart_samples": len(heart_values),
        "heart_avg": _avg(heart_values),
        "respiration_samples": len(respiration_values),
        "respiration_avg": _avg(respiration_values),
        "presence_events": presence_count,
        "distance_samples": len(target_distances),
        "distance_avg_cm": _avg(target_distances),
    }


def _resident_safety_score(
    *,
    episodes: list[dict[str, Any]],
    raw_fall_detections: int,
    generated_at: str,
) -> dict[str, Any]:
    score = 100
    decreases: list[str] = []
    episode_penalty = min(55, len(episodes) * 22)
    if episode_penalty:
        score -= episode_penalty
        decreases.append(f"{len(episodes)} likely fall episode(s)")
    repeated_clusters = sum(1 for episode in episodes if int(episode["raw_detection_count"]) >= 3)
    if repeated_clusters:
        penalty = min(20, repeated_clusters * 11)
        score -= penalty
        decreases.append("repeated fall-like cluster")
    recent_unreviewed = 0
    generated_dt = parse_iso_to_datetime(generated_at)
    for episode in episodes:
        start_dt = parse_iso_to_datetime(episode.get("start_timestamp") or "")
        if generated_dt and start_dt and (generated_dt - start_dt).total_seconds() <= 48 * 3600:
            recent_unreviewed += 1
    if recent_unreviewed:
        score -= min(15, recent_unreviewed * 10)
        decreases.append("recent unreviewed fall-like event")
    if raw_fall_detections > len(episodes):
        decreases.append(f"{raw_fall_detections} raw fall-like detections grouped into episodes")
    score = max(0, min(100, score))
    if score >= 85:
        label = "Low concern"
    elif score >= 65:
        label = "Monitor"
    elif score >= 40:
        label = "Elevated concern"
    else:
        label = "High concern"
    if not decreases:
        decreases.append("no likely fall episodes detected")
    return {"score": score, "label": label, "decreases": decreases}


def _system_reliability_score(
    *,
    events: list[Event],
    alerts: list[Alert],
    reliability_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    score = 100
    factors: list[str] = []
    stale_rows = [row for row in reliability_rows if row["staleness"] in {"warn", "stale", "none"}]
    failed_alerts = [alert for alert in alerts if not alert.sent_success]
    successful_alerts = [alert for alert in alerts if alert.sent_success]
    if stale_rows:
        score -= min(45, len(stale_rows) * 15)
        factors.append(f"{len(stale_rows)} stale/offline sensor(s)")
    else:
        factors.append("all sensors were fresh")
    if failed_alerts:
        score -= min(20, len(failed_alerts) * 4)
        factors.append(f"{len(failed_alerts)} failed alert(s)")
    elif alerts:
        factors.append("all alerts successfully sent")
    if not events:
        score -= 10
        factors.append("no sensor data was available")
    else:
        factors.append("sensor data was available throughout the report window")
    score = max(0, min(100, score))
    if score >= 90:
        label = "Excellent"
    elif score >= 75:
        label = "Good"
    elif score >= 55:
        label = "Degraded"
    else:
        label = "Needs attention"
    return {
        "score": score,
        "label": label,
        "factors": factors,
        "alerts_successful": len(successful_alerts),
        "alerts_failed": len(failed_alerts),
        "stale_sensors": len(stale_rows),
    }


def _alert_delivery_summary(alerts: list[Alert], episodes: list[dict[str, Any]]) -> dict[str, Any]:
    sent = sum(1 for alert in alerts if alert.sent_success)
    failed = len(alerts) - sent
    return {
        "alerts_triggered": len(alerts),
        "alerts_sent": sent,
        "alerts_failed": failed,
        "acknowledgement_tracking_enabled": False,
        "acknowledged": None,
        "unresolved_unreviewed": len(episodes),
        "note": "Caregiver acknowledgment tracking is not enabled yet.",
    }


def _baseline_summary(
    session: Session,
    *,
    start: date,
    end: date,
    source_filter: str | None,
    night_start_hour: int,
    night_end_hour: int,
) -> dict[str, Any]:
    span = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span - 1)
    dates = _dates_between(prev_start, prev_end)
    events = _event_rows_for_dates(session, dates=dates, source_filter=source_filter)
    alerts = _alert_rows_for_dates(session, dates=dates, source_filter=source_filter)
    if not events and not alerts:
        return {
            "available": False,
            "message": "Baseline comparison: Not enough previous data yet. This week will be used as the starting baseline.",
        }
    falls = [event for event in events if _is_fall_like(event)]
    episodes = _cluster_fall_episodes(session, falls)
    reliability_rows = _sensor_reliability(events)
    night = _night_bathroom_activity(
        events,
        episodes,
        night_start_hour=night_start_hour,
        night_end_hour=night_end_hour,
    )
    sleep = _sleep_rest_pattern(events)
    system = _system_reliability_score(events=events, alerts=alerts, reliability_rows=reliability_rows)
    daytime = 0
    for event in events:
        dt = parse_iso_to_datetime(event.timestamp)
        if dt and not _hour_in_window(dt.hour, start=night_start_hour, end=night_end_hour):
            daytime += 1
    return {
        "available": True,
        "date_range": _format_human_date_range(prev_start, prev_end),
        "raw_fall_detections": len(falls),
        "likely_fall_episodes": len(episodes),
        "night_sensor_readings": night["night_sensor_readings"],
        "night_bathroom_events": night["night_bathroom_events"],
        "daytime_sensor_readings": daytime,
        "heart_avg": sleep["heart_avg"],
        "respiration_avg": sleep["respiration_avg"],
        "system_reliability_score": system["score"],
    }


def _executive_summary(ctx: dict[str, Any]) -> str:
    episodes = ctx["fall_episodes"]
    raw_falls = ctx["totals"]["raw_fall_like_detections"]
    safety_label = ctx["resident_safety_score"]["label"].lower()
    if episodes:
        first = episodes[0]
        cluster_text = (
            f" One episode occurred as a cluster of repeated detections on "
            f"{_format_human_datetime(first['start_timestamp']).split(',')[0]}."
            if int(first["raw_detection_count"]) > 1
            else ""
        )
        return (
            f"This week showed a {safety_label} safety pattern. Emergyx detected "
            f"{len(episodes)} likely fall episode(s) based on {raw_falls} raw fall-like sensor detection(s)."
            f"{cluster_text} {ctx['alert_delivery']['alerts_sent']} alert(s) were successfully sent, and "
            f"the system reliability score was {ctx['system_reliability_score']['score']} out of 100."
        )
    return (
        "This week showed no likely fall episodes in the recorded sensor timeline. Emergyx collected "
        f"{ctx['totals']['sensor_readings']} sensor reading(s), with a system reliability score of "
        f"{ctx['system_reliability_score']['score']} out of 100."
    )


def _recommended_actions(ctx: dict[str, Any]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if ctx["fall_episodes"]:
        actions.extend(
            [
                {
                    "priority": "High",
                    "action": "Review the incident timeline and confirm true fall versus false alarm.",
                },
                {
                    "priority": "High",
                    "action": "Check for dizziness, weakness, pain, confusion, or difficulty standing after the episode.",
                },
                {
                    "priority": "Medium",
                    "action": "Inspect the area for fall risks such as poor lighting, rugs, obstacles, and missing support rails.",
                },
                {
                    "priority": "Low",
                    "action": "Continue monitoring for repeated fall-like detections over the next week.",
                },
            ]
        )
    else:
        actions.extend(
            [
                {"priority": "Low", "action": "Continue normal monitoring and review any new alerts promptly."},
                {"priority": "Low", "action": "Use this week as a baseline for future changes in activity and rest signals."},
            ]
        )
    if ctx["system_reliability_score"]["score"] < 90:
        actions.append(
            {
                "priority": "Medium",
                "action": "Check stale or offline sensors so future safety events are not missed.",
            }
        )
    return actions


def _build_weekly_context(
    session: Session,
    *,
    mode: str,
    source_filter: str | None,
    start_date: str | None,
    end_date: str | None,
    night_start_hour: int,
    night_end_hour: int,
) -> dict[str, Any]:
    start, end = _date_range(start_date, end_date)
    dates = _dates_between(start, end)
    generated_at = current_timestamp()
    events = _event_rows_for_dates(session, dates=dates, source_filter=source_filter)
    alerts = _alert_rows_for_dates(session, dates=dates, source_filter=source_filter)
    fall_events = [event for event in events if _is_fall_like(event)]
    episodes = _cluster_fall_episodes(session, fall_events)
    reliability_rows = _sensor_reliability(events)
    night = _night_bathroom_activity(
        events,
        episodes,
        night_start_hour=night_start_hour,
        night_end_hour=night_end_hour,
    )
    sleep = _sleep_rest_pattern(events)
    resident_score = _resident_safety_score(
        episodes=episodes,
        raw_fall_detections=len(fall_events),
        generated_at=generated_at,
    )
    system_score = _system_reliability_score(events=events, alerts=alerts, reliability_rows=reliability_rows)
    alert_delivery = _alert_delivery_summary(alerts, episodes)
    room_activity = _room_activity(events, episodes)
    ctx = {
        "mode": mode,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "date_range_human": _format_human_date_range(start, end),
        "generated_at": generated_at,
        "care_context": load_runtime_care_context(),
        "generated_at_human": _format_human_datetime(generated_at),
        "model_name": GEMMA_WEEKLY_MODEL,
        "model_label": GEMMA_WEEKLY_MODEL_LABEL,
        "totals": {
            "sensor_readings": len(events),
            "alerts": len(alerts),
            "alerts_sent": alert_delivery["alerts_sent"],
            "raw_fall_like_detections": len(fall_events),
            "likely_fall_episodes": len(episodes),
        },
        "resident_safety_score": resident_score,
        "system_reliability_score": system_score,
        "safety_score": resident_score,
        "fall_episodes": episodes,
        "key_incidents": episodes,
        "room_activity": room_activity,
        "night_bathroom": night,
        "sleep_rest": sleep,
        "sensor_reliability": reliability_rows,
        "alert_delivery": alert_delivery,
        "baseline_comparison": _baseline_summary(
            session,
            start=start,
            end=end,
            source_filter=source_filter,
            night_start_hour=night_start_hour,
            night_end_hour=night_end_hour,
        ),
        "technical_appendix": {
            "raw_room_ids": sorted({event.room for event in events if event.room}),
            "sensor_ids": sorted({event.sensor_id for event in events if event.sensor_id}),
            "raw_fall_timestamps": [event.timestamp for event in fall_events],
            "model_name": GEMMA_WEEKLY_MODEL,
            "raw_counts": {
                "events": len(events),
                "alerts": len(alerts),
                "fall_events": len(fall_events),
                "fall_episodes": len(episodes),
            },
            "score_factors": {
                "resident_safety_decreases": resident_score["decreases"],
                "system_reliability_factors": system_score["factors"],
            },
            "generated_iso_timestamp": generated_at,
        },
    }
    ctx["executive_summary"] = _executive_summary(ctx)
    ctx["recommended_actions"] = _recommended_actions(ctx)
    return ctx


def _format_context_for_gemma(ctx: dict[str, Any]) -> str:
    payload = {
        "date_range": ctx["date_range_human"],
        "raw_fall_detections": ctx["totals"]["raw_fall_like_detections"],
        "clustered_fall_episodes": [
            {
                "episode": item["episode_number"],
                "start": item["start_timestamp"],
                "end": item["end_timestamp"],
                "location": item["location"],
                "raw_detections": item["raw_detection_count"],
                "confidence": item["confidence"],
                "alert_status": item["alert_status"],
                "review_status": item["review_status"],
            }
            for item in ctx["fall_episodes"]
        ],
        "room_summaries": ctx["room_activity"],
        "vitals_summary": ctx["sleep_rest"],
        "nighttime_summary": ctx["night_bathroom"],
        "alert_delivery_summary": ctx["alert_delivery"],
        "system_reliability_summary": ctx["system_reliability_score"],
        "baseline_comparison": ctx["baseline_comparison"],
        "resident_and_sensor_context": ctx.get("care_context") or {},
    }
    return json.dumps(payload, indent=2)


def _call_weekly_gemma(ctx: dict[str, Any]) -> str:
    settings = get_settings()
    if not settings.gemma_enabled:
        raise WeeklyReportGemmaError("Gemma is disabled. Enable GEMMA_ENABLED to generate weekly PDFs.")

    prompt = (
        "Generate caregiver-facing analysis for a weekly safety and wellness PDF. "
        "Use only the structured facts below. Explain the week as a timeline and pattern, not as a raw log. "
        "Avoid diagnosis, medication advice, certainty, and unnecessary repetition of counts. "
        "Output exactly these headings: Caregiver summary, Key observations, Recommended actions, Safety disclaimer. "
        "Caregiver summary must be 1 short paragraph. Key observations must be 3 bullets. "
        "Recommended actions must be 3 bullets with High, Medium, or Low labels. "
        "Safety disclaimer must include 'Not a medical diagnosis.'\n\n"
        f"STRUCTURED FACTS:\n{_format_context_for_gemma(ctx)}"
    )
    payload = {
        "model": GEMMA_WEEKLY_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Gemma, a local caregiver-support assistant for Emergyx Care. "
                    "Use conservative, practical language. Never diagnose."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.1, "num_predict": 900},
    }
    try:
        response = httpx.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/chat",
            json=payload,
            timeout=75.0,
        )
        response.raise_for_status()
    except Exception as exc:
        raise WeeklyReportGemmaError(
            f"Gemma weekly report generation failed for {GEMMA_WEEKLY_MODEL}: {exc}"
        ) from exc
    body = response.json()
    text = ((body.get("message") or {}).get("content") or "").strip()
    lower = text.lower()
    required = ("caregiver summary", "key observations", "recommended actions", "safety disclaimer")
    if len(text.split()) < 40 or any(item not in lower for item in required):
        raise WeeklyReportGemmaError(
            f"Gemma returned an incomplete weekly report with {GEMMA_WEEKLY_MODEL}."
        )
    return text


def _paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    escaped = (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )
    return Paragraph(escaped, style)


def _section(story: list[Any], title: str, body: str, styles: dict[str, ParagraphStyle]) -> None:
    story.append(Paragraph(title, styles["SectionTitle"]))
    story.append(_paragraph(body, styles["BodyText"]))
    story.append(Spacer(1, 0.14 * inch))


def _bullet_lines(lines: list[str]) -> str:
    return "\n".join(f"- {line}" for line in lines)


def _card_table(rows: list[list[Any]], col_widths: list[float] | None = None) -> Table:
    table = Table(rows, colWidths=col_widths)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("LEADING", (0, 0), (-1, -1), 11),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _build_pdf(ctx: dict[str, Any], gemma_text: str) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
    )
    styles = getSampleStyleSheet()
    styles["Title"].fontSize = 19
    styles["Title"].leading = 22
    styles["BodyText"].fontSize = 9.2
    styles["BodyText"].leading = 12.5
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8, leading=10))
    styles.add(
        ParagraphStyle(
            name="SectionTitle",
            parent=styles["Heading2"],
            fontSize=12.5,
            leading=15,
            spaceBefore=8,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BoxBody",
            parent=styles["BodyText"],
            backColor=colors.HexColor("#f8fafc"),
            borderColor=colors.HexColor("#cbd5e1"),
            borderWidth=0.5,
            borderPadding=7,
            leading=12.5,
        )
    )

    story: list[Any] = [
        Paragraph("Emergyx Care Weekly Safety & Wellness Report", styles["Title"]),
        _paragraph(
            f"{ctx['date_range_human']} | Generated {ctx['generated_at_human']} | Model {ctx['model_label']} | {DISCLAIMER}",
            styles["Small"],
        ),
        Spacer(1, 0.16 * inch),
        Paragraph("Executive Summary", styles["SectionTitle"]),
        _paragraph(ctx["executive_summary"], styles["BoxBody"]),
        Spacer(1, 0.16 * inch),
    ]

    resident = ctx["resident_safety_score"]
    system = ctx["system_reliability_score"]
    alert_delivery = ctx["alert_delivery"]
    summary_cards = Table(
        [
            ["Resident Safety", "System Reliability", "Fall Episodes", "Alerts Sent"],
            [
                f"{resident['score']} / 100\n{resident['label']}",
                f"{system['score']} / 100\n{system['label']}",
                f"{ctx['totals']['likely_fall_episodes']}\n{ctx['totals']['raw_fall_like_detections']} raw detections",
                f"{alert_delivery['alerts_sent']} / {alert_delivery['alerts_triggered']}",
            ],
        ],
        colWidths=[1.7 * inch, 1.7 * inch, 1.7 * inch, 1.7 * inch],
    )
    summary_cards.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbeafe")),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#bfdbfe")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dbeafe")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LEADING", (0, 0), (-1, -1), 12),
                ("PADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(summary_cards)
    story.append(Spacer(1, 0.16 * inch))

    _section(
        story,
        "Resident Safety Score",
        f"{resident['score']} / 100 - {resident['label']}\n\nWhy the safety score decreased\n"
        + _bullet_lines(resident["decreases"]),
        styles,
    )
    _section(
        story,
        "System Reliability Score",
        f"{system['score']} / 100 - {system['label']}\n\nProtective/system factors\n"
        + _bullet_lines(system["factors"]),
        styles,
    )

    story.append(Paragraph("Key Incidents", styles["SectionTitle"]))
    if ctx["fall_episodes"]:
        for episode in ctx["fall_episodes"]:
            end_text = (
                f"-{_format_time_only(episode['end_timestamp'])}"
                if episode.get("end_timestamp")
                else ""
            )
            incident = [
                [f"Incident {episode['episode_number']} - Likely fall episode", episode["confidence"]],
                ["Date/time", f"{_format_human_datetime(episode['start_timestamp'])}{end_text}"],
                ["Location", episode["location"]],
                ["Raw detections", str(episode["raw_detection_count"])],
                ["Alert status", episode["alert_status"]],
                ["Review status", episode["review_status"]],
                ["Interpretation", _paragraph(episode["interpretation"], styles["Small"])],
            ]
            story.append(KeepTogether([_card_table(incident, [1.55 * inch, 5.25 * inch]), Spacer(1, 0.1 * inch)]))
    else:
        story.append(_paragraph("No likely-fall incidents were recorded in this weekly window.", styles["BodyText"]))
    story.append(Spacer(1, 0.08 * inch))

    room_lines = []
    for item in ctx["room_activity"][:10]:
        room_lines.append(
            f"{item['room_name']}\n"
            f"- {item['sensor_readings']:,} sensor readings\n"
            f"- {item['raw_fall_like_detections']} raw fall-like detections"
            + (
                f" grouped into {item['likely_fall_episodes']} likely episode(s)"
                if item["likely_fall_episodes"]
                else ""
            )
            + f"\n- Main signal source: {item['main_signal_source']}\n- {item['safety_note']}"
        )
    _section(story, "Room Activity Trends", "\n\n".join(room_lines) or "No room activity was recorded.", styles)

    night = ctx["night_bathroom"]
    nighttime_fall_text = (
        "No nighttime fall episode detected"
        if not night["nighttime_fall_episodes"]
        else f"{night['nighttime_fall_episodes']} nighttime fall episode(s) detected"
    )
    _section(
        story,
        "Nighttime Pattern",
        (
            f"Night window: {night['night_window']}\n"
            f"- {night['night_sensor_readings']:,} nighttime sensor readings recorded\n"
            f"- {night['night_bathroom_events']} bathroom-related events detected\n"
            f"- {'No clear nighttime bathroom trend detected' if not night['night_bathroom_events'] else 'Bathroom-related nighttime activity was detected'}\n"
            f"- {nighttime_fall_text}"
        ),
        styles,
    )

    sleep = ctx["sleep_rest"]
    _section(
        story,
        "Sleep / Rest Signals",
        (
            f"- Heart-rate readings: {sleep['heart_samples']:,}\n"
            f"- Average heart rate: {sleep['heart_avg'] if sleep['heart_avg'] is not None else 'n/a'} bpm\n"
            f"- Respiration readings: {sleep['respiration_samples']:,}\n"
            f"- Average respiration rate: {sleep['respiration_avg'] if sleep['respiration_avg'] is not None else 'n/a'} breaths/min\n"
            f"- Presence detections: {sleep['presence_events']:,}\n"
            f"- Average detected distance: {sleep['distance_avg_cm'] if sleep['distance_avg_cm'] is not None else 'n/a'} cm\n\n"
            "Interpretation:\nBreathing and heart-rate data were successfully collected when readings are present. "
            "Averages alone should not be used for diagnosis. These signals become more valuable when compared "
            "against the resident's personal baseline over multiple weeks."
        ),
        styles,
    )

    _section(
        story,
        "Alert Delivery & Caregiver Response",
        (
            f"- Alerts triggered: {alert_delivery['alerts_triggered']}\n"
            f"- Successfully sent: {alert_delivery['alerts_sent']}\n"
            f"- Failed: {alert_delivery['alerts_failed']}\n"
            f"- Acknowledged: {'n/a' if alert_delivery['acknowledged'] is None else alert_delivery['acknowledged']}\n"
            f"- Unresolved/unreviewed: {alert_delivery['unresolved_unreviewed']}\n"
            f"- {alert_delivery['note']}"
        ),
        styles,
    )

    baseline = ctx["baseline_comparison"]
    if baseline.get("available"):
        baseline_text = (
            f"Compared with {baseline['date_range']}:\n"
            f"- Fall episodes: {baseline['likely_fall_episodes']} previous vs {ctx['totals']['likely_fall_episodes']} current\n"
            f"- Raw fall detections: {baseline['raw_fall_detections']} previous vs {ctx['totals']['raw_fall_like_detections']} current\n"
            f"- Nighttime sensor readings: {baseline['night_sensor_readings']} previous vs {night['night_sensor_readings']} current\n"
            f"- Bathroom activity: {baseline['night_bathroom_events']} previous vs {night['night_bathroom_events']} current\n"
            f"- Daytime activity: {baseline['daytime_sensor_readings']} previous\n"
            f"- Average HR/RR: {baseline['heart_avg'] or 'n/a'} bpm / {baseline['respiration_avg'] or 'n/a'} br/min previous\n"
            f"- Previous system reliability score: {baseline['system_reliability_score']} / 100"
        )
    else:
        baseline_text = baseline["message"]
    _section(story, "Baseline Comparison", baseline_text, styles)

    story.append(Paragraph("Gemma Care Intelligence", styles["SectionTitle"]))
    story.append(_paragraph(gemma_text, styles["BoxBody"]))
    story.append(Spacer(1, 0.14 * inch))

    action_lines = [
        f"{item['priority']}: {item['action']}" for item in ctx["recommended_actions"]
    ]
    story.append(Paragraph("Recommended Caregiver Actions", styles["SectionTitle"]))
    story.append(_paragraph(_bullet_lines(action_lines), styles["BoxBody"]))
    story.append(Spacer(1, 0.14 * inch))
    story.append(_paragraph(DISCLAIMER, styles["Small"]))

    appendix = ctx["technical_appendix"]
    story.append(PageBreak())
    story.append(Paragraph("Technical Appendix", styles["SectionTitle"]))
    appendix_rows = [
        ["Raw room IDs", ", ".join(appendix["raw_room_ids"]) or "none"],
        ["Sensor IDs", ", ".join(appendix["sensor_ids"]) or "none"],
        ["Exact fall timestamps", "\n".join(appendix["raw_fall_timestamps"]) or "none"],
        ["Model name", appendix["model_name"]],
        ["Raw counts", json.dumps(appendix["raw_counts"], indent=2)],
        ["Score factors", json.dumps(appendix["score_factors"], indent=2)],
        ["Generated ISO timestamp", appendix["generated_iso_timestamp"]],
    ]
    story.append(_card_table(appendix_rows, [1.7 * inch, 5.1 * inch]))
    doc.build(story)
    return buffer.getvalue()


def generate_weekly_pdf_report(
    session: Session,
    *,
    mode: str,
    source_filter: str | None,
    start_date: str | None = None,
    end_date: str | None = None,
    night_start_hour: int = 22,
    night_end_hour: int = 6,
) -> WeeklyReportResult:
    ctx = _build_weekly_context(
        session,
        mode=mode,
        source_filter=source_filter,
        start_date=start_date,
        end_date=end_date,
        night_start_hour=night_start_hour,
        night_end_hour=night_end_hour,
    )
    gemma_text = _call_weekly_gemma(ctx)
    pdf_bytes = _build_pdf(ctx, gemma_text)
    filename = f"emergyx-weekly-care-report-{ctx['start_date']}-to-{ctx['end_date']}.pdf"
    return WeeklyReportResult(
        pdf_bytes=pdf_bytes,
        filename=filename,
        model_name=GEMMA_WEEKLY_MODEL,
        used_mock=False,
        context=ctx,
        gemma_text=gemma_text,
    )
