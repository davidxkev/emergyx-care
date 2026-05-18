from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.db import get_session
from app.schemas import TrendsTodayResponse, TrendsWeekResponse
from app.services.trends import get_today_trends, get_week_trends
from app.services.utils import parse_mode


router = APIRouter(prefix="/trends", tags=["trends"])


@router.get("/today", response_model=TrendsTodayResponse)
def trends_today(
    mode: str = Query("demo", description="demo or live"),
    night_start_hour: int | None = Query(default=None, ge=0, le=23),
    night_end_hour: int | None = Query(default=None, ge=0, le=23),
    session: Session = Depends(get_session),
) -> TrendsTodayResponse:
    normalized_mode, source_filter = parse_mode(mode)
    payload = get_today_trends(
        session,
        mode=normalized_mode,
        source_filter=source_filter,
        night_start_hour=night_start_hour,
        night_end_hour=night_end_hour,
    )
    return TrendsTodayResponse.model_validate(payload)


@router.get("/week", response_model=TrendsWeekResponse)
def trends_week(
    mode: str = Query("demo", description="demo or live"),
    night_start_hour: int | None = Query(default=None, ge=0, le=23),
    night_end_hour: int | None = Query(default=None, ge=0, le=23),
    session: Session = Depends(get_session),
) -> TrendsWeekResponse:
    normalized_mode, source_filter = parse_mode(mode)
    payload = get_week_trends(
        session,
        mode=normalized_mode,
        source_filter=source_filter,
        night_start_hour=night_start_hour,
        night_end_hour=night_end_hour,
    )
    return TrendsWeekResponse.model_validate(payload)

