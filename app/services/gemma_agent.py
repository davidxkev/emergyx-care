"""Gemma caregiver agent — local explanation, Q&A, and reporting layer.

Architectural contract:

  Sensors detect events → configured alert path stores everything in SQLite →
  Gemma reads structured local context → Gemma EXPLAINS, ANSWERS, REPORTS.

By default, urgent alerts stay rule-based. If gemma_first_notifications is
enabled, services.alerts.handle_event_alerts asks Gemma to decide whether to
create Telegram/dashboard alerts for likely falls and major vital changes.
The chat/report/explanation entry points may still use deterministic fallback
text when Ollama is unavailable.

Conservative wording is enforced via the system prompt:
  • say "likely fall" not "definite fall"
  • no diagnosis
  • answer only from the provided local data
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx
from sqlmodel import Session

from app.config import get_settings
from app.config import load_runtime_care_context
from app.models import AgentDecision, DailyReport
from app.services.events import (
    get_latest_event_by_type,
    get_latest_light_context,
    list_alerts_for_date,
    list_events_for_date,
    list_recent_alerts,
    list_recent_events,
)
from app.services.incidents import (
    get_incident_context,
    get_incidents_for_date,
)
from app.services.local_rag import retrieve_local_context
from app.services.trends import get_today_trends, summarize_trends_for_humans
from app.services.utils import current_date, current_timestamp


LOGGER = logging.getLogger(__name__)


# --- Public response shape ----------------------------------------------------

def _wrap_response(
    *,
    text: str,
    used_mock: bool,
    model_name: str,
    tools_used: list[str],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "success": True,
        "used_mock": used_mock,
        "model_name": model_name,
        "tools_used": tools_used,
        "text": text,
    }
    if extra:
        base.update(extra)
    return base


def _format_lux(lux: float | None) -> str:
    if isinstance(lux, (int, float)):
        return f"{lux:.1f} lux"
    return "unknown lux"


def _format_light_line(light: dict[str, Any] | None) -> str:
    if not light:
        return "Latest light context: none recorded."
    return (
        f"Latest light context: {light.get('category', 'unknown')} "
        f"({_format_lux(light.get('lux'))}) at {light.get('timestamp', '?')} "
        f"in {_format_room_name(light.get('room'))} [{light.get('source', '?')}]."
    )


def _format_vitals_for_prompt(vitals: dict[str, Any] | None) -> str:
    if not vitals:
        return "Current vitals: no heart-rate or breathing-rate readings found."
    lines = ["Current vitals:"]
    for key, label, unit in (
        ("heart_rate", "Heart rate", "bpm"),
        ("respiration_rate", "Breathing rate", "breaths/min"),
    ):
        info = vitals.get(key) or {}
        valid = info.get("current_valid")
        stale_valid = info.get("latest_valid") if not valid else None
        raw = info.get("latest_raw")
        if valid:
            lines.append(
                f"- {label}: {valid.get('value')} {unit} at {valid.get('timestamp')} "
                f"in {valid.get('room')} ({valid.get('age_human')})."
            )
        elif stale_valid:
            lines.append(
                f"- {label}: no fresh current reading. Latest valid reading was "
                f"{stale_valid.get('value')} {unit} at {stale_valid.get('timestamp')} "
                f"in {stale_valid.get('room')} ({stale_valid.get('age_human')})."
            )
        else:
            lines.append(f"- {label}: no valid current reading.")
        if raw and raw != valid and raw != stale_valid:
            lines.append(
                f"  Latest raw {label.lower()} value was {raw.get('value')} at {raw.get('timestamp')}; "
                "zero or out-of-range raw values should be described as unstable/no-target, not as true vital signs."
            )
    return "\n".join(lines)


def _format_event_line(event: dict[str, Any]) -> str:
    return (
        f"- {event.get('ts') or event.get('timestamp', '?')}: {event.get('type') or event.get('event_type', '?')}={event.get('value', '?')} "
        f"in {_format_room_name(event.get('room_label') or event.get('room'))} [{event.get('source', '?')}]"
    )


def _format_alert_line(alert: dict[str, Any]) -> str:
    return (
        f"- {alert.get('ts', '?')}: {alert.get('type', '?')} via "
        f"{alert.get('channel', '?')} (sent_success={alert.get('sent_success', '?')})"
    )


def _format_latest_state_line(label: str, event: dict[str, Any] | None) -> str:
    if not event:
        return f"{label}: no data."
    return (
        f"{label}: {event.get('type', '?')}={event.get('value', '?')} at "
        f"{event.get('ts', '?')} in {_format_room_name(event.get('room') or event.get('room_label'))} [{event.get('source', '?')}]."
    )


def _format_room_name(room: str | None) -> str:
    if not room:
        return "Unassigned room"
    match = re.fullmatch(r"auto_room_(\d+)", room)
    if match:
        return f"Sensor Area {match.group(1)}"
    if room == "demo_room":
        return "Demo Room"
    return " ".join(part.capitalize() for part in re.split(r"[_\s-]+", room) if part)


def _is_vitals_question(question: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9_]+", question.lower()))
    return bool(
        {"heart", "heartrate", "hr", "pulse", "breathing", "breath", "respiration", "respiratory", "vitals"}
        & tokens
    )


def _is_care_context_question(question: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9_]+", question.lower()))
    return bool(
        {"resident", "residents", "profile", "profiles", "context", "room", "rooms", "sensor", "sensors", "david"}
        & tokens
    )


def _is_greeting_question(question: str) -> bool:
    clean = re.sub(r"[^a-z0-9\s]", " ", question.lower()).strip()
    tokens = clean.split()
    if not tokens:
        return False
    greetings = {"hi", "hey", "hello", "yo", "hiya", "howdy"}
    return len(tokens) <= 3 and all(token in greetings or token in {"there"} for token in tokens)


def _greeting_answer() -> str:
    return (
        "Hi. I can help with the live sensor status, latest incidents, heart and breathing readings, "
        "alerts, reports, or caregiver recommendations. Ask me what you want to check."
    )


def _format_vital_value(reading: dict[str, Any] | None, *, decimals: int = 0) -> str:
    if not reading or reading.get("value") is None:
        return "not available"
    value = float(reading["value"])
    return f"{value:.{decimals}f}"


def _current_vitals_answer(retrieval: dict[str, Any]) -> str:
    snapshot = retrieval.get("snapshot") or {}
    vitals = snapshot.get("latest_vitals") or {}
    heart_info = vitals.get("heart_rate") or {}
    breathing_info = vitals.get("respiration_rate") or {}
    heart = heart_info.get("current_valid")
    breathing = breathing_info.get("current_valid")
    stale_heart = heart_info.get("latest_valid") if not heart else None
    stale_breathing = breathing_info.get("latest_valid") if not breathing else None
    heart_raw = heart_info.get("latest_raw")
    breathing_raw = breathing_info.get("latest_raw")

    parts: list[str] = []
    if heart:
        parts.append(
            f"The latest valid heart-rate reading is {_format_vital_value(heart)} bpm"
            f" from {_format_room_name(heart.get('room'))}, recorded {heart.get('age_human') or 'recently'}."
        )
    elif stale_heart:
        parts.append(
            f"I do not have a fresh current heart-rate reading. The latest valid heart-rate reading was "
            f"{_format_vital_value(stale_heart)} bpm from {_format_room_name(stale_heart.get('room'))}, "
            f"recorded {stale_heart.get('age_human') or 'earlier'}."
        )
    else:
        parts.append("I do not have a valid current heart-rate reading right now.")

    if breathing:
        parts.append(
            f"The latest valid breathing-rate reading is {_format_vital_value(breathing)} breaths/min"
            f" from {_format_room_name(breathing.get('room'))}, recorded {breathing.get('age_human') or 'recently'}."
        )
    elif stale_breathing:
        parts.append(
            f"I do not have a fresh current breathing-rate reading. The latest valid breathing-rate reading was "
            f"{_format_vital_value(stale_breathing)} breaths/min from {_format_room_name(stale_breathing.get('room'))}, "
            f"recorded {stale_breathing.get('age_human') or 'earlier'}."
        )
    else:
        parts.append("I do not have a stable current breathing-rate reading right now.")

    caution_parts: list[str] = []
    if heart_raw and heart_raw.get("value") in {0, 0.0}:
        caution_parts.append("heart-rate")
    if breathing_raw and (
        breathing_raw.get("value") in {0, 0.0}
        or (isinstance(breathing_raw.get("value"), (int, float)) and float(breathing_raw["value"]) < 6)
    ):
        caution_parts.append("breathing-rate")
    if caution_parts:
        parts.append(
            "I ignored the latest zero/out-of-range "
            + " and ".join(caution_parts)
            + " sensor value because these readings usually mean the mmWave sensor is settling, has no stable target, or produced a transient measurement."
        )

    if heart or breathing:
        parts.append("Use the Sensors page for the live stream; these values are monitoring signals, not a medical diagnosis.")
    else:
        parts.append("The sensor may still be online, but the current vital signal is stale or not stable enough to report as a live caregiver-facing value.")
    return " ".join(parts)


def _care_context_answer(question: str, retrieval: dict[str, Any]) -> str | None:
    snapshot = retrieval.get("snapshot") or {}
    care_context = snapshot.get("care_context") or {}
    residents = care_context.get("residents") or []
    sensors = care_context.get("sensors") or []
    if not residents and not sensors:
        return None

    lowered = question.lower()
    matched_residents = [
        resident
        for resident in residents
        if str(resident.get("name", "")).lower() in lowered
    ]
    if not matched_residents and any(token in lowered for token in ("resident", "residents", "profile", "david")):
        matched_residents = residents

    parts: list[str] = []
    for resident in matched_residents[:4]:
        name = resident.get("name") or "Resident"
        rooms = resident.get("room_labels") or []
        room_text = ", ".join(rooms) if rooms else "no monitored rooms yet"
        context = resident.get("context") or ""
        sentence = f"{name} is assigned to {room_text}."
        if context:
            sentence += f" Saved caregiver context: {context}"
        parts.append(sentence)

    if not parts and any(token in lowered for token in ("sensor", "sensors", "room", "rooms", "context")):
        for sensor in sensors[:5]:
            label = sensor.get("name") or sensor.get("sensor_id") or "Sensor"
            sentence = f"{label} is assigned to {sensor.get('room_label') or 'an unassigned room'}."
            if sensor.get("context"):
                sentence += f" Sensor context: {sensor.get('context')}"
            parts.append(sentence)

    if not parts:
        return None
    return " ".join(parts)


def _format_incident_line(incident: dict[str, Any]) -> str:
    event = incident.get("event") or {}
    duration = incident.get("duration_seconds")
    duration_part = f", duration ~{duration}s" if duration is not None else ""
    return (
        f"- Likely fall at {event.get('timestamp', '?')} in {_format_room_name(incident.get('room'))} "
        f"[{incident.get('source', '?')}]"
        f"{duration_part}."
    )


def _meta_response_detected(text: str | None) -> bool:
    if not text:
        return True
    lower = text.strip().lower()
    bad_phrases = (
        "the provided data is a json object",
        "please let me know what you would like me to do with it",
        "structured local data",
        "based on the data provided",
        "the data provided is",
        "i need more specific information about the data",
        "the input appears to be",
        "this is a json",
    )
    return any(phrase in lower for phrase in bad_phrases)


def _strict_retry_prompt(prompt: str) -> str:
    return (
        f"{prompt}\n\n"
        "IMPORTANT: Answer the caregiver directly.\n"
        "Do not describe the input format.\n"
        "Do not say JSON, structured data, provided data, or ask what to do with the data.\n"
        "Start with the answer itself."
    )


# --- Ollama HTTP client -------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are Gemma, the caregiver-support assistant for Emergyx Care. "
    "You ONLY use the structured local data provided in the user message. "
    "Rules:\n"
    "- Never diagnose. Use 'likely fall' instead of 'fall' when relevant.\n"
    "- Be calm, factual, and concise. For caregiver Q&A, prefer 4 to 8 sentences.\n"
    "- If light context is given, mention it as context only — never claim darkness caused a fall.\n"
    "- If the data is simulated, mention that.\n"
    "- If there is not enough data, say so plainly.\n"
    "- Do not invent events that are not in the structured data."
)


def _ollama_num_predict(think: bool) -> int:
    return 768 if think else 512


def _call_ollama(
    prompt: str,
    *,
    think: bool = False,
    timeout: float = 45.0,
) -> tuple[str, str]:
    """Call local Ollama chat API. Raises on transport/HTTP errors so callers fall back."""
    settings = get_settings()
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    payload = {
        "model": settings.gemma_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "think": think,
        "options": {
            "temperature": 0.1,
            "num_predict": _ollama_num_predict(think),
        },
    }
    response = httpx.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    body = response.json()
    message = body.get("message", {}) or {}
    text = (message.get("content") or "").strip()
    thinking = (message.get("thinking") or "").strip()
    return (text, thinking)


def _iter_ollama_events(
    prompt: str,
    *,
    think: bool = False,
    timeout: float = 45.0,
):
    """Yield streamed thinking/content events from local Ollama chat API."""
    settings = get_settings()
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    payload = {
        "model": settings.gemma_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": True,
        "think": think,
        "options": {
            "temperature": 0.1,
            "num_predict": _ollama_num_predict(think),
        },
    }

    with httpx.stream("POST", url, json=payload, timeout=timeout) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            body = json.loads(line)
            message = (body.get("message", {}) or {})
            thinking_delta = message.get("thinking") or ""
            if thinking_delta:
                yield {"type": "thinking", "delta": thinking_delta}
            content_delta = message.get("content") or ""
            if content_delta:
                yield {"type": "chunk", "delta": content_delta}


def _try_gemma(
    prompt: str,
    *,
    think: bool = False,
) -> tuple[str | None, str, str, bool]:
    """Returns (text_or_none, thinking_text, model_label, used_mock)."""
    settings = get_settings()
    model_label = f"mock:{settings.gemma_model}"
    if not settings.gemma_enabled:
        return (None, "", model_label, True)
    try:
        text, thinking = _call_ollama(prompt, think=think)
        if not text:
            LOGGER.info("Ollama returned empty body, falling back to deterministic text.")
            return (None, thinking, model_label, True)
        return (text, thinking, settings.gemma_model, False)
    except Exception as exc:
        LOGGER.warning("Ollama unavailable, falling back to deterministic text: %s", exc)
        return (None, "", model_label, True)


def _generate_agent_text(
    prompt: str,
    fallback_text: str,
    *,
    think: bool = False,
    validator: Callable[[str], bool] | None = None,
) -> tuple[str, str, str, bool]:
    text, thinking, model_label, used_mock = _try_gemma(prompt, think=think)
    if (
        text is not None
        and not _meta_response_detected(text)
        and (validator is None or validator(text))
    ):
        return (text, thinking, model_label, used_mock)

    if text is not None:
        LOGGER.info("Gemma returned a meta or low-quality answer; retrying with stricter prompt.")
        retry_text, retry_thinking, retry_model_label, retry_used_mock = _try_gemma(
            _strict_retry_prompt(prompt),
            think=think,
        )
        if (
            retry_text is not None
            and not _meta_response_detected(retry_text)
            and (validator is None or validator(retry_text))
        ):
            return (retry_text, retry_thinking, retry_model_label, retry_used_mock)

    settings = get_settings()
    return (fallback_text, "", f"mock:{settings.gemma_model}", True)


def _incident_answer_is_usable(text: str) -> bool:
    lower = text.lower()
    return "likely fall" in lower and len(text.split()) >= 18


def _qa_answer_is_usable(text: str) -> bool:
    lower = text.lower()
    if _meta_response_detected(text):
        return False
    if len(text.split()) < 12:
        return False
    if "what would you like me to do" in lower:
        return False
    return True


def _chunk_text(text: str, *, target_size: int = 72) -> list[str]:
    clean = text.strip()
    if not clean:
        return []
    words = clean.split()
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > target_size:
            chunks.append(current + " ")
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _format_chat_history(history: list[dict[str, str]] | None) -> str:
    if not history:
        return "No prior conversation."
    lines: list[str] = []
    for item in history[-4:]:
        role = "Caregiver" if item.get("role") == "user" else "Assistant"
        content = " ".join((item.get("content") or "").split())
        if not content:
            continue
        lines.append(f"{role}: {content[:180]}")
    return "\n".join(lines) if lines else "No prior conversation."


def _format_snapshot_for_prompt(snapshot: dict[str, Any]) -> str:
    stats = snapshot.get("today_stats") or {}
    person = snapshot.get("latest_person") or {}
    fall = snapshot.get("latest_fall") or {}
    light = snapshot.get("latest_light")
    parts = [
        f"Mode: {snapshot.get('mode', '?')}.",
        f"Date: {snapshot.get('date', '?')}.",
        f"Today's totals: {stats.get('total_events_today', 0)} events and {stats.get('fall_events_today', 0)} likely-fall events.",
    ]
    if person:
        parts.append(
            f"Latest person state: {person.get('value', '?')} at {person.get('timestamp', '?')} in {_format_room_name(person.get('room_label') or person.get('room'))}."
        )
    if fall:
        parts.append(
            f"Latest fall state: {fall.get('value', '?')} at {fall.get('timestamp', '?')}."
        )
    if light:
        parts.append(_format_light_line(light))
    vitals = snapshot.get("latest_vitals")
    if vitals:
        parts.append(_format_vitals_for_prompt(vitals))
    return " ".join(parts)


def _format_evidence_for_prompt(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return "- No matching local evidence found."
    lines: list[str] = []
    for item in evidence[:4]:
        text = " ".join(str(item.get("text", "")).split())[:180]
        lines.append(
            f"- [{item.get('kind', '?')}] {item.get('label', '?')} @ "
            f"{item.get('timestamp', '?')}: {text}"
        )
    return "\n".join(lines)


def _daily_report_is_usable(text: str) -> bool:
    if len(text.split()) < 24:
        return False
    required_sections = ("executive summary", "key incidents", "daily signals", "caregiver recommendations", "note")
    lower = text.lower()
    return all(section in lower for section in required_sections)


def _trend_analysis_is_usable(text: str) -> bool:
    if len(text.split()) < 20:
        return False
    if _meta_response_detected(text):
        return False
    return True


# --- AgentDecision persistence ------------------------------------------------

def _save_agent_decision(
    session: Session,
    *,
    decision_type: str,
    related_event_id: int | None,
    input_summary: str,
    output_text: str,
    model_name: str,
    used_mock: bool,
    tools_used: list[str],
) -> AgentDecision:
    decision = AgentDecision(
        timestamp=current_timestamp(),
        related_event_id=related_event_id,
        decision_type=decision_type,
        input_summary=input_summary[:500],
        output_text=output_text,
        model_name=model_name,
        metadata_json=json.dumps(
            {"used_mock": used_mock, "tools_used": tools_used},
            sort_keys=True,
            default=str,
        ),
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return decision


# --- Feature 1: explain a single fall incident with full reconstruction -------

def _format_incident_for_prompt(incident: dict[str, Any]) -> str:
    event = incident.get("event") or {}
    before_person = incident.get("person_before")
    after_person = incident.get("after_person")
    after_fall_clear = incident.get("fall_clear_after")
    alert = incident.get("alert")
    light = incident.get("light_context")
    summary_lines = incident.get("summary") or []

    parts = [
        f"Incident source: {incident.get('source', '?')}.",
        f"Likely fall event: {event.get('timestamp', '?')} in {incident.get('room', '?')}.",
    ]
    if before_person:
        parts.append(
            f"Last person-present=true before incident: {before_person.get('timestamp', '?')}."
        )
    if after_person:
        parts.append(
            f"Next person-present event after incident: {after_person.get('timestamp', '?')} value={after_person.get('value', '?')}."
        )
    if after_fall_clear:
        parts.append(
            f"Fall state cleared at {after_fall_clear.get('timestamp', '?')} value={after_fall_clear.get('value', '?')}."
        )
    if incident.get("duration_seconds") is not None:
        parts.append(f"Fall-state duration: about {incident['duration_seconds']} seconds.")
    if light:
        parts.append(_format_light_line(light))
    if alert:
        parts.append(
            f"Alert record: {alert.get('alert_type', '?')} via {alert.get('sent_channel', '?')} "
            f"(sent_success={alert.get('sent_success', '?')})."
        )
    if summary_lines:
        parts.append("Timeline summary:")
        parts.extend(f"- {line}" for line in summary_lines[:4])
    return "\n".join(parts)


def _mock_incident_explanation(incident: dict[str, Any]) -> str:
    summary_lines = incident.get("summary") or []
    bullet_block = "\n".join(f"• {line}" for line in summary_lines)
    light_note = ""
    light = incident.get("light_context")
    if light:
        light_note = (
            f"\nThe room was categorized as {light.get('category', 'unknown')}"
            " at the time. This is context only, not a cause."
        )
    sim_note = ""
    if incident.get("source") and incident["source"] != "live_sensor":
        sim_note = f"\nNote: this incident has source '{incident['source']}', not live sensor."
    return (
        "Likely fall summary (deterministic fallback — Ollama not available):\n"
        f"{bullet_block}"
        f"{light_note}"
        f"{sim_note}\n\n"
        "Emergyx Care is a prototype caregiver-support tool, not a medical device. "
        "Please check on the person directly."
    )


def explain_incident(
    session: Session,
    *,
    event_id: int | None = None,
    source_filter: str | None = None,
) -> dict[str, Any]:
    """Build incident reconstruction → ask Gemma → return caregiver-friendly text.

    If `event_id` is None, the latest fall_detected=true event matching
    `source_filter` is used.
    """
    if event_id is None:
        from app.services.events import get_latest_true_fall_event

        latest = get_latest_true_fall_event(session, source_filter)
        if latest is None or latest.id is None:
            scope = " (live mode)" if source_filter == "live_sensor" else ""
            return {
                "success": False,
                "used_mock": True,
                "model_name": "none",
                "tools_used": ["incidents"],
                "text": f"No fall_detected=true event has been recorded yet{scope}.",
                "incident": None,
            }
        event_id = latest.id

    incident = get_incident_context(session, event_id, source_filter=source_filter)
    if incident is None:
        return {
            "success": False,
            "used_mock": True,
            "model_name": "none",
            "tools_used": ["incidents"],
            "text": f"No event found for id={event_id}.",
            "incident": None,
        }

    prompt = (
        "Write a caregiver-facing explanation of the incident below.\n"
        "Rules:\n"
        "- 4 short sentences maximum.\n"
        "- Sentence 1 must directly summarize the likely fall with room and time.\n"
        "- Mention before/after timeline details only if they help.\n"
        "- If light context is present, mention it as context only, never as a cause.\n"
        "- End with a direct caregiver check-in recommendation.\n"
        "- Mention that Emergyx Care is a prototype caregiver-support tool, not a medical device.\n"
        "- Do not mention JSON, structured data, prompts, or tools.\n\n"
        f"FACTS:\n{_format_incident_for_prompt(incident)}"
    )

    text, _, model_label, used_mock = _generate_agent_text(
        prompt,
        _mock_incident_explanation(incident),
        validator=_incident_answer_is_usable,
    )

    related = incident.get("event") or {}
    _save_agent_decision(
        session,
        decision_type="incident_explanation",
        related_event_id=related.get("id"),
        input_summary=f"incident_event_id={related.get('id')} room={incident.get('room')} source={incident.get('source')}",
        output_text=text,
        model_name=model_label,
        used_mock=used_mock,
        tools_used=["incidents", "events", "alerts", "light_context"],
    )

    return _wrap_response(
        text=text,
        used_mock=used_mock,
        model_name=model_label,
        tools_used=["incidents", "events", "alerts", "light_context"],
        extra={"incident": incident, "explanation": text, "related_event_id": related.get("id")},
    )


# --- Feature 2: caregiver Q&A over local RAG ---------------------------------

def _mock_qa_answer(
    question: str,
    retrieval: dict[str, Any],
) -> str:
    snapshot = retrieval.get("snapshot") or {}
    stats = snapshot.get("today_stats") or {}
    light = snapshot.get("latest_light") or {}
    evidence = retrieval.get("evidence") or []
    light_str = (
        f"latest light: {light.get('category', 'unknown')}"
        + (f", {light['lux']:.1f} lux" if isinstance(light.get("lux"), (int, float)) else "")
        if light
        else "no light reading on file"
    )
    evidence_str = "; ".join(item.get("label", "?") for item in evidence[:3]) or "no matching evidence"
    return (
        "Deterministic local-data answer (Ollama not available):\n"
        f"Question received: {question!r}.\n"
        f"Today ({snapshot.get('date', '?')}): {stats.get('total_events_today', 0)} events, "
        f"{stats.get('fall_events_today', 0)} likely-fall events.\n"
        f"{light_str}.\n"
        f"Most relevant local context: {evidence_str}.\n"
        "Emergyx Care is a prototype caregiver-support tool, not a medical device."
    )


def _caregiver_qa_prompt(
    *,
    question: str,
    retrieval: dict[str, Any],
    conversation_history: list[dict[str, str]] | None,
    think: bool,
) -> tuple[str, dict[str, Any], list[dict[str, Any]], list[str]]:
    snapshot = retrieval.get("snapshot") or {}
    evidence = retrieval.get("evidence") or []
    tools_used = retrieval.get(
        "tools_used",
        ["events", "alerts", "incidents", "reports", "light_context", "vitals", "care_context"],
    )
    verbosity_instruction = (
        "Take time to reason before answering. Then give a fuller caregiver answer in 4 to 8 sentences unless the question truly only needs a brief yes/no answer. "
        if think
        else "Answer directly for the caregiver in 3 to 5 sentences. "
    )
    if _is_greeting_question(question):
        prompt = (
            f"A caregiver says: {question.strip()}\n"
            "You are Gemma, the Emergyx Care caregiver-support assistant. "
            "Reply with a brief friendly greeting and ask what they want to check, such as live sensor status, incidents, reports, or resident context. "
            "Do not summarize safety data, sensor readings, incidents, or reports unless the caregiver asks for them."
        )
        return prompt, {}, [], ["gemma_chat"]

    prompt = (
        f"A caregiver asks: {question.strip()}\n"
        f"{verbosity_instruction}"
        "You are Gemma. Generate the caregiver-facing answer yourself using only the local evidence below. "
        "Do not mention JSON, structured data, prompts, or tools. "
        "If the caregiver only greets you or says hello, reply briefly as Gemma and ask what they want to check; do not summarize sensor data unless they ask for it. "
        "If there were no likely falls today, say that clearly. "
        "For heart-rate or breathing-rate questions, use the Current vitals section and do not report zero, out-of-range, stale, or missing values as current live vital signs. "
        "For resident, room, sensor, or context questions, use the care-context evidence and saved room labels. "
        "If the question asks about cause, say the system cannot determine cause from this data alone. "
        "If the question asks about urgency, separate the rule-based alert from the explanatory AI layer. "
        "Start with the direct answer in the first sentence, then add the most relevant supporting context. "
        "Mention that Emergyx Care is not a medical device only if that warning is relevant.\n\n"
        f"Conversation so far:\n{_format_chat_history(conversation_history)}\n\n"
        f"Mode snapshot:\n{_format_snapshot_for_prompt(snapshot)}\n\n"
        f"Retrieved local evidence:\n{_format_evidence_for_prompt(evidence)}"
    )
    return prompt, snapshot, evidence, tools_used


def answer_caregiver_question(
    session: Session,
    *,
    question: str,
    source_filter: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    think: bool = False,
) -> dict[str, Any]:
    if not question or not question.strip():
        return {
            "success": False,
            "used_mock": False,
            "model_name": "none",
            "tools_used": [],
            "text": "Please provide a question.",
        }

    retrieval = retrieve_local_context(
        session,
        question=question,
        source_filter=source_filter,
    )
    prompt, snapshot, evidence, tools_used = _caregiver_qa_prompt(
        question=question,
        retrieval=retrieval,
        conversation_history=conversation_history,
        think=think,
    )

    settings = get_settings()
    if not settings.gemma_enabled:
        raise RuntimeError("Gemma/Ollama chat is disabled. Enable Gemma in Settings before using chat.")
    text, thinking_text = _call_ollama(prompt, think=think)
    if not text:
        raise RuntimeError("Gemma/Ollama returned an empty chat response.")
    if _meta_response_detected(text):
        retry_text, retry_thinking = _call_ollama(_strict_retry_prompt(prompt), think=think)
        if retry_text:
            text = retry_text
            thinking_text = retry_thinking

    _save_agent_decision(
        session,
        decision_type="caregiver_qa",
        related_event_id=None,
        input_summary=f"question={question[:240]}",
        output_text=text,
        model_name=settings.gemma_model,
        used_mock=False,
        tools_used=retrieval.get("tools_used", ["events", "alerts", "incidents", "reports", "light_context"]),
    )

    return _wrap_response(
        text=text,
        used_mock=False,
        model_name=settings.gemma_model,
        tools_used=tools_used,
        extra={
            "answer": text,
            "question": question,
            "evidence": evidence,
            "snapshot": snapshot,
            "thinking": thinking_text or None,
        },
    )


def stream_answer_caregiver_question(
    session: Session,
    *,
    question: str,
    source_filter: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    think: bool = False,
):
    if not question or not question.strip():
        yield {"type": "error", "error": "Please provide a question."}
        return None

    retrieval = retrieve_local_context(
        session,
        question=question,
        source_filter=source_filter,
    )
    tools_used = retrieval.get(
        "tools_used",
        ["events", "alerts", "incidents", "reports", "light_context"],
    )
    prompt, snapshot, evidence, tools_used = _caregiver_qa_prompt(
        question=question,
        retrieval=retrieval,
        conversation_history=conversation_history,
        think=think,
    )

    settings = get_settings()
    model_label = settings.gemma_model
    parts: list[str] = []
    thinking_parts: list[str] = []

    if not settings.gemma_enabled:
        yield {"type": "error", "error": "Gemma/Ollama chat is disabled. Enable Gemma in Settings before using chat."}
        return None

    try:
        for event in _iter_ollama_events(prompt, think=think):
            if event.get("type") == "thinking":
                delta = str(event.get("delta") or "")
                if delta:
                    thinking_parts.append(delta)
                    yield {"type": "thinking", "delta": delta}
                continue

            delta = str(event.get("delta") or "")
            if delta:
                parts.append(delta)
                yield {"type": "chunk", "delta": delta}
    except Exception as exc:
        LOGGER.warning("Ollama streaming unavailable for chat: %s", exc)
        yield {"type": "error", "error": f"Gemma/Ollama chat failed: {exc}"}
        return None

    text = "".join(parts).strip()
    if not text:
        yield {"type": "error", "error": "Gemma/Ollama returned an empty chat response."}
        return None

    thinking_text = "".join(thinking_parts).strip() or None

    _save_agent_decision(
        session,
        decision_type="caregiver_qa",
        related_event_id=None,
        input_summary=f"question={question[:240]}",
        output_text=text,
        model_name=model_label,
        used_mock=False,
        tools_used=tools_used,
    )

    return _wrap_response(
        text=text,
        used_mock=False,
        model_name=model_label,
        tools_used=tools_used,
        extra={
            "answer": text,
            "question": question,
            "evidence": evidence,
            "snapshot": snapshot,
            "thinking": thinking_text,
        },
    )


# --- Feature 3: daily caregiver report ----------------------------------------

def _build_daily_context(
    session: Session,
    date_str: str,
    source_filter: str | None = None,
) -> dict[str, Any]:
    events = list_events_for_date(session, date_str, source_filter=source_filter)
    alerts = list_alerts_for_date(session, date_str, source_filter=source_filter)
    incidents = get_incidents_for_date(session, date_str, source_filter=source_filter)
    light = get_latest_light_context(session, source_filter=source_filter)

    fall_true_count = sum(
        1 for ev in events if ev.event_type == "fall_detected" and ev.value == "true"
    )
    person_present_count = sum(
        1 for ev in events if ev.event_type == "person_present" and ev.value == "true"
    )

    return {
        "date": date_str,
        "mode": "live_sensor_only" if source_filter == "live_sensor" else "all_sources",
        "care_context": load_runtime_care_context(),
        "totals": {
            "events": len(events),
            "alerts": len(alerts),
            "likely_falls": fall_true_count,
            "person_present_events": person_present_count,
        },
        "incidents": incidents,
        "alerts": [
            {
                "id": a.id,
                "ts": a.timestamp,
                "type": a.alert_type,
                "severity": a.severity,
                "channel": a.sent_channel,
                "sent_success": a.sent_success,
            }
            for a in alerts
        ],
        "latest_light": light,
        "sources": sorted({ev.source for ev in events}),
    }


def _format_daily_context_for_prompt(ctx: dict[str, Any]) -> str:
    totals = ctx.get("totals") or {}
    incidents = ctx.get("incidents") or []
    alerts = ctx.get("alerts") or []
    parts = [
        f"Date: {ctx.get('date', '?')}.",
        f"Mode: {ctx.get('mode', '?')}.",
        f"Totals: {totals.get('events', 0)} events, {totals.get('likely_falls', 0)} likely falls, "
        f"{totals.get('alerts', 0)} alerts, {totals.get('person_present_events', 0)} person-present events.",
        _format_light_line(ctx.get('latest_light')),
        f"Sources seen today: {', '.join(ctx.get('sources') or []) or 'none'}.",
        "Incidents:",
    ]
    if incidents:
        parts.extend(_format_incident_line(incident) for incident in incidents[:5])
    else:
        parts.append("- No likely-fall incidents recorded.")
    parts.append("Alerts:")
    if alerts:
        parts.extend(_format_alert_line(alert) for alert in alerts[:5])
    else:
        parts.append("- No alerts recorded.")
    return "\n".join(parts)


def _format_daily_context_natural_language(ctx: dict[str, Any]) -> str:
    totals = ctx.get("totals") or {}
    parts = [
        f"The report date is {ctx.get('date', '?')}.",
        f"The app is in {ctx.get('mode', '?')} mode.",
        f"There were {totals.get('events', 0)} events, {totals.get('likely_falls', 0)} likely-fall events, {totals.get('alerts', 0)} alerts, and {totals.get('person_present_events', 0)} person-present events.",
    ]

    incidents = ctx.get("incidents") or []
    if incidents:
        first = incidents[0]
        event = first.get("event") or {}
        parts.append(
            f"A likely fall was recorded at {event.get('timestamp', '?')} in {_format_room_name(first.get('room'))}."
        )
    else:
        parts.append("No likely falls were recorded.")

    light = ctx.get("latest_light")
    if light:
        parts.append(
            f"The latest light context was {light.get('category', 'unknown')} at {_format_lux(light.get('lux'))} in {_format_room_name(light.get('room'))}."
        )

    sources = ", ".join(ctx.get("sources") or []) or "none"
    parts.append(f"Event sources seen today: {sources}.")

    care_context = ctx.get("care_context") or {}
    residents = care_context.get("residents") or []
    sensor_contexts = care_context.get("sensor_contexts") or {}
    if residents:
        resident_bits = []
        for resident in residents[:3]:
            rooms = ", ".join(_format_room_name(room) for room in resident.get("rooms", [])) or "no assigned rooms"
            context = resident.get("context") or "no extra context"
            resident_bits.append(f"{resident.get('name', 'Resident')}: rooms {rooms}; context: {context}")
        parts.append("Resident context: " + " | ".join(resident_bits) + ".")
    if sensor_contexts:
        sensor_bits = [f"{sensor_id}: {context}" for sensor_id, context in list(sensor_contexts.items())[:4]]
        parts.append("Sensor context: " + " | ".join(sensor_bits) + ".")
    return " ".join(parts)


def _mock_daily_report(ctx: dict[str, Any]) -> str:
    totals = ctx["totals"]
    incidents = ctx.get("incidents") or []
    light = ctx.get("latest_light") or {}
    light_part = ""
    if light:
        light_part = (
            f"Light context near the end of the day: {light.get('category', 'unknown')}"
            + (f" ({light['lux']:.1f} lux)" if isinstance(light.get("lux"), (int, float)) else "")
            + f" in {_format_room_name(light.get('room'))}"
            + ".\n"
        )

    incident_lines: list[str] = []
    for inc in incidents:
        when = (inc.get("event") or {}).get("timestamp", "?")
        room = _format_room_name(inc.get("room"))
        dur = inc.get("duration_seconds")
        if dur is not None:
            incident_lines.append(f"• Likely fall at {when} in {room}, fall state lasted ~{dur}s.")
        else:
            incident_lines.append(f"• Likely fall at {when} in {room}.")
    incidents_block = "\n".join(incident_lines) if incident_lines else "• No likely-fall incidents recorded."

    sources_str = ", ".join(ctx.get("sources") or []) or "none"

    return (
        f"Daily Caregiver Report — {ctx['date']}\n\n"
        f"Totals: {totals['events']} events, {totals['likely_falls']} likely falls, "
        f"{totals['alerts']} caregiver alerts.\n\n"
        f"Incidents:\n{incidents_block}\n\n"
        f"{light_part}"
        f"Event sources today: {sources_str}.\n\n"
        "Emergyx Care is a prototype caregiver-support tool, not a medical device. "
        "Alert behavior depends on the configured notification mode; this summary is for caregiver context."
    )


def generate_daily_report(
    session: Session,
    *,
    date_str: str | None = None,
    persist: bool = True,
    source_filter: str | None = None,
) -> dict[str, Any]:
    if date_str is None:
        date_str = current_date()

    ctx = _build_daily_context(session, date_str, source_filter=source_filter)
    mode = "live" if source_filter == "live_sensor" else "demo"
    prompt = (
        "Write a polished caregiver-facing daily report using exactly these headings: Executive Summary, Key Incidents, Daily Signals, Caregiver Recommendations, Note. "
        "Say clearly whether any likely falls were recorded. "
        "Use readable room names exactly as provided; never output raw room ids such as auto_room_157. "
        "Refer to continuous readings as sensor readings, not all as incidents. "
        "Mention light as context only. "
        "Give practical caregiver actions only if there were likely falls or alerts. "
        "Mention that Emergyx Care is a prototype caregiver-support tool and not a medical device. "
        "Do not mention JSON or data formatting.\n\n"
        f"Facts: {_format_daily_context_natural_language(ctx)}"
    )

    text, _, model_label, used_mock = _generate_agent_text(
        prompt,
        _mock_daily_report(ctx),
        validator=_daily_report_is_usable,
    )

    saved_id: int | None = None
    if persist:
        report = DailyReport(
            date=date_str,
            report_text=text,
            created_at=current_timestamp(),
            metadata_json=json.dumps(
                {
                    "used_mock": used_mock,
                    "model_name": model_label,
                    "mode": mode,
                    "totals": ctx["totals"],
                    "incident_count": len(ctx.get("incidents") or []),
                },
                sort_keys=True,
                default=str,
            ),
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        saved_id = report.id

        _save_agent_decision(
            session,
            decision_type="daily_report",
            related_event_id=None,
            input_summary=f"date={date_str} totals={ctx['totals']}",
            output_text=text,
            model_name=model_label,
            used_mock=used_mock,
            tools_used=["events_for_date", "alerts_for_date", "incidents_for_date", "light_context"],
        )

    return _wrap_response(
        text=text,
        used_mock=used_mock,
        model_name=model_label,
        tools_used=["events_for_date", "alerts_for_date", "incidents_for_date", "light_context"],
        extra={
            "report": text,
            "report_id": saved_id,
            "date": date_str,
            "context": ctx,
        },
    )


# --- Feature 4: trend analysis over local SQLite timeline ---------------------

def _format_trends_for_prompt(trends: dict[str, Any]) -> str:
    metrics = trends.get("metrics") or {}
    fall = metrics.get("fall_count") or {}
    alerts = metrics.get("alerts_sent") or {}
    night = metrics.get("nighttime_movement_count") or {}
    events = metrics.get("event_count") or {}
    light = trends.get("light") or {}
    activity = trends.get("activity") or {}
    freshness = trends.get("freshness") or {}
    notable = trends.get("notable_changes") or []
    lines = [
        f"Mode: {trends.get('mode', '?')}.",
        (
            "Window: today "
            f"{(trends.get('window') or {}).get('today', '?')} vs baseline "
            f"{(trends.get('window') or {}).get('baseline_start', '?')} to "
            f"{(trends.get('window') or {}).get('baseline_end', '?')}."
        ),
        (
            "Likely falls: today "
            f"{fall.get('today', 0)} vs baseline average {fall.get('baseline_average', 0)}."
        ),
        (
            "Alerts sent: today "
            f"{alerts.get('today', 0)} vs baseline average {alerts.get('baseline_average', 0)}."
        ),
        (
            "Night movement: today "
            f"{night.get('today', 0)} vs baseline average {night.get('baseline_average', 0)}."
        ),
        (
            "Events: today "
            f"{events.get('today', 0)} vs baseline average {events.get('baseline_average', 0)}."
        ),
        (
            "Light context: latest "
            f"{light.get('latest_category', 'unknown')} "
            f"({light.get('latest_lux', 'n/a')} lux), today average "
            f"{light.get('today_average_category', 'unknown')}."
        ),
        (
            "Last activity: "
            f"{activity.get('last_activity_age_human', 'unknown')} "
            f"(staleness={activity.get('last_activity_staleness', 'unknown')})."
        ),
        (
            "Sensor freshness: "
            f"{freshness.get('stale_sensor_count', 0)} stale/warn sensors."
        ),
    ]
    if notable:
        lines.append("Notable changes:")
        for item in notable[:4]:
            lines.append(
                f"- [{item.get('severity', 'info')}] {item.get('title', '?')}: {item.get('detail', '')}"
            )
    return "\n".join(lines)


def _mock_trend_analysis(trends: dict[str, Any]) -> str:
    summary = summarize_trends_for_humans(trends)
    notable = trends.get("notable_changes") or []
    warning_items = [item for item in notable if item.get("severity") == "warning"]
    details = ""
    if warning_items:
        details = "\n".join(
            f"- {item.get('title')}: {item.get('detail')}" for item in warning_items[:3]
        )
        details = f"\nNotable changes:\n{details}\n"
    else:
        details = "\nNo unusual changes were flagged in the local trend rules.\n"
    return (
        "Trend analysis (deterministic fallback — Ollama not available):\n"
        f"{summary}\n"
        f"{details}\n"
        "These trend signals are caregiver context only and do not diagnose cause. "
        "Emergyx Care is a prototype caregiver-support tool, not a medical device."
    )


def analyze_trends(
    session: Session,
    *,
    mode: str,
    source_filter: str | None,
    night_start_hour: int | None = None,
    night_end_hour: int | None = None,
) -> dict[str, Any]:
    trends = get_today_trends(
        session,
        mode=mode,
        source_filter=source_filter,
        night_start_hour=night_start_hour,
        night_end_hour=night_end_hour,
    )
    prompt = (
        "Write a caregiver-friendly trend analysis from local trend facts only.\n"
        "Rules:\n"
        "- 4 to 7 sentences.\n"
        "- Use conservative wording. If mentioning a fall, say likely fall.\n"
        "- Do not diagnose, do not claim medical certainty, and do not infer cause.\n"
        "- Mention unusual changes only if they are in the notable change list.\n"
        "- Mention limited data plainly when metrics are sparse or no unusual changes are present.\n"
        "- Include a short reminder that Emergyx Care is not a medical device.\n"
        "- Do not mention JSON, prompts, tools, or internal formatting.\n\n"
        f"FACTS:\n{_format_trends_for_prompt(trends)}"
    )

    text, _, model_label, used_mock = _generate_agent_text(
        prompt,
        _mock_trend_analysis(trends),
        validator=_trend_analysis_is_usable,
    )

    _save_agent_decision(
        session,
        decision_type="trend_analysis",
        related_event_id=None,
        input_summary=(
            f"mode={mode} night_window={trends.get('night_window')} "
            f"unusual_detected={trends.get('unusual_detected')}"
        ),
        output_text=text,
        model_name=model_label,
        used_mock=used_mock,
        tools_used=["trends", "events", "alerts", "light_context", "freshness"],
    )

    return _wrap_response(
        text=text,
        used_mock=used_mock,
        model_name=model_label,
        tools_used=["trends", "events", "alerts", "light_context", "freshness"],
        extra={
            "analysis": text,
            "trends": trends,
        },
    )


# --- Status snapshot for dashboard / health checks ----------------------------

def gemma_status_snapshot() -> dict[str, Any]:
    settings = get_settings()
    snapshot: dict[str, Any] = {
        "gemma_enabled": settings.gemma_enabled,
        "model": settings.gemma_model,
        "ollama_base_url": settings.ollama_base_url,
        "checked_at": current_timestamp(),
    }
    if not settings.gemma_enabled:
        snapshot["status"] = "disabled"
        snapshot["reachable"] = False
        return snapshot

    try:
        resp = httpx.get(
            f"{settings.ollama_base_url.rstrip('/')}/api/tags", timeout=2.5
        )
        resp.raise_for_status()
        snapshot["status"] = "online"
        snapshot["reachable"] = True
        try:
            snapshot["installed_models"] = [
                m.get("name") for m in resp.json().get("models", []) if m.get("name")
            ][:10]
        except Exception:
            pass
    except Exception as exc:
        snapshot["status"] = "unreachable"
        snapshot["reachable"] = False
        snapshot["error"] = str(exc)
    return snapshot


# --- Backward compatibility shim ---------------------------------------------

def explain_event(session: Session, event: Any) -> dict[str, Any]:
    """Deprecated: prefer explain_incident(session, event_id=...).

    Kept so the existing /agent/explain-latest router and any external callers
    continue to work while we migrate.
    """
    event_id = getattr(event, "id", None)
    result = explain_incident(session, event_id=event_id)
    # Translate to the older AgentExplainResponse shape used by routers.
    return {
        "success": result.get("success", False),
        "used_mock": result.get("used_mock", True),
        "model_name": result.get("model_name", "none"),
        "explanation": result.get("text", ""),
        "related_event_id": event_id,
    }


__all__ = [
    "analyze_trends",
    "answer_caregiver_question",
    "explain_event",
    "explain_incident",
    "gemma_status_snapshot",
    "generate_daily_report",
]


_ = datetime  # keep importable for callers building timestamps
