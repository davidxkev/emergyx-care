from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from app.models import DailyReport, WeeklyReport
from app.services.utils import current_timestamp, normalize_metadata
from app.services.weekly_reports import WeeklyReportResult


def report_service_status() -> str:
    return (
        "Daily report scheduling is intentionally deferred. "
        "Milestone 1 focuses on local event logging, immediate rule-based fall alerts, and dashboard visibility."
    )


def _report_metadata(report: DailyReport) -> dict[str, Any]:
    if not report.metadata_json:
        return {}
    try:
        loaded = json.loads(report.metadata_json)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _report_matches_mode(report: DailyReport, mode: str) -> bool:
    metadata = _report_metadata(report)
    return metadata.get("mode") == mode


def list_reports_for_mode(
    session: Session,
    *,
    mode: str,
    limit: int = 14,
) -> list[DailyReport]:
    statement = select(DailyReport).order_by(DailyReport.id.desc()).limit(max(limit, 1) * 3)
    reports = list(session.exec(statement))
    filtered = [report for report in reports if _report_matches_mode(report, mode)]
    return filtered[:limit]


def get_latest_report_for_mode(
    session: Session,
    *,
    mode: str,
) -> DailyReport | None:
    reports = list_reports_for_mode(session, mode=mode, limit=1)
    return reports[0] if reports else None


def save_weekly_report(
    session: Session,
    *,
    mode: str,
    result: WeeklyReportResult,
) -> WeeklyReport:
    ctx = result.context
    appendix = ctx.get("technical_appendix") or {}
    metadata = {
        "mode": mode,
        "used_mock": result.used_mock,
        "raw_counts": appendix.get("raw_counts"),
        "score_factors": appendix.get("score_factors"),
        "generated_iso_timestamp": appendix.get("generated_iso_timestamp"),
    }
    report = WeeklyReport(
        start_date=str(ctx.get("start_date") or ""),
        end_date=str(ctx.get("end_date") or ""),
        created_at=current_timestamp(),
        mode=mode,
        filename=result.filename,
        model_name=result.model_name,
        pdf_bytes=result.pdf_bytes,
        metadata_json=normalize_metadata(metadata),
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def list_weekly_reports_for_mode(
    session: Session,
    *,
    mode: str,
    limit: int = 20,
) -> list[WeeklyReport]:
    statement = (
        select(WeeklyReport)
        .where(WeeklyReport.mode == mode)
        .order_by(WeeklyReport.id.desc())
        .limit(max(limit, 1))
    )
    return list(session.exec(statement))


def get_weekly_report(
    session: Session,
    *,
    report_id: int,
) -> WeeklyReport | None:
    return session.get(WeeklyReport, report_id)
