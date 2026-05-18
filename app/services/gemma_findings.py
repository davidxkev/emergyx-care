from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from app.config import get_settings, load_runtime_care_context
from app.models import AgentDecision, Alert, Event, GemmaFinding
from app.services.telegram import send_telegram_message
from app.services.trends import get_today_trends, get_week_trends
from app.services.utils import (
    DEMO_MODE_SOURCE_FILTER,
    DEMO_SOURCES,
    LIVE_SENSOR_SOURCE,
    current_date,
    current_timestamp,
    json_safe_value,
    parse_floatish,
)


LOGGER = logging.getLogger(__name__)


def _source_statement(source_filter: str | None):
    statement = select(Event)
    if source_filter == DEMO_MODE_SOURCE_FILTER:
        statement = statement.where(Event.source.in_(DEMO_SOURCES))
    elif source_filter is not None:
        statement = statement.where(Event.source == source_filter)
    return statement


def _recent_events(session: Session, *, source_filter: str | None, limit: int = 120) -> list[dict[str, Any]]:
    statement = _source_statement(source_filter).order_by(Event.id.desc()).limit(limit)
    rows = list(session.exec(statement))
    return [
        {
            "id": row.id,
            "timestamp": row.timestamp,
            "sensor_id": row.sensor_id,
            "room": row.room,
            "event_type": row.event_type,
            "value": row.value,
            "source": row.source,
            "metadata_json": row.metadata_json,
        }
        for row in reversed(rows)
    ]


def _vital_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for event_type, label, unit in (
        ("heart_rate", "heart rate", "bpm"),
        ("respiration_rate", "breathing rate", "breaths/min"),
    ):
        values: list[float] = []
        latest: dict[str, Any] | None = None
        for event in events:
            if event.get("event_type") != event_type:
                continue
            value = parse_floatish(event.get("value"))
            if value is None:
                continue
            if event_type == "heart_rate" and not (25 <= value <= 220):
                continue
            if event_type == "respiration_rate" and not (6 <= value <= 60):
                continue
            values.append(value)
            latest = {**event, "value": value}
        summary[event_type] = {
            "label": label,
            "unit": unit,
            "reading_count": len(values),
            "latest": latest,
            "average": round(sum(values) / len(values), 1) if values else None,
            "minimum": min(values) if values else None,
            "maximum": max(values) if values else None,
        }
    return summary


def _extract_json_object(text: str) -> dict[str, Any]:
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", clean, flags=re.S)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Gemma findings response was not a JSON object.")
    return parsed


def _fingerprint(*, mode: str, pattern_type: str, title: str) -> str:
    raw = f"{current_date()}|{mode}|{pattern_type.strip().lower()}|{title.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _existing_fingerprint(session: Session, fingerprint: str) -> bool:
    return (
        session.exec(
            select(GemmaFinding)
            .where(GemmaFinding.fingerprint == fingerprint)
            .limit(1)
        ).first()
        is not None
    )


def _normalize_severity(value: object) -> str:
    severity = str(value or "info").strip().lower()
    if severity in {"critical", "urgent"}:
        return "high"
    if severity not in {"info", "low", "medium", "high"}:
        return "medium"
    return severity


def _prompt(payload: dict[str, Any]) -> str:
    return json.dumps(
        {
            "task": "Analyze Emergyx Care local data for caregiver-relevant safety and wellness patterns.",
            "requirements": [
                "Return JSON only. No markdown.",
                "Do not diagnose, do not give medication advice, and do not pretend certainty.",
                "Use likely-fall wording for fall-related patterns.",
                "Find patterns from the provided data, not from assumptions.",
                "Create findings only when a caregiver could act on them or should know about them.",
                "If no meaningful pattern exists, return an empty findings array and a short overall_summary.",
                "Set send_alert true only for patterns that deserve caregiver attention today.",
                "If send_alert is true, write the exact telegram_message and dashboard_message.",
            ],
            "required_json_schema": {
                "overall_summary": "string",
                "findings": [
                    {
                        "pattern_type": "fall_risk | vitals_change | nighttime_activity | bathroom_trend | sensor_reliability | routine_change | other",
                        "severity": "info | low | medium | high",
                        "title": "string",
                        "summary": "string",
                        "evidence": ["string"],
                        "caregiver_action": "string",
                        "send_alert": "boolean",
                        "telegram_message": "string",
                        "dashboard_message": "string",
                    }
                ],
            },
            "local_data": payload,
        },
        indent=2,
        sort_keys=True,
        default=str,
    )


