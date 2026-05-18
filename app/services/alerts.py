from __future__ import annotations

import json
import logging
import re
from threading import Thread
from typing import Any

from sqlmodel import Session, select

from app.config import get_settings
from app.models import AgentDecision, Alert, Event
from app.services.telegram import send_telegram_message
from app.services.utils import current_timestamp, json_safe_value, parse_boolish, parse_floatish


LOGGER = logging.getLogger(__name__)


# Default alerts use the deterministic urgent path. When the
# gemma_first_notifications setting is enabled, eligible events are routed
# through Gemma before any dashboard or Telegram alert is created.
# Severity codes follow a simple traffic-light model: RED = immediate caregiver
# alert, YELLOW = digest-only, GREEN = log-only.
SEVERITY_RED = "RED"
SEVERITY_YELLOW = "YELLOW"
SEVERITY_GREEN = "GREEN"
VITAL_CHANGE_TYPES = {"heart_rate", "respiration_rate"}


def _short_time(timestamp: str) -> str:
    if "T" in timestamp:
        return timestamp.split("T")[-1][:5]
    return timestamp


def build_fall_alert_message(event: Event, light: dict[str, Any] | None = None) -> str:
    when = _short_time(event.timestamp)
    lines = [
        "🚨 Emergyx Care Alert",
        "",
        f"Likely fall detected in {event.room} at {when}.",
    ]
    if light is not None:
        lux = light.get("lux")
        category = light.get("category", "unknown")
        if isinstance(lux, (int, float)):
            lines.append(f"Light context: {category}, {lux:.1f} lux.")
        else:
            lines.append(f"Light context: {category}.")

    if event.source != "live_sensor":
        lines.append(f"(Event source: {event.source})")

    lines.extend(
        [
            "",
            "Please check on the person immediately.",
            "",
            "Prototype caregiver-support alert. Not a medical device.",
        ]
    )
    return "\n".join(lines)


def build_fall_alert_actions() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Explain", "callback_data": "cmd:explain"},
                {"text": "Live status", "callback_data": "cmd:status"},
            ],
            [
                {"text": "Latest event", "callback_data": "cmd:latest"},
                {"text": "Daily report", "callback_data": "cmd:report"},
            ],
        ]
    }


def _latest_light_context(session: Session, event: Event) -> dict[str, Any] | None:
    # Imported lazily to avoid a circular import (events imports alerts).
    from app.services.events import get_latest_light_context

    return get_latest_light_context(
        session,
        source_filter=event.source,
        sensor_id_filter=event.sensor_id,
    )


def _valid_vital_range(event_type: str) -> tuple[float, float]:
    if event_type == "heart_rate":
        return (25.0, 220.0)
    return (6.0, 60.0)


def _major_vital_change(session: Session, event: Event) -> dict[str, Any] | None:
    if event.event_type not in VITAL_CHANGE_TYPES:
        return None
    current_value = parse_floatish(event.value)
    if current_value is None:
        return None
    min_value, max_value = _valid_vital_range(event.event_type)
    if not (min_value <= current_value <= max_value):
        return None

    statement = (
        select(Event)
        .where(Event.sensor_id == event.sensor_id)
        .where(Event.event_type == event.event_type)
        .where(Event.id != event.id)
        .order_by(Event.id.desc())
        .limit(25)
    )
    previous: Event | None = None
    previous_value: float | None = None
    for row in session.exec(statement):
        value = parse_floatish(row.value)
        if value is not None and min_value <= value <= max_value:
            previous = row
            previous_value = value
            break
    if previous is None or previous_value is None:
        return None

    delta = current_value - previous_value
    abs_delta = abs(delta)
    pct_delta = abs_delta / max(previous_value, 1.0)
    if event.event_type == "heart_rate":
        is_major = abs_delta >= 25 or pct_delta >= 0.3
        unit = "bpm"
    else:
        is_major = abs_delta >= 8 or pct_delta >= 0.4
        unit = "breaths/min"
    if not is_major:
        return None
    return {
        "event_type": event.event_type,
        "current_value": current_value,
        "previous_value": previous_value,
        "delta": delta,
        "percent_delta": round(pct_delta * 100, 1),
        "unit": unit,
        "previous_timestamp": previous.timestamp,
        "threshold": "heart rate >=25 bpm or >=30%" if event.event_type == "heart_rate" else "breathing >=8 br/min or >=40%",
    }


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
        raise ValueError("Gemma notification decision was not a JSON object.")
    return parsed


