from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session, init_db
from app.routers import (
    agent,
    alerts,
    chat,
    demo,
    events,
    incidents,
    reports,
    settings as settings_router,
    stats,
    trends,
)
from app.services.chat_threads import get_thread_detail, list_threads
from app.services.events import (
    get_latest_event_by_type,
    get_latest_light_context,
    get_today_stats,
    list_alerts_for_date,
    list_events_for_date,
    list_recent_alerts,
    list_recent_events,
)
from app.services.gemma_agent import gemma_status_snapshot
from app.services.incidents import get_incidents_for_date, get_latest_incident, get_today_incidents
from app.services.local_rag import build_scope_snapshot
from app.services.reports import list_reports_for_mode
from app.services.report_scheduler import start_report_scheduler, stop_report_scheduler
from app.services.telegram_bot import start_telegram_command_bot, stop_telegram_command_bot
from app.services.utils import (
    age_seconds_now,
    current_date,
    event_type_label,
    fall_state_label,
    humanize_age_seconds,
    parse_mode,
    person_state_label,
    severity_label,
    severity_tone,
    source_label,
    source_tone,
    staleness_category,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _mode_badge(mode: str) -> dict[str, str]:
    if mode == "live":
        return {
            "label": "LIVE",
            "title": "Real sensor data only",
            "description": "Showing only live_sensor events from the current home hub.",
            "tone": "live",
        }
    return {
        "label": "DEMO",
        "title": "Simulated data only",
        "description": "Showing demo runs and baseline simulation data only.",
        "tone": "demo",
    }


def _safety_state(
    *,
    latest_fall_value: str | None,
    latest_incident: dict[str, object] | None,
) -> dict[str, str]:
    if latest_fall_value == "true":
        return {
            "label": "Attention needed",
            "detail": "A likely fall is still active in the local care timeline.",
            "tone": "urgent",
        }
    if latest_incident and str((latest_incident.get("event") or {}).get("timestamp", "")).startswith(current_date()):
        return {
            "label": "Stable",
            "detail": "A likely fall was logged earlier today and the safety event has cleared.",
            "tone": "success",
        }
    return {
        "label": "Stable",
        "detail": "No active likely-fall condition is currently present.",
        "tone": "success",
    }


def _latest_incident_summary(latest_incident: dict[str, object] | None) -> dict[str, str]:
    if not latest_incident:
        return {
            "label": "No urgent incident",
            "detail": "No likely-fall incident is recorded in this mode right now.",
            "tone": "neutral",
        }
    event = latest_incident.get("event") or {}
    timestamp = str(event.get("timestamp") or "")
    time_only = timestamp.split("T")[-1][:5] if "T" in timestamp else timestamp or "recently"
    room = str(latest_incident.get("room") or "the room")
    return {
        "label": f"Likely fall at {time_only}",
        "detail": f"{room} • {source_label(latest_incident.get('source'))}",
        "tone": "urgent",
    }


def _alert_status(latest_alert, telegram_configured: bool) -> dict[str, str]:
    if not telegram_configured:
        return {
            "label": "Not configured",
            "detail": "Telegram is not configured for remote caregiver alerts.",
            "tone": "warning",
        }
    if latest_alert is None:
        return {
            "label": "Ready",
            "detail": "Rule-based urgent alerts can be sent immediately.",
            "tone": "success",
        }
    if latest_alert.sent_success:
        return {
            "label": "Sent immediately",
            "detail": f"{severity_label(latest_alert.severity)} alert via {latest_alert.sent_channel}.",
            "tone": severity_tone(latest_alert.severity),
        }
    return {
        "label": "Send failed",
        "detail": "The latest alert was logged locally, but remote delivery did not succeed.",
        "tone": "warning",
    }


def _timeline_summary(
    *,
    today_stats,
    alerts_today_count: int,
    latest_light: dict[str, object] | None,
    latest_source: str | None,
    mode: str,
) -> list[dict[str, str]]:
    return [
        {"label": "Events today", "value": str(today_stats.total_events_today)},
        {"label": "Likely falls today", "value": str(today_stats.fall_events_today)},
        {"label": "Alerts sent", "value": str(alerts_today_count)},
        {
            "label": "Light context",
            "value": str((latest_light or {}).get("category", "No reading")).replace("_", " ").title(),
        },
        {
            "label": "Current source",
            "value": source_label(latest_source) if latest_source else ("Live sensor" if mode == "live" else "Demo run"),
        },
    ]


def _dashboard_stat_cards(
    *,
    hero_cards: dict[str, dict[str, str]],
    today_stats,
    latest_light: dict[str, object] | None,
    latest_alert,
) -> list[dict[str, object]]:
    light_value = (
        f"{float(latest_light['lux']):.1f} lux"
        if latest_light and latest_light.get("lux") is not None
        else "No reading"
    )
    alert_channel = getattr(latest_alert, "sent_channel", None) or "Telegram"
    return [
        {
            "title": "Current safety",
            "value": hero_cards["safety"]["label"],
            "detail": hero_cards["safety"]["detail"],
            "change": "Attention" if hero_cards["safety"]["tone"] == "urgent" else "Stable",
            "change_tone": hero_cards["safety"]["tone"],
            "icon": "✓",
            "progress": 36 if hero_cards["safety"]["tone"] == "urgent" else 92,
            "color": "teal",
        },
        {
            "title": "Local incidents",
            "value": str(today_stats.fall_events_today),
            "detail": "Likely-fall events logged today",
            "change": "Today",
            "change_tone": "urgent" if today_stats.fall_events_today else "neutral",
            "icon": "!",
            "progress": min(100, 24 + today_stats.fall_events_today * 18),
            "color": "blue",
        },
        {
            "title": "Person presence",
            "value": hero_cards["presence"]["label"],
            "detail": light_value,
            "change": "Current room state",
            "change_tone": hero_cards["presence"]["tone"],
            "icon": "◌",
            "progress": 88 if hero_cards["presence"]["tone"] == "success" else 42,
            "color": "green",
        },
        {
            "title": "Caregiver alerts",
            "value": hero_cards["alert"]["label"],
            "detail": hero_cards["alert"]["detail"],
            "change": alert_channel,
            "change_tone": hero_cards["alert"]["tone"],
            "icon": "↗",
            "progress": 100 if hero_cards["alert"]["tone"] == "success" else 58,
            "color": "violet",
        },
    ]


def _overview_totals(series: list[dict[str, object]]) -> list[dict[str, str]]:
    total_events = sum(int(item["events"]) for item in series)
    total_alerts = sum(int(item["alerts"]) for item in series)
    total_falls = sum(int(item["falls"]) for item in series)
    average = round(total_events / len(series), 1) if series else 0
    return [
        {"label": "Total events", "value": str(total_events), "tone": "blue"},
        {"label": "Likely falls", "value": str(total_falls), "tone": "urgent"},
        {"label": "Average / day", "value": str(average), "tone": "violet"},
        {"label": "Alerts sent", "value": str(total_alerts), "tone": "warning"},
    ]


def _chart_payloads(
    *,
    overview_series: list[dict[str, object]],
    recent_events,
) -> dict[str, object]:
    categories = [str(item["label"]) for item in overview_series]
    events = [int(item["events"]) for item in overview_series]
    alerts = [int(item["alerts"]) for item in overview_series]
    falls = [int(item["falls"]) for item in overview_series]

    activity_mix = {
        "Presence": 0,
        "Likely falls": 0,
        "Light context": 0,
    }
    for event in recent_events[:30]:
        if event.event_type == "person_present":
            activity_mix["Presence"] += 1
        elif event.event_type == "fall_detected" and event.value == "true":
            activity_mix["Likely falls"] += 1
        elif event.event_type == "illuminance":
            activity_mix["Light context"] += 1

    if not any(activity_mix.values()):
        activity_mix = {
            "Presence": 1,
            "Likely falls": 0,
            "Light context": 0,
        }

    return {
        "main": {
            "categories": categories,
            "series": [
                {"name": "Events", "data": events},
                {"name": "Alerts", "data": alerts, "color": "#f472b6"},
            ],
            "valueFormat": {"suffix": ""},
            "axisFormat": {"suffix": ""},
        },
        "small": {
            "label": "Alerts",
            "series": [
                {
                    "name": "Alerts",
                    "data": [{"x": categories[index], "y": alerts[index]} for index in range(len(categories))],
                }
            ],
            "valueFormat": {"suffix": ""},
        },
        "spark": {
            "label": "Likely falls",
            "series": [
                {
                    "name": "Likely falls",
                    "data": [{"x": categories[index], "y": falls[index]} for index in range(len(categories))],
                }
            ],
            "valueFormat": {"suffix": ""},
        },
        "mix": {
            "labels": list(activity_mix.keys()),
            "series": list(activity_mix.values()),
            "valueFormat": {"suffix": ""},
        },
    }


def _system_status_items(*, gemma_status: dict[str, object], sensor_status: str, telegram_configured: bool, mode_snapshot: dict[str, object]) -> list[dict[str, object]]:
    freshness = str(mode_snapshot.get("last_event_category") or "neutral")
    freshness_percentage = 96 if freshness in {"fresh", "recent"} else 62 if freshness == "warn" else 38
    return [
        {
            "label": "Sensor stream",
            "status": "Online" if sensor_status == "Configured" else "Offline",
            "tone": "success" if sensor_status == "Configured" else "warning",
            "percentage": 98 if sensor_status == "Configured" else 22,
        },
        {
            "label": "Gemma agent",
            "status": "Online" if gemma_status.get("status") == "online" else "Fallback",
            "tone": "success" if gemma_status.get("status") == "online" else "warning",
            "percentage": 100 if gemma_status.get("status") == "online" else 58,
        },
        {
            "label": "Alert delivery",
            "status": "Configured" if telegram_configured else "Local only",
            "tone": "success" if telegram_configured else "warning",
            "percentage": 94 if telegram_configured else 40,
        },
        {
            "label": "Freshness",
            "status": str(mode_snapshot.get("last_event_age_human") or "No data"),
            "tone": "success" if freshness in {"fresh", "recent"} else "warning" if freshness == "warn" else "urgent",
            "percentage": freshness_percentage,
        },
    ]


def _last_n_dates(days: int = 7) -> list[str]:
    end = date.fromisoformat(current_date())
    return [(end - timedelta(days=offset)).isoformat() for offset in reversed(range(days))]


def _overview_series(
    session: Session,
    *,
    source_filter: str | None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for date_str in _last_n_dates(7):
        events = list_events_for_date(session, date_str, source_filter=source_filter)
        alerts = list_alerts_for_date(session, date_str, source_filter=source_filter)
        incidents = get_incidents_for_date(session, date_str, source_filter=source_filter)
        fall_count = sum(
            1
            for event in events
            if event.event_type == "fall_detected" and event.value == "true"
        )
        day_value = date.fromisoformat(date_str)
        rows.append(
            {
                "date": date_str,
                "label": day_value.strftime("%a"),
                "day": day_value.strftime("%-d"),
                "events": len(events),
                "alerts": len(alerts),
                "falls": fall_count,
                "incidents": len(incidents),
            }
        )

    max_events = max((int(row["events"]) for row in rows), default=0)
    max_alerts = max((int(row["alerts"]) for row in rows), default=0)
    for row in rows:
        event_value = int(row["events"])
        alert_value = int(row["alerts"])
        row["event_height"] = 14 if max_events == 0 else max(14, round((event_value / max_events) * 100))
        row["alert_height"] = 10 if max_alerts == 0 else max(10, round((alert_value / max_alerts) * 100))
    return rows


def _recent_activity(
    *,
    recent_events,
    recent_alerts,
    mode: str,
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    fallback_source = "Live" if mode == "live" else "Demo"

    for alert in recent_alerts[:6]:
        items.append(
            {
                "timestamp": alert.timestamp,
                "title": "Urgent caregiver alert sent" if alert.sent_success else "Urgent caregiver alert logged",
                "detail": f"{severity_label(alert.severity)} via {alert.sent_channel or 'local log'}",
                "tone": severity_tone(alert.severity),
                "source_label": fallback_source,
                "source_tone": "live" if mode == "live" else "demo",
                "kind": "Alert",
            }
        )

    for event in recent_events[:10]:
        if event.event_type == "person_present":
            title = "Person detected" if event.value == "true" else "No person detected"
            tone = "success" if event.value == "true" else "neutral"
            detail = f"{event.room} • Presence update"
        elif event.event_type == "fall_detected":
            title = "Likely fall detected" if event.value == "true" else "Fall state cleared"
            tone = "urgent" if event.value == "true" else "success"
            detail = f"{event.room} • Safety event"
        elif event.event_type == "illuminance":
            title = "Light context updated"
            tone = "neutral"
            detail = f"{event.room} • {event.value} lux"
        else:
            title = event_type_label(event.event_type)
            tone = "neutral"
            detail = f"{event.room} • Local care timeline"

        items.append(
            {
                "timestamp": event.timestamp,
                "title": title,
                "detail": detail,
                "tone": tone,
                "source_label": source_label(event.source),
                "source_tone": source_tone(event.source),
                "kind": "Timeline",
            }
        )

    items.sort(key=lambda item: item["timestamp"], reverse=True)
    return items[:8]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    LOGGER.info("Database initialized")
    start_report_scheduler()
    start_telegram_command_bot()
    try:
        yield
    finally:
        stop_telegram_command_bot()
        stop_report_scheduler()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.3.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"http://(192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+):3000",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(events.router)
app.include_router(alerts.router)
app.include_router(stats.router)
app.include_router(trends.router)
app.include_router(agent.router)
app.include_router(chat.router)
app.include_router(demo.router)
app.include_router(incidents.router)
app.include_router(reports.router)
app.include_router(settings_router.router)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/health")
def health() -> dict[str, object]:
    current_settings = get_settings()
    sensors = current_settings.configured_fda2_sensors()
    return {
        "status": "ok",
        "app": current_settings.app_name,
        "version": "0.3.0",
        "gemma": gemma_status_snapshot(),
        "fda2_sensors": [
            {
                "sensor_id": sensor.sensor_id,
                "room": sensor.room,
                "host": sensor.host,
                "sensor_family": sensor.sensor_family,
                "rgb_light_configured": sensor.rgb_light_key is not None,
            }
            for sensor in sensors
        ],
        "telegram_configured": bool(current_settings.telegram_bot_token and current_settings.telegram_chat_id),
        "telegram_gemma_explanations": current_settings.telegram_send_gemma_explanations,
        "dashboard_refresh_seconds": current_settings.dashboard_refresh_seconds,
        "environment": current_settings.app_env,
    }


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    mode: str = Query("demo", description="demo or live"),
    thread_id: int | None = Query(None),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    normalized_mode, source_filter = parse_mode(mode)
    today_stats = get_today_stats(session, source_filter=source_filter)
    snapshot = build_scope_snapshot(session, source_filter=source_filter)
    gemma_status = gemma_status_snapshot()
    threads = list_threads(session, mode=normalized_mode, limit=24)
    selected_thread_id = thread_id or (threads[0]["id"] if threads else None)
    active_thread = (
        get_thread_detail(session, thread_id=selected_thread_id, mode=normalized_mode)
        if selected_thread_id is not None
        else None
    )
    sensor_status = "Configured" if settings.fda2_sensor_ip else "Not configured"
    telegram_configured = bool(settings.telegram_bot_token and settings.telegram_chat_id)
    recent_events = list_recent_events(session, limit=12, source_filter=source_filter)
    recent_alerts = list_recent_alerts(session, limit=8, source_filter=source_filter)
    latest_alert = recent_alerts[0] if recent_alerts else None
    today_alerts = list_alerts_for_date(session, current_date(), source_filter=source_filter)
    reports_for_mode = list_reports_for_mode(session, mode=normalized_mode, limit=6)
    latest_mode_event = recent_events[:1]
    latest_item = latest_mode_event[0] if latest_mode_event else None
    latest_age_seconds = age_seconds_now(latest_item.timestamp) if latest_item else None
    mode_snapshot = {
        "last_event_timestamp": latest_item.timestamp if latest_item else None,
        "last_event_age_seconds": latest_age_seconds,
        "last_event_age_human": humanize_age_seconds(latest_age_seconds),
        "last_event_category": staleness_category(latest_age_seconds),
    }
    latest_person = snapshot.get("latest_person")
    latest_fall = snapshot.get("latest_fall")
    latest_light = snapshot.get("latest_light")
    latest_incident = snapshot.get("latest_incident")
    safety_state = _safety_state(
        latest_fall_value=(latest_fall or {}).get("value"),
        latest_incident=latest_incident,
    )
    hero_cards = {
        "safety": safety_state,
        "incident": _latest_incident_summary(latest_incident),
        "presence": {
            "label": person_state_label((latest_person or {}).get("value")),
            "detail": (latest_person or {}).get("room") or "No person presence event yet.",
            "tone": "success" if (latest_person or {}).get("value") == "true" else "neutral",
        },
        "alert": _alert_status(latest_alert, telegram_configured),
    }
    history_threads = threads[:8]
    overview_series = _overview_series(session, source_filter=source_filter)
    overview_totals = _overview_totals(overview_series)
    activity_items = _recent_activity(
        recent_events=recent_events,
        recent_alerts=recent_alerts,
        mode=normalized_mode,
    )
    stat_cards = _dashboard_stat_cards(
        hero_cards=hero_cards,
        today_stats=today_stats,
        latest_light=latest_light,
        latest_alert=latest_alert,
    )
    system_status_items = _system_status_items(
        gemma_status=gemma_status,
        sensor_status=sensor_status,
        telegram_configured=telegram_configured,
        mode_snapshot=mode_snapshot,
    )
    chart_payloads = _chart_payloads(
        overview_series=overview_series,
        recent_events=recent_events,
    )

    context = {
        "settings": settings,
        "mode": normalized_mode,
        "is_live_mode": normalized_mode == "live",
        "active_nav": "overview",
        "threads": history_threads,
        "active_thread": active_thread,
        "snapshot": snapshot,
        "mode_snapshot": mode_snapshot,
        "gemma_status": gemma_status,
        "telegram_configured": telegram_configured,
        "sensor_status": sensor_status,
        "mode_badge": _mode_badge(normalized_mode),
        "hero_cards": hero_cards,
        "latest_alert": latest_alert,
        "latest_report": reports_for_mode[0] if reports_for_mode else None,
        "overview_series": overview_series,
        "overview_totals": overview_totals,
        "activity_items": activity_items,
        "history_count": len(threads),
        "stat_cards": stat_cards,
        "system_status_items": system_status_items,
        "chart_payloads": chart_payloads,
        "table_rows": [
            {
                "timestamp": event.timestamp,
                "label": event_type_label(event.event_type),
                "value": (
                    person_state_label(event.value)
                    if event.event_type == "person_present"
                    else fall_state_label(event.value)
                    if event.event_type == "fall_detected"
                    else event.value
                ),
                "room": event.room,
                "source_label": source_label(event.source),
                "source_tone": source_tone(event.source),
            }
            for event in recent_events[:6]
        ],
        "timeline_summary": _timeline_summary(
            today_stats=today_stats,
            alerts_today_count=len(today_alerts),
            latest_light=latest_light,
            latest_source=getattr(latest_item, "source", None),
            mode=normalized_mode,
        ),
        "quick_prompts": [
            "What happened today?",
            "Why was I alerted?",
            "Was the room dark?",
            "Summarize today for my sister.",
            "Any likely falls this week?",
            "Generate today's report.",
        ],
    }
    return templates.TemplateResponse(request, "dashboard.html", context)


@app.get("/dashboard/details", response_class=HTMLResponse)
def dashboard_details(
    request: Request,
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    normalized_mode, source_filter = parse_mode(mode)
    today_stats = get_today_stats(session, source_filter=source_filter)
    latest_person = get_latest_event_by_type(session, "person_present", source_filter=source_filter)
    latest_fall = get_latest_event_by_type(session, "fall_detected", source_filter=source_filter)
    latest_light = get_latest_light_context(session, source_filter=source_filter)
    latest_incident = get_latest_incident(session, source_filter=source_filter)
    today_incidents = get_today_incidents(session, source_filter=source_filter)
    recent_events = list_recent_events(session, limit=30, source_filter=source_filter)
    recent_alerts = list_recent_alerts(session, limit=20, source_filter=source_filter)
    reports_for_mode = list_reports_for_mode(session, mode=normalized_mode, limit=12)
    latest_mode_event = list_recent_events(session, limit=1, source_filter=source_filter)
    latest_item = latest_mode_event[0] if latest_mode_event else None
    latest_age_seconds = age_seconds_now(latest_item.timestamp) if latest_item else None
    latest_alert = recent_alerts[0] if recent_alerts else None
    today_alerts = list_alerts_for_date(session, current_date(), source_filter=source_filter)
    overview_series = _overview_series(session, source_filter=source_filter)
    chart_payloads = _chart_payloads(
        overview_series=overview_series,
        recent_events=recent_events,
    )

    context = {
        "settings": settings,
        "mode": normalized_mode,
        "is_live_mode": normalized_mode == "live",
        "active_nav": "details",
        "today_stats": today_stats,
        "latest_person": latest_person,
        "latest_fall": latest_fall,
        "latest_light": latest_light,
        "latest_incident": latest_incident,
        "today_incidents": today_incidents,
        "recent_events": recent_events,
        "recent_alerts": recent_alerts,
        "reports": reports_for_mode,
        "latest_report": reports_for_mode[0] if reports_for_mode else None,
        "gemma_status": gemma_status_snapshot(),
        "telegram_configured": bool(settings.telegram_bot_token and settings.telegram_chat_id),
        "sensor_status": "Configured" if settings.fda2_sensor_ip else "Not configured",
        "mode_badge": _mode_badge(normalized_mode),
        "latest_alert": latest_alert,
        "overview_series": overview_series,
        "chart_payloads": chart_payloads,
        "timeline_summary": _timeline_summary(
            today_stats=today_stats,
            alerts_today_count=len(today_alerts),
            latest_light=latest_light,
            latest_source=getattr(latest_item, "source", None),
            mode=normalized_mode,
        ),
        "suggested_questions": [
            "What happened today?",
            "Were there any likely falls today?",
            "What is the current room status?",
            "What should a caregiver know right now?",
        ],
        "event_rows": [
            {
                "timestamp": event.timestamp,
                "label": event_type_label(event.event_type),
                "value": (
                    person_state_label(event.value)
                    if event.event_type == "person_present"
                    else fall_state_label(event.value)
                    if event.event_type == "fall_detected"
                    else event.value
                ),
                "room": event.room,
                "source_label": source_label(event.source),
                "source_tone": source_tone(event.source),
            }
            for event in recent_events
        ],
        "alert_rows": [
            {
                "timestamp": alert.timestamp,
                "label": alert.alert_type.replace("_", " ").title(),
                "severity_label": severity_label(alert.severity),
                "severity_tone": severity_tone(alert.severity),
                "channel": alert.sent_channel,
                "sent_success": alert.sent_success,
            }
            for alert in recent_alerts
        ],
        "mode_snapshot": {
            "last_event_timestamp": latest_item.timestamp if latest_item else None,
            "last_event_age_seconds": latest_age_seconds,
            "last_event_age_human": humanize_age_seconds(latest_age_seconds),
            "last_event_category": staleness_category(latest_age_seconds),
        },
    }
    return templates.TemplateResponse(request, "dashboard_details.html", context)
