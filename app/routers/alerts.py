from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.db import get_session
from app.schemas import AlertRead, TelegramTestResponse
from app.services.events import list_recent_alerts
from app.services.telegram import send_telegram_message
from app.services.utils import current_timestamp, parse_mode


router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertRead])
def get_alerts(
    limit: int = 20,
    live_only: bool = False,
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
) -> list[AlertRead]:
    safe_limit = max(1, min(limit, 200))
    _, source_filter = parse_mode(mode)
    return list_recent_alerts(
        session,
        limit=safe_limit,
        live_only=live_only,
        source_filter=source_filter,
    )


@router.post("/test-telegram", response_model=TelegramTestResponse)
def test_telegram() -> TelegramTestResponse:
    message = (
        "Emergyx Care Telegram test\n\n"
        f"Sent at {current_timestamp()}.\n\n"
        "This is a prototype caregiver-support channel. Not a medical device."
    )
    success = send_telegram_message(message)
    detail = (
        "Telegram test message sent."
        if success
        else "Telegram not configured or send failed. Check environment variables and logs."
    )
    return TelegramTestResponse(success=success, message=detail)
