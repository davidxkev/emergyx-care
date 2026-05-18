from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings


LOGGER = logging.getLogger(__name__)


def send_telegram_message(
    text: str,
    *,
    chat_id: str | None = None,
    reply_markup: dict[str, Any] | None = None,
) -> bool:
    settings = get_settings()
    target_chat_id = chat_id or settings.telegram_chat_id
    if settings.mock_alert_channel:
        LOGGER.info("Mock alert channel enabled; captured Telegram message locally: %s", text[:240])
        return True
    if not settings.telegram_bot_token or not target_chat_id:
        LOGGER.info("Telegram not configured; skipping send.")
        return False

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": target_chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    try:
        response = httpx.post(url, json=payload, timeout=10.0)
        response.raise_for_status()
        body = response.json()
        if not body.get("ok", False):
            LOGGER.warning("Telegram API returned a non-ok response: %s", body)
            return False
        return True
    except Exception as exc:
        LOGGER.warning("Telegram send failed: %s", exc)
        return False


def send_telegram_document(
    document: bytes,
    *,
    filename: str,
    caption: str,
    chat_id: str | None = None,
) -> bool:
    settings = get_settings()
    target_chat_id = chat_id or settings.telegram_chat_id
    if settings.mock_alert_channel:
        LOGGER.info(
            "Mock alert channel enabled; captured Telegram document locally: filename=%s caption=%s",
            filename,
            caption[:240],
        )
        return True
    if not settings.telegram_bot_token or not target_chat_id:
        LOGGER.info("Telegram not configured; skipping document send.")
        return False

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendDocument"
    data = {
        "chat_id": target_chat_id,
        "caption": caption,
    }
    files = {
        "document": (filename, document, "application/pdf"),
    }
    try:
        response = httpx.post(url, data=data, files=files, timeout=30.0)
        response.raise_for_status()
        body = response.json()
        if not body.get("ok", False):
            LOGGER.warning("Telegram document API returned a non-ok response: %s", body)
            return False
        return True
    except Exception as exc:
        LOGGER.warning("Telegram document send failed: %s", exc)
        return False
