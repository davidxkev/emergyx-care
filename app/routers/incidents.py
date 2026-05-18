from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.db import get_session
from app.schemas import IncidentResponse
from app.services.incidents import (
    get_incident_context,
    get_latest_incident,
    get_today_incidents,
)
from app.services.utils import parse_mode


router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("/latest", response_model=IncidentResponse)
def latest_incident(
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
) -> IncidentResponse:
    _, source_filter = parse_mode(mode)
    incident = get_latest_incident(session, source_filter=source_filter)
    return IncidentResponse(incident=incident, found=incident is not None)


@router.get("/today", response_model=list[dict])
def today_incidents(
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
) -> list[dict]:
    _, source_filter = parse_mode(mode)
    return get_today_incidents(session, source_filter=source_filter)


@router.get("/{event_id}", response_model=IncidentResponse)
def incident_by_event(
    event_id: int,
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
) -> IncidentResponse:
    _, source_filter = parse_mode(mode)
    incident = get_incident_context(session, event_id, source_filter=source_filter)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"No event with id={event_id}")
    return IncidentResponse(incident=incident, found=True)