def _fallback_findings_payload(payload: dict[str, Any], error_message: str) -> dict[str, Any]:
    week = payload.get("week_trends") if isinstance(payload.get("week_trends"), dict) else {}
    today = payload.get("today_trends") if isinstance(payload.get("today_trends"), dict) else {}
    findings: list[dict[str, Any]] = []

    safety = week.get("safety") if isinstance(week.get("safety"), dict) else {}
    fall_count = int(safety.get("falls_week") or safety.get("likely_falls_week") or 0)
    if fall_count > 0:
        findings.append(
            {
                "pattern_type": "fall_risk",
                "severity": "high" if fall_count >= 2 else "medium",
                "title": "Likely fall pattern needs review",
                "summary": (
                    f"Emergyx recorded {fall_count} likely-fall signal(s) in the demo week. "
                    "A caregiver should review the incident timeline and confirm whether each signal was a true fall or a false alarm."
                ),
                "evidence": [f"{fall_count} likely-fall signal(s) recorded this week"],
                "caregiver_action": "Review the incident timeline, confirm true fall versus false alarm, and inspect room fall risks.",
                "send_alert": fall_count >= 2,
                "telegram_message": "Emergyx Care pattern: repeated likely-fall signals need caregiver review.",
                "dashboard_message": "Repeated likely-fall signals need caregiver review.",
            }
        )

    nighttime = today.get("nighttime") if isinstance(today.get("nighttime"), dict) else {}
    night_readings = int(nighttime.get("night_sensor_readings") or nighttime.get("total_events") or 0)
    bathroom_events = int(nighttime.get("bathroom_events") or 0)
    if bathroom_events > 0 or night_readings >= 5:
        findings.append(
            {
                "pattern_type": "nighttime_activity",
                "severity": "medium",
                "title": "Nighttime movement pattern",
                "summary": (
                    "Nighttime movement was recorded in the demo data. This is useful caregiver context, "
                    "especially when reviewed alongside fall-like signals and room safety."
                ),
                "evidence": [f"{night_readings} nighttime sensor reading(s)", f"{bathroom_events} bathroom-related event(s)"],
                "caregiver_action": "Review the bathroom path, lighting, rugs, and support rails before the next night.",
                "send_alert": False,
                "telegram_message": "",
                "dashboard_message": "Nighttime activity pattern recorded for caregiver review.",
            }
        )

    if not findings:
        findings.append(
            {
                "pattern_type": "other",
                "severity": "info",
                "title": "Demo data reviewed",
                "summary": "The local demo timeline was reviewed, but no urgent new pattern was detected.",
                "evidence": ["Seeded demo data is available"],
                "caregiver_action": "Continue with the demo walkthrough and review the weekly report.",
                "send_alert": False,
                "telegram_message": "",
                "dashboard_message": "Demo data reviewed.",
            }
        )

    return {
        "overall_summary": f"Gemma was unavailable, so Emergyx used local deterministic analysis. {error_message}",
        "findings": findings[:3],
    }


def _save_decision(
    session: Session,
    *,
    text: str,
    model_name: str,
    metadata: dict[str, Any],
) -> None:
    session.add(
        AgentDecision(
            timestamp=current_timestamp(),
            related_event_id=None,
            decision_type="gemma_pattern_scan",
            input_summary=str(metadata.get("input_summary") or "scheduled pattern scan"),
            output_text=text[:5000],
            model_name=model_name,
            metadata_json=json.dumps(json_safe_value(metadata), sort_keys=True, default=str),
        )
    )
    session.commit()


def list_gemma_findings(
    session: Session,
    *,
    mode: str,
    limit: int = 20,
) -> list[GemmaFinding]:
    statement = (
        select(GemmaFinding)
        .where(GemmaFinding.mode == mode)
        .order_by(GemmaFinding.id.desc())
        .limit(max(1, min(limit, 100)))
    )
    return list(session.exec(statement))


