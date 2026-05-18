from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any

from sqlmodel import Session

from app.config import load_runtime_report_schedule, save_runtime_report_schedule
from app.db import engine
from app.services.gemma_findings import run_gemma_pattern_scan
from app.services.gemma_agent import generate_daily_report
from app.services.reports import save_weekly_report
from app.services.telegram import send_telegram_document, send_telegram_message
from app.services.utils import LIVE_SENSOR_SOURCE, current_timestamp
from app.services.weekly_reports import generate_weekly_pdf_report


LOGGER = logging.getLogger(__name__)
DEFAULT_SCHEDULE: dict[str, Any] = {
    "daily_enabled": False,
    "daily_time": "20:00",
    "daily_send_telegram": False,
    "weekly_enabled": False,
    "weekly_day": 0,
    "weekly_time": "09:00",
    "weekly_send_telegram": False,
    "pattern_enabled": False,
    "pattern_interval_minutes": 60,
    "pattern_send_telegram": False,
}

_stop_event = threading.Event()
_thread: threading.Thread | None = None
_job_lock = threading.Lock()


def _valid_time(value: object, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError:
        return fallback
    return value


def report_schedule_settings() -> dict[str, Any]:
    stored = load_runtime_report_schedule()
    settings = {
        **DEFAULT_SCHEDULE,
        **stored,
        "daily_time": _valid_time(stored.get("daily_time"), DEFAULT_SCHEDULE["daily_time"]),
        "weekly_time": _valid_time(stored.get("weekly_time"), DEFAULT_SCHEDULE["weekly_time"]),
        "weekly_day": min(6, max(0, int(stored.get("weekly_day", DEFAULT_SCHEDULE["weekly_day"])))),
        "pattern_interval_minutes": min(
            1440,
            max(15, int(stored.get("pattern_interval_minutes", DEFAULT_SCHEDULE["pattern_interval_minutes"]))),
        ),
    }
    return settings


def save_report_schedule_settings(update: dict[str, Any]) -> dict[str, Any]:
    current = report_schedule_settings()
    next_settings = {
        **current,
        "daily_enabled": bool(update.get("daily_enabled")),
        "daily_time": _valid_time(update.get("daily_time"), current["daily_time"]),
        "daily_send_telegram": bool(update.get("daily_send_telegram")),
        "weekly_enabled": bool(update.get("weekly_enabled")),
        "weekly_day": min(6, max(0, int(update.get("weekly_day", current["weekly_day"])))),
        "weekly_time": _valid_time(update.get("weekly_time"), current["weekly_time"]),
        "weekly_send_telegram": bool(update.get("weekly_send_telegram")),
        "pattern_enabled": bool(update.get("pattern_enabled", current["pattern_enabled"])),
        "pattern_interval_minutes": min(
            1440,
            max(15, int(update.get("pattern_interval_minutes", current["pattern_interval_minutes"]))),
        ),
        "pattern_send_telegram": bool(update.get("pattern_send_telegram", current["pattern_send_telegram"])),
    }
    save_runtime_report_schedule(next_settings)
    return report_schedule_settings()


def scheduler_running() -> bool:
    return bool(_thread and _thread.is_alive())


def _record_schedule_state(**changes: Any) -> None:
    save_runtime_report_schedule({**report_schedule_settings(), **changes})


def _send_daily_report_text(result: dict[str, Any]) -> None:
    report = str(result.get("text") or "").strip()
    date = str(result.get("date") or "")
    if not report:
        return
    send_telegram_message(
        "\n".join(
            [
                f"Emergyx Care Daily Report — {date}",
                "",
                report,
                "",
                "Not a medical diagnosis.",
            ]
        )
    )


def _run_daily(now: datetime, settings: dict[str, Any]) -> None:
    with Session(engine) as session:
        result = generate_daily_report(
            session,
            date_str=now.date().isoformat(),
            source_filter=LIVE_SENSOR_SOURCE,
            persist=True,
        )
    if result.get("used_mock"):
        raise RuntimeError("Gemma daily report generation was unavailable.")
    if settings.get("daily_send_telegram"):
        _send_daily_report_text(result)
    _record_schedule_state(
        last_daily_run_date=now.date().isoformat(),
        last_run_at=current_timestamp(),
        last_error=None,
    )


def _run_weekly(now: datetime, settings: dict[str, Any]) -> None:
    with Session(engine) as session:
        result = generate_weekly_pdf_report(
            session,
            mode="live",
            source_filter=LIVE_SENSOR_SOURCE,
        )
        save_weekly_report(session, mode="live", result=result)
    if settings.get("weekly_send_telegram"):
        send_telegram_document(
            result.pdf_bytes,
            filename=result.filename,
            caption=(
                "Emergyx Care Weekly Safety & Wellness Report\n"
                f"{result.context.get('start_date')} to {result.context.get('end_date')}\n\n"
                "Not a medical diagnosis."
            ),
        )
    _record_schedule_state(
        last_weekly_run_key=f"{now.isocalendar().year}-W{now.isocalendar().week:02d}",
        last_run_at=current_timestamp(),
        last_error=None,
    )


def _should_run_pattern(now: datetime, settings: dict[str, Any]) -> bool:
    last_run = settings.get("last_pattern_run_at")
    if not isinstance(last_run, str) or not last_run:
        return True
    try:
        last_dt = datetime.fromisoformat(last_run)
    except ValueError:
        return True
    if last_dt.tzinfo is None:
        last_dt = last_dt.astimezone()
    elapsed_minutes = (now - last_dt.astimezone(now.tzinfo)).total_seconds() / 60
    return elapsed_minutes >= int(settings.get("pattern_interval_minutes", 60))


def _run_pattern_scan(now: datetime, settings: dict[str, Any]) -> None:
    with Session(engine) as session:
        result = run_gemma_pattern_scan(
            session,
            mode="live",
            source_filter=LIVE_SENSOR_SOURCE,
            send_telegram=bool(settings.get("pattern_send_telegram")),
        )
    _record_schedule_state(
        last_pattern_run_at=now.isoformat(),
        last_run_at=current_timestamp(),
        last_error=None,
        last_pattern_summary=result.get("overall_summary"),
    )


def _tick() -> None:
    now = datetime.now().astimezone()
    settings = report_schedule_settings()
    current_time = now.strftime("%H:%M")

    if settings.get("daily_enabled") and current_time == settings.get("daily_time"):
        today = now.date().isoformat()
        if settings.get("last_daily_run_date") != today:
            _run_daily(now, settings)

    if (
        settings.get("weekly_enabled")
        and now.weekday() == int(settings.get("weekly_day", 0))
        and current_time == settings.get("weekly_time")
    ):
        week_key = f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
        if settings.get("last_weekly_run_key") != week_key:
            _run_weekly(now, settings)

    if settings.get("pattern_enabled") and _should_run_pattern(now, settings):
        _run_pattern_scan(now, settings)


def _loop() -> None:
    LOGGER.info("Report scheduler started")
    while not _stop_event.wait(30):
        if not _job_lock.acquire(blocking=False):
            continue
        try:
            _tick()
        except Exception as exc:
            LOGGER.exception("Report scheduler tick failed")
            _record_schedule_state(last_error=str(exc), last_run_at=current_timestamp())
        finally:
            _job_lock.release()
    LOGGER.info("Report scheduler stopped")


def start_report_scheduler() -> None:
    global _thread
    if scheduler_running():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_loop, name="emergyx-report-scheduler", daemon=True)
    _thread.start()


def stop_report_scheduler() -> None:
    _stop_event.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=2.0)
