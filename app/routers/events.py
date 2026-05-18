from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.schemas import EventCreate, EventRead, SimulateFallRequest
from app.services.events import (
    create_event,
    list_latest_events_by_sensor_type,
    list_recent_events,
)
from app.services.utils import parse_mode


router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventRead])
def get_events(
    limit: int = 50,
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
) -> list[EventRead]:
    safe_limit = max(1, min(limit, 200))
    _, source_filter = parse_mode(mode)
    return list_recent_events(session, limit=safe_limit, source_filter=source_filter)


@router.get("/latest-by-sensor", response_model=list[EventRead])
def get_latest_events_by_sensor(
    mode: str = Query("live", description="demo or live"),
    scan_limit: int = Query(5000, ge=100, le=50000),
    session: Session = Depends(get_session),
) -> list[EventRead]:
    _, source_filter = parse_mode(mode)
    return list_latest_events_by_sensor_type(
        session,
        source_filter=source_filter,
        scan_limit=scan_limit,
    )


@router.post("", response_model=EventRead)
def post_event(payload: EventCreate, session: Session = Depends(get_session)) -> EventRead:
    event = create_event(
        session,
        sensor_id=payload.sensor_id,
        room=payload.room,
        event_type=payload.event_type,
        value=payload.value,
        source=payload.source,
        metadata_json=payload.metadata_json,
        trigger_alerts=True,
    )
    return event


@router.post("/simulate-fall", response_model=EventRead)
def simulate_fall(
    payload: SimulateFallRequest | None = None,
    session: Session = Depends(get_session),
) -> EventRead:
    settings = get_settings()
    request = payload or SimulateFallRequest()
    event = create_event(
        session,
        sensor_id=request.sensor_id or settings.fda2_sensor_id,
        room=request.room or settings.fda2_room,
        event_type="fall_detected",
        value=True,
        source="simulated",
        metadata_json=request.metadata_json or {"simulation": "manual_trigger"},
        trigger_alerts=True,
    )
    if event is None:
        raise HTTPException(status_code=500, detail="Failed to simulate fall event")
    return event
