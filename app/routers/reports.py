from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlmodel import Session

from app.db import get_session
from app.schemas import (
    DailyReportRead,
    DailyReportRequest,
    DailyReportResponse,
    GemmaFindingRead,
    GemmaPatternScanRequest,
    GemmaPatternScanResponse,
    ReportScheduleRead,
    ReportScheduleTelegramTestRequest,
    ReportScheduleTelegramTestResponse,
    ReportScheduleUpdate,
    WeeklyReportRead,
    WeeklyReportRequest,
)
from app.services.gemma_agent import generate_daily_report
from app.services.gemma_findings import list_gemma_findings, run_gemma_pattern_scan
from app.services.reports import (
    get_latest_report_for_mode,
    get_weekly_report,
    list_reports_for_mode,
    list_weekly_reports_for_mode,
    save_weekly_report,
)
from app.services.weekly_reports import WeeklyReportGemmaError, generate_weekly_pdf_report
from app.services.report_scheduler import (
    report_schedule_settings,
    save_report_schedule_settings,
    scheduler_running,
)
from app.services.telegram import send_telegram_document, send_telegram_message
from app.services.utils import LIVE_SENSOR_SOURCE, parse_mode


router = APIRouter(prefix="/reports", tags=["reports"])


def _schedule_read() -> ReportScheduleRead:
    return ReportScheduleRead(
        **report_schedule_settings(),
        scheduler_running=scheduler_running(),
    )


@router.get("/schedule", response_model=ReportScheduleRead)
def get_report_schedule() -> ReportScheduleRead:
    return _schedule_read()


@router.post("/schedule", response_model=ReportScheduleRead)
def update_report_schedule(payload: ReportScheduleUpdate) -> ReportScheduleRead:
    save_report_schedule_settings(payload.model_dump())
    return _schedule_read()


@router.post("/schedule/test-telegram", response_model=ReportScheduleTelegramTestResponse)
def test_report_schedule_telegram(
    payload: ReportScheduleTelegramTestRequest,
    session: Session = Depends(get_session),
) -> ReportScheduleTelegramTestResponse:
    if payload.report_type == "daily":
        result = generate_daily_report(
            session,
            persist=True,
            source_filter=LIVE_SENSOR_SOURCE,
        )
        if result.get("used_mock"):
            raise HTTPException(status_code=503, detail="Gemma daily report generation was unavailable.")
        sent = send_telegram_message(
            "\n".join(
                [
                    f"Emergyx Care Daily Report — {result.get('date')}",
                    "",
                    str(result.get("text") or "").strip(),
                    "",
                    "Not a medical diagnosis.",
                ]
            )
        )
        return ReportScheduleTelegramTestResponse(
            success=sent,
            message="Daily report sent to Telegram." if sent else "Daily report Telegram send failed.",
        )

    try:
        result = generate_weekly_pdf_report(
            session,
            mode="live",
            source_filter=LIVE_SENSOR_SOURCE,
        )
        saved_report = save_weekly_report(session, mode="live", result=result)
    except WeeklyReportGemmaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    sent = send_telegram_document(
        result.pdf_bytes,
        filename=result.filename,
        caption=(
            "Emergyx Care Weekly Safety & Wellness Report\n"
            f"{result.context.get('start_date')} to {result.context.get('end_date')}\n\n"
            "Not a medical diagnosis."
        ),
    )
    return ReportScheduleTelegramTestResponse(
        success=sent,
        message=(
            f"Weekly report #{saved_report.id} sent to Telegram."
            if sent
            else f"Weekly report #{saved_report.id} was generated, but Telegram send failed."
        ),
    )


@router.post("/daily", response_model=DailyReportResponse)
def generate_today_report(
    payload: DailyReportRequest | None = None,
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
) -> DailyReportResponse:
    request = payload or DailyReportRequest()
    _, source_filter = parse_mode(mode)
    result = generate_daily_report(
        session,
        date_str=request.date,
        persist=True,
        source_filter=source_filter,
    )
    if request.require_gemma and result.get("used_mock"):
        raise HTTPException(
            status_code=503,
            detail="Gemma daily report generation was unavailable. Check Ollama/Gemma settings.",
        )
    return DailyReportResponse(
        success=result["success"],
        used_mock=result["used_mock"],
        model_name=result["model_name"],
        date=result["date"],
        report=result.get("text", ""),
        report_id=result.get("report_id"),
        tools_used=result.get("tools_used", []),
    )