def _gemma_notification_prompt(
    *,
    event: Event,
    trigger: str,
    light: dict[str, Any] | None,
    vital_change: dict[str, Any] | None,
) -> str:
    payload = {
        "task": "Decide whether Emergyx Care should send a caregiver alert for this event.",
        "rules": [
            "You are the only decision-maker in Gemma-first notification mode.",
            "Return JSON only. No markdown.",
            "Do not diagnose.",
            "If send_alert is true, write the exact caregiver-facing telegram_message.",
            "If send_alert is false, keep telegram_message empty.",
            "Use likely-fall language for fall events.",
        ],
        "required_json_schema": {
            "send_alert": "boolean",
            "severity": "low | medium | high",
            "alert_type": "likely_fall | vital_change | no_alert",
            "telegram_message": "string",
            "dashboard_message": "string",
            "rationale": "string",
        },
        "event": {
            "id": event.id,
            "timestamp": event.timestamp,
            "sensor_id": event.sensor_id,
            "room": event.room,
            "event_type": event.event_type,
            "value": event.value,
            "source": event.source,
            "metadata_json": event.metadata_json,
        },
        "trigger": trigger,
        "light_context": light,
        "vital_change": vital_change,
    }
    return json.dumps(json_safe_value(payload), indent=2, sort_keys=True)


def _save_gemma_notification_decision(
    session: Session,
    *,
    event: Event,
    output_text: str,
    metadata: dict[str, Any],
) -> None:
    session.add(
        AgentDecision(
            timestamp=current_timestamp(),
            related_event_id=event.id,
            decision_type="gemma_first_notification",
            input_summary=f"event_id={event.id} type={event.event_type} room={event.room}",
            output_text=output_text[:5000],
            model_name=str(metadata.get("model_name") or get_settings().gemma_model),
            metadata_json=json.dumps(json_safe_value(metadata), sort_keys=True, default=str),
        )
    )
    session.commit()


def _handle_gemma_first_notification(
    session: Session,
    event: Event,
    *,
    light: dict[str, Any] | None,
) -> list[Alert]:
    if event.event_type == "fall_detected" and parse_boolish(event.value):
        trigger = "likely_fall"
        vital_change = None
    else:
        vital_change = _major_vital_change(session, event)
        if vital_change is None:
            return []
        trigger = "major_vital_change"

    settings = get_settings()
    if not settings.gemma_enabled:
        _save_gemma_notification_decision(
            session,
            event=event,
            output_text="Gemma-first notification skipped because Gemma is disabled.",
            metadata={"send_alert": False, "error": "gemma_disabled", "model_name": settings.gemma_model},
        )
        return []

    try:
        from app.services.gemma_agent import _call_ollama

        prompt = _gemma_notification_prompt(
            event=event,
            trigger=trigger,
            light=light,
            vital_change=vital_change,
        )
        text, _thinking = _call_ollama(prompt, think=False, timeout=45.0)
        decision = _extract_json_object(text)
    except Exception as exc:
        LOGGER.warning("Gemma-first notification decision failed for event_id=%s: %s", event.id, exc)
        _save_gemma_notification_decision(
            session,
            event=event,
            output_text=f"Gemma-first notification failed: {exc}",
            metadata={"send_alert": False, "error": str(exc), "model_name": settings.gemma_model},
        )
        return []

    send_alert = bool(decision.get("send_alert"))
    telegram_message = str(decision.get("telegram_message") or "").strip()
    dashboard_message = str(decision.get("dashboard_message") or telegram_message or "").strip()
    alert_type = str(decision.get("alert_type") or ("likely_fall" if trigger == "likely_fall" else "vital_change"))
    severity = str(decision.get("severity") or "medium").lower()
    if severity not in {"low", "medium", "high"}:
        severity = "medium"

    metadata = {
        "gemma_first": True,
        "trigger": trigger,
        "decision": decision,
        "light_context": light,
        "vital_change": vital_change,
        "model_name": settings.gemma_model,
    }
    _save_gemma_notification_decision(
        session,
        event=event,
        output_text=text,
        metadata={**metadata, "send_alert": send_alert},
    )

    if not send_alert:
        LOGGER.info("Gemma-first notification suppressed alert for event_id=%s", event.id)
        return []

    if not telegram_message:
        telegram_message = dashboard_message or "Emergyx Care alert: Gemma recommends caregiver review."
    sent_success = send_telegram_message(telegram_message, reply_markup=build_fall_alert_actions())
    alert = Alert(
        timestamp=current_timestamp(),
        event_id=event.id,
        severity=severity,
        alert_type=alert_type,
        message=dashboard_message or telegram_message,
        sent_channel="telegram" if sent_success else "telegram_skipped_or_failed",
        sent_success=sent_success,
        metadata_json=json.dumps(json_safe_value(metadata), sort_keys=True, default=str),
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)
    LOGGER.info("Gemma-first notification created alert for event_id=%s sent_success=%s", event.id, sent_success)
    return [alert]