def run_gemma_pattern_scan(
    session: Session,
    *,
    mode: str = "live",
    source_filter: str | None = LIVE_SENSOR_SOURCE,
    send_telegram: bool = False,
    night_start_hour: int = 22,
    night_end_hour: int = 6,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.gemma_enabled:
        raise RuntimeError("Gemma is disabled. Enable Gemma before running pattern scans.")

    today_trends = get_today_trends(
        session,
        mode=mode,
        source_filter=source_filter,
        night_start_hour=night_start_hour,
        night_end_hour=night_end_hour,
    )
    week_trends = get_week_trends(
        session,
        mode=mode,
        source_filter=source_filter,
        night_start_hour=night_start_hour,
        night_end_hour=night_end_hour,
    )
    recent_events = _recent_events(session, source_filter=source_filter)
    payload = {
        "scan_time": current_timestamp(),
        "mode": mode,
        "source_filter": source_filter,
        "care_context": load_runtime_care_context(),
        "today_trends": today_trends,
        "week_trends": week_trends,
        "vitals_summary": _vital_summary(recent_events),
        "recent_events": recent_events[-80:],
    }

    from app.services.gemma_agent import _call_ollama, ollama_error_message

    used_fallback = False
    thinking = ""
    try:
        text, thinking = _call_ollama(_prompt(payload), think=False, timeout=180.0)
        parsed = _extract_json_object(text)
    except Exception as exc:
        used_fallback = True
        LOGGER.warning("Gemma pattern scan unavailable; using deterministic fallback: %s", exc)
        parsed = _fallback_findings_payload(payload, ollama_error_message(exc))
        text = json.dumps(parsed, sort_keys=True, default=str)
    findings_payload = parsed.get("findings") or []
    if not isinstance(findings_payload, list):
        raise ValueError("Gemma findings response did not include a findings array.")

    saved: list[GemmaFinding] = []
    alerts_created: list[Alert] = []
    for item in findings_payload[:8]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        summary = str(item.get("summary") or "").strip()
        if not title or not summary:
            continue
        pattern_type = str(item.get("pattern_type") or "other").strip().lower() or "other"
        severity = _normalize_severity(item.get("severity"))
        fingerprint = _fingerprint(mode=mode, pattern_type=pattern_type, title=title)
        if _existing_fingerprint(session, fingerprint):
            continue

        evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        send_alert = bool(item.get("send_alert")) and severity in {"medium", "high"}
        finding = GemmaFinding(
            created_at=current_timestamp(),
            mode=mode,
            source_filter=source_filter,
            pattern_type=pattern_type,
            severity=severity,
            title=title,
            summary=summary,
            evidence_json=json.dumps(json_safe_value(evidence), sort_keys=True, default=str),
            caregiver_action=str(item.get("caregiver_action") or "").strip() or None,
            model_name=settings.gemma_model,
            send_alert=send_alert,
            fingerprint=fingerprint,
            metadata_json=json.dumps(
                json_safe_value(
                    {
                        "overall_summary": parsed.get("overall_summary"),
                        "raw_item": item,
                        "thinking": thinking,
                    }
                ),
                sort_keys=True,
                default=str,
            ),
        )
        session.add(finding)
        session.commit()
        session.refresh(finding)

        if send_alert:
            telegram_message = str(item.get("telegram_message") or "").strip()
            dashboard_message = str(item.get("dashboard_message") or telegram_message or summary).strip()
            sent_success = send_telegram_message(telegram_message or dashboard_message) if send_telegram else False
            alert = Alert(
                timestamp=current_timestamp(),
                event_id=None,
                severity="high" if severity == "high" else "medium",
                alert_type="gemma_pattern",
                message=dashboard_message,
                sent_channel="telegram" if sent_success else ("dashboard_only" if not send_telegram else "telegram_skipped_or_failed"),
                sent_success=sent_success,
                metadata_json=json.dumps(
                    json_safe_value(
                        {
                            "gemma_finding_id": finding.id,
                            "pattern_type": pattern_type,
                            "telegram_requested": send_telegram,
                            "model_name": settings.gemma_model,
                            "used_fallback": used_fallback,
                        }
                    ),
                    sort_keys=True,
                    default=str,
                ),
            )
            session.add(alert)
            session.commit()
            session.refresh(alert)
            finding.alert_id = alert.id
            session.add(finding)
            session.commit()
            session.refresh(finding)
            alerts_created.append(alert)
        saved.append(finding)

    _save_decision(
        session,
        text=text,
        model_name=settings.gemma_model,
        metadata={
            "input_summary": f"mode={mode} findings={len(saved)} alerts={len(alerts_created)}",
            "overall_summary": parsed.get("overall_summary"),
            "used_fallback": used_fallback,
            "new_finding_ids": [finding.id for finding in saved],
            "alert_ids": [alert.id for alert in alerts_created],
        },
    )

    return {
        "success": True,
        "model_name": f"fallback:{settings.gemma_model}" if used_fallback else settings.gemma_model,
        "used_mock": used_fallback,
        "created_at": current_timestamp(),
        "overall_summary": str(parsed.get("overall_summary") or "").strip(),
        "findings": saved,
        "alerts_created": alerts_created,
        "raw_response": parsed,
    }