@router.get("/daily/latest", response_model=DailyReportRead | None)
def get_latest_report(
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
) -> DailyReportRead | None:
    normalized_mode, _ = parse_mode(mode)
    report = get_latest_report_for_mode(session, mode=normalized_mode)
    if report is None:
        return None
    return DailyReportRead.model_validate(report)


@router.get("/daily", response_model=list[DailyReportRead])
def list_reports(
    limit: int = 14,
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
) -> list[DailyReportRead]:
    safe_limit = max(1, min(limit, 60))
    normalized_mode, _ = parse_mode(mode)
    reports = list_reports_for_mode(session, mode=normalized_mode, limit=safe_limit)
    return [DailyReportRead.model_validate(r) for r in reports]


@router.get("/gemma-findings", response_model=list[GemmaFindingRead])
def list_findings(
    limit: int = 20,
    mode: str = Query("live", description="demo or live"),
    session: Session = Depends(get_session),
) -> list[GemmaFindingRead]:
    safe_limit = max(1, min(limit, 100))
    normalized_mode, _ = parse_mode(mode)
    findings = list_gemma_findings(session, mode=normalized_mode, limit=safe_limit)
    return [GemmaFindingRead.model_validate(finding) for finding in findings]


@router.post("/gemma-findings/scan", response_model=GemmaPatternScanResponse)
def run_findings_scan(
    payload: GemmaPatternScanRequest | None = None,
    mode: str = Query("live", description="demo or live"),
    session: Session = Depends(get_session),
) -> GemmaPatternScanResponse:
    request = payload or GemmaPatternScanRequest()
    normalized_mode, source_filter = parse_mode(mode)
    try:
        result = run_gemma_pattern_scan(
            session,
            mode=normalized_mode,
            source_filter=source_filter,
            send_telegram=request.send_telegram,
            night_start_hour=request.night_start_hour if request.night_start_hour is not None else 22,
            night_end_hour=request.night_end_hour if request.night_end_hour is not None else 6,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return GemmaPatternScanResponse(
        success=True,
        model_name=str(result.get("model_name") or ""),
        created_at=str(result.get("created_at") or ""),
        overall_summary=str(result.get("overall_summary") or ""),
        findings=[GemmaFindingRead.model_validate(item) for item in result.get("findings", [])],
        alerts_created=len(result.get("alerts_created", [])),
    )


@router.post("/weekly/pdf")
def generate_weekly_pdf(
    payload: WeeklyReportRequest | None = None,
    mode: str = Query("live", description="demo or live"),
    session: Session = Depends(get_session),
) -> Response:
    request = payload or WeeklyReportRequest()
    normalized_mode, source_filter = parse_mode(mode)
    try:
        result = generate_weekly_pdf_report(
            session,
            mode=normalized_mode,
            source_filter=source_filter,
            start_date=request.start_date,
            end_date=request.end_date,
            night_start_hour=request.night_start_hour if request.night_start_hour is not None else 22,
            night_end_hour=request.night_end_hour if request.night_end_hour is not None else 6,
        )
        saved_report = save_weekly_report(session, mode=normalized_mode, result=result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except WeeklyReportGemmaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return Response(
        content=result.pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
            "X-Emergyx-Model": result.model_name,
            "X-Emergyx-Weekly-Report-Id": str(saved_report.id),
        },
    )


@router.get("/weekly", response_model=list[WeeklyReportRead])
def list_weekly_reports(
    limit: int = 20,
    mode: str = Query("live", description="demo or live"),
    session: Session = Depends(get_session),
) -> list[WeeklyReportRead]:
    safe_limit = max(1, min(limit, 60))
    normalized_mode, _ = parse_mode(mode)
    reports = list_weekly_reports_for_mode(session, mode=normalized_mode, limit=safe_limit)
    return [WeeklyReportRead.model_validate(report) for report in reports]


@router.get("/weekly/{report_id}/pdf")
def download_weekly_report(
    report_id: int,
    session: Session = Depends(get_session),
) -> Response:
    report = get_weekly_report(session, report_id=report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Weekly report not found.")
    return Response(
        content=report.pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{report.filename}"',
            "X-Emergyx-Model": report.model_name,
            "X-Emergyx-Weekly-Report-Id": str(report.id),
        },
    )