def _build_gemma_followup_message(result: dict[str, Any]) -> str:
    incident = result.get("incident") or {}
    event = incident.get("event") or {}
    room = incident.get("room") or event.get("room") or "unknown room"
    model_name = result.get("model_name") or "Gemma"
    label = "Deterministic fallback" if result.get("used_mock") else f"Gemma via {model_name}"
    return "\n".join(
        [
            "Emergyx Care explanation",
            "",
            f"{label}",
            f"Incident: {room}",
            "",
            str(result.get("text") or "").strip(),
            "",
            "This explanation is separate from the immediate rule-based alert.",
        ]
    )


def _send_gemma_followup_async(event_id: int, source_filter: str | None) -> None:
    def run() -> None:
        try:
            from app.db import engine
            from app.services.gemma_agent import explain_incident

            with Session(engine) as followup_session:
                result = explain_incident(
                    followup_session,
                    event_id=event_id,
                    source_filter=source_filter,
                )
            if not result.get("success"):
                LOGGER.info("Skipping Telegram Gemma follow-up for event_id=%s: %s", event_id, result.get("text"))
                return

            sent = send_telegram_message(_build_gemma_followup_message(result))
            LOGGER.info(
                "Telegram Gemma follow-up processed for event_id=%s sent_success=%s",
                event_id,
                sent,
            )
        except Exception as exc:
            LOGGER.warning("Telegram Gemma follow-up failed for event_id=%s: %s", event_id, exc)

    Thread(target=run, name=f"gemma-alert-followup-{event_id}", daemon=True).start()


def handle_event_alerts(session: Session, event: Event) -> list[Alert]:
    created_alerts: list[Alert] = []

    settings = get_settings()
    light = _latest_light_context(session, event)
    if settings.gemma_first_notifications:
        return _handle_gemma_first_notification(session, event, light=light)

    if event.event_type != "fall_detected" or not parse_boolish(event.value):
        return created_alerts

    message = build_fall_alert_message(event, light=light)
    sent_success = send_telegram_message(message, reply_markup=build_fall_alert_actions())
    if sent_success:
        sent_channel = "telegram"
    else:
        # We always create the Alert row even when Telegram is offline / not
        # configured — the local dashboard must still reflect the event.
        sent_channel = "telegram_skipped_or_failed"

    metadata: dict[str, Any] = {
        "rule": "fall_detected_true_immediate",
        "event_type": event.event_type,
        "source": event.source,
        "severity_code": SEVERITY_RED,
    }
    if light is not None:
        metadata["light_context"] = light

    alert = Alert(
        timestamp=current_timestamp(),
        event_id=event.id,
        severity="high",
        alert_type="likely_fall",
        message=message,
        sent_channel=sent_channel,
        sent_success=sent_success,
        metadata_json=json.dumps(metadata, sort_keys=True, default=str),
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)
    created_alerts.append(alert)

    LOGGER.info(
        "Processed fall alert for event_id=%s, sent_success=%s",
        event.id,
        sent_success,
    )

    if settings.telegram_send_gemma_explanations and event.id is not None:
        _send_gemma_followup_async(event.id, event.source)

    return created_alerts
