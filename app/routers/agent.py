from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.db import get_session
from app.schemas import (
    AgentTrendAnalysisResponse,
    AgentExplainResponse,
    CaregiverAskRequest,
    CaregiverAskResponse,
)
from app.services.gemma_agent import (
    analyze_trends,
    answer_caregiver_question,
    explain_incident,
    gemma_status_snapshot,
)
from app.services.utils import parse_mode


router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/explain-latest", response_model=AgentExplainResponse)
def explain_latest(
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
) -> AgentExplainResponse:
    _, source_filter = parse_mode(mode)
    result = explain_incident(session, source_filter=source_filter)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("text", "No fall event found"))
    return AgentExplainResponse(
        success=result["success"],
        used_mock=result["used_mock"],
        model_name=result["model_name"],
        explanation=result.get("text", ""),
        related_event_id=result.get("related_event_id"),
        tools_used=result.get("tools_used", []),
        incident=result.get("incident"),
    )


@router.post("/explain/{event_id}", response_model=AgentExplainResponse)
def explain_specific(
    event_id: int,
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
) -> AgentExplainResponse:
    _, source_filter = parse_mode(mode)
    result = explain_incident(session, event_id=event_id, source_filter=source_filter)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("text", "Event not found"))
    return AgentExplainResponse(
        success=result["success"],
        used_mock=result["used_mock"],
        model_name=result["model_name"],
        explanation=result.get("text", ""),
        related_event_id=result.get("related_event_id"),
        tools_used=result.get("tools_used", []),
        incident=result.get("incident"),
    )


@router.post("/ask", response_model=CaregiverAskResponse)
def ask(
    payload: CaregiverAskRequest,
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
) -> CaregiverAskResponse:
    if not payload.question or not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question is required")
    _, source_filter = parse_mode(mode)
    result = answer_caregiver_question(
        session, question=payload.question, source_filter=source_filter
    )
    return CaregiverAskResponse(
        success=result["success"],
        used_mock=result["used_mock"],
        model_name=result["model_name"],
        answer=result.get("text", ""),
        question=payload.question,
        tools_used=result.get("tools_used", []),
    )


@router.get("/status")
def status() -> dict[str, object]:
    return gemma_status_snapshot()


@router.post("/analyze-trends", response_model=AgentTrendAnalysisResponse)
def analyze_trends_route(
    mode: str = Query("demo", description="demo or live"),
    night_start_hour: int | None = Query(default=None, ge=0, le=23),
    night_end_hour: int | None = Query(default=None, ge=0, le=23),
    session: Session = Depends(get_session),
) -> AgentTrendAnalysisResponse:
    normalized_mode, source_filter = parse_mode(mode)
    result = analyze_trends(
        session,
        mode=normalized_mode,
        source_filter=source_filter,
        night_start_hour=night_start_hour,
        night_end_hour=night_end_hour,
    )
    return AgentTrendAnalysisResponse(
        success=result["success"],
        used_mock=result["used_mock"],
        model_name=result["model_name"],
        analysis=result.get("text", ""),
        tools_used=result.get("tools_used", []),
        trends=result.get("trends"),
    )
