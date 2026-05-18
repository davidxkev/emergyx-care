from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.db import get_session
from app.schemas import LightContextRead, LiveSnapshotResponse, TodayStats
from app.services.events import (
    get_latest_event_by_type,
    get_latest_live_event,
    get_today_stats,
    list_recent_events,
)
from app.services.incidents import get_latest_incident
from app.services.local_rag import build_scope_snapshot
from app.services.utils import age_seconds_now, humanize_age_seconds, parse_mode, staleness_category


router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/today", response_model=TodayStats)
def stats_today(
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
) -> TodayStats:
    _, source_filter = parse_mode(mode)
    return get_today_stats(session, source_filter=source_filter)


@router.get("/live-snapshot", response_model=LiveSnapshotResponse)
def live_snapshot(session: Session = Depends(get_session)) -> LiveSnapshotResponse:
    latest_live = get_latest_live_event(session)
    last_live_age_seconds = age_seconds_now(latest_live.timestamp) if latest_live else None
    snapshot = build_scope_snapshot(session, source_filter="live_sensor")
    light = snapshot.get("latest_light")

    return LiveSnapshotResponse(
        last_live_timestamp=latest_live.timestamp if latest_live else None,
        last_live_age_seconds=last_live_age_seconds,
        last_live_age_human=humanize_age_seconds(last_live_age_seconds),
        last_live_category=staleness_category(last_live_age_seconds),
        light=LightContextRead(**light) if light else None,
    )


@router.get("/mode-snapshot")
def mode_snapshot(
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    normalized_mode, source_filter = parse_mode(mode)
    latest_event = list_recent_events(session, limit=1, source_filter=source_filter)
    latest_item = latest_event[0] if latest_event else None
    age_seconds = age_seconds_now(latest_item.timestamp) if latest_item else None
    snapshot = build_scope_snapshot(session, source_filter=source_filter)
    latest_person = get_latest_event_by_type(session, "person_present", source_filter=source_filter)
    latest_fall = get_latest_event_by_type(session, "fall_detected", source_filter=source_filter)
    incident = get_latest_incident(session, source_filter=source_filter)

    return {
        "mode": normalized_mode,
        "last_event_timestamp": latest_item.timestamp if latest_item else None,
        "last_event_age_seconds": age_seconds,
        "last_event_age_human": humanize_age_seconds(age_seconds),
        "last_event_category": staleness_category(age_seconds),
        "light": snapshot.get("latest_light"),
        "latest_person": {
            "timestamp": latest_person.timestamp,
            "value": latest_person.value,
            "sensor_id": latest_person.sensor_id,
            "room": latest_person.room,
        }
        if latest_person
        else None,
        "latest_fall": {
            "timestamp": latest_fall.timestamp,
            "value": latest_fall.value,
            "sensor_id": latest_fall.sensor_id,
            "room": latest_fall.room,
        }
        if latest_fall
        else None,
        "latest_incident": incident,
        "today_stats": snapshot.get("today_stats"),
    }
