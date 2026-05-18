from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.models import Alert, Event
from app.schemas import AlertRead, EventRead
from app.services.events import create_event
from app.services.gemma_findings import run_gemma_pattern_scan
from app.services.utils import current_timestamp, normalize_metadata


router = APIRouter(prefix="/demo", tags=["demo"])


def _mock_alert(session: Session, *, event: Event | None, severity: str, alert_type: str, message: str) -> Alert:
    alert = Alert(
        timestamp=current_timestamp(),
        event_id=event.id if event else None,
        severity=severity,
        alert_type=alert_type,
        message=message,
        sent_channel="mock_demo_inbox",
        sent_success=True,
        metadata_json=normalize_metadata({"demo_scenario": True, "mock_delivery": True, "mode": "demo"}),
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


def _response(*, scenario: str, events: list[Event], alerts: list[Alert], next_step: str) -> dict[str, Any]:
    return {
        "success": True,
        "scenario": scenario,
        "created_at": current_timestamp(),
        "events": [EventRead.model_validate(event) for event in events],
        "alerts": [AlertRead.model_validate(alert) for alert in alerts],
        "next_step": next_step,
    }


@router.post("/scenarios/fall")
def scenario_fall(session: Session = Depends(get_session)) -> dict[str, Any]:
    fall = create_event(
        session,
        sensor_id="demo_fda2_bedroom",
        room="bedroom",
        event_type="fall_detected",
        value=True,
        source="simulated",
        metadata_json={"demo_scenario": "judge_fall", "triggered_at": current_timestamp()},
        trigger_alerts=False,
    )
    clear = create_event(
        session,
        sensor_id="demo_fda2_bedroom",
        room="bedroom",
        event_type="fall_detected",
        value=False,
        source="simulated",
        metadata_json={"demo_scenario": "judge_fall_clear", "triggered_at": current_timestamp()},
        trigger_alerts=False,
    )
    alert = _mock_alert(
        session,
        event=fall,
        severity="high",
        alert_type="likely_fall",
        message="Mock alert: likely fall detected in Bedroom. Open the incident timeline and ask Gemma for interpretation.",
    )
    return _response(
        scenario="fall",
        events=[fall, clear],
        alerts=[alert],
        next_step="Open Overview or Chat and ask Gemma: What happened in the bedroom?",
    )


@router.post("/scenarios/vitals-change")
def scenario_vitals_change(session: Session = Depends(get_session)) -> dict[str, Any]:
    heart = create_event(
        session,
        sensor_id="demo_bha2_bedside",
        room="bedroom",
        event_type="heart_rate",
        value=108,
        source="simulated",
        metadata_json={"demo_scenario": "vitals_change", "unit": "bpm"},
        trigger_alerts=False,
    )
    breathing = create_event(
        session,
        sensor_id="demo_bha2_bedside",
        room="bedroom",
        event_type="respiration_rate",
        value=22,
        source="simulated",
        metadata_json={"demo_scenario": "vitals_change", "unit": "breaths/min"},
        trigger_alerts=False,
    )
    alert = _mock_alert(
        session,
        event=heart,
        severity="medium",
        alert_type="gemma_pattern",
        message="Mock alert: demo vitals changed from baseline. Gemma pattern scan can decide whether caregiver attention is needed.",
    )
    return _response(
        scenario="vitals-change",
        events=[heart, breathing],
        alerts=[alert],
        next_step="Run a Gemma pattern scan from Reports to turn this into a caregiver finding.",
    )


@router.post("/scenarios/night-activity")
def scenario_night_activity(session: Session = Depends(get_session)) -> dict[str, Any]:
    events: list[Event] = []
    for room, minute in (("bathroom", 5), ("bathroom", 12), ("bedroom", 20)):
        events.append(
            create_event(
                session,
                sensor_id="demo_mmwave_bathroom" if room == "bathroom" else "demo_fda2_bedroom",
                room=room,
                event_type="person_present",
                value=True,
                source="simulated",
                metadata_json={"demo_scenario": "night_activity", "minute": minute},
                trigger_alerts=False,
            )
        )
    alert = _mock_alert(
        session,
        event=events[0],
        severity="medium",
        alert_type="gemma_pattern",
        message="Mock alert: nighttime bathroom activity increased in the demo scenario. Review trends and bathroom path safety.",
    )
    return _response(
        scenario="night-activity",
        events=events,
        alerts=[alert],
        next_step="Open Reports and review Gemma Pattern Monitor.",
    )


@router.post("/scenarios/pattern-scan")
def scenario_pattern_scan(session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        result = run_gemma_pattern_scan(
            session,
            mode="demo",
            source_filter="__demo_simulated__",
            send_telegram=False,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "success": True,
        "scenario": "pattern-scan",
        "created_at": current_timestamp(),
        "model_name": result.get("model_name"),
        "overall_summary": result.get("overall_summary"),
        "findings_created": len(result.get("findings", [])),
        "alerts_created": len(result.get("alerts_created", [])),
        "next_step": "Open Reports and review saved Gemma findings.",
    }


@router.post("/scenarios/reset")
def scenario_reset() -> dict[str, Any]:
    from scripts.seed_demo_data import seed

    seed(reset=True)
    return {
        "success": True,
        "scenario": "reset",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "next_step": "Reload the dashboard in demo mode.",
    }
