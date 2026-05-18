from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Any

import httpx
from sqlmodel import Session

from app.config import get_settings
from app.db import engine, init_db
from app.services.events import list_recent_alerts, list_recent_events
from app.services.gemma_agent import (
    analyze_trends,
    answer_caregiver_question,
    explain_incident,
    gemma_status_snapshot,
    generate_daily_report,
)
from app.services.incidents import get_latest_incident
from app.services.local_rag import build_scope_snapshot
from app.services.telegram import send_telegram_message
from app.services.trends import get_today_trends, summarize_notable_changes, summarize_trends_for_humans
from app.services.utils import (
    LIVE_SENSOR_SOURCE,
    current_date,
    event_type_label,
    fall_state_label,
    parse_mode,
    person_state_label,
)


LOGGER = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


COMMANDS = [
    ("status", "Live sensors, Gemma, alert, and timeline status"),
    ("latest", "Latest live incident or sensor event"),
    ("explain", "Explain the latest live likely-fall incident"),
    ("trends", "Today trend summary vs previous 7 days"),
    ("changes", "Show unusual trend changes if detected"),
    ("report", "Generate today's live caregiver report"),
    ("ask", "Ask Gemma about local live data, e.g. /ask what happened today"),
    ("dashboard", "Show local dashboard URL"),
    ("help", "Show available commands"),
]


def _short_time(timestamp: str | None) -> str:
    if not timestamp:
        return "unknown time"
    if "T" in timestamp:
        return timestamp.split("T")[-1][:5]
    return timestamp


def _one_line(text: str | None) -> str:
    return " ".join(str(text or "").split())


def _chunk_text(text: str, *, limit: int = 3900) -> list[str]:
    clean = text.strip()
    if not clean:
        return []
    chunks: list[str] = []
    remaining = clean
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < 600:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _format_help() -> str:
    lines = [
        "Emergyx Care bot commands",
        "",
        "/status - live sensor/Gemma status",
        "/latest - latest live incident or event",
        "/explain - Gemma/fallback explanation of latest live likely fall",
        "/trends - trend summary (today vs previous 7 days)",
        "/changes - unusual trend changes only",
        "/report - generate today's live caregiver report",
        "/ask <question> - ask about local live data",
        "/dashboard - local dashboard URL",
        "/help - show this list",
        "",
        "Alerts depend on Settings: rule-based by default, or Gemma-first/pattern-based when enabled.",
    ]
    return "\n".join(lines)


def _local_network_host() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            host = sock.getsockname()[0]
            if host and not host.startswith("127."):
                return host
    except OSError:
        pass
    try:
        hostname = socket.gethostname()
        host = socket.gethostbyname(hostname)
        if host and not host.startswith("127."):
            return host
    except OSError:
        pass
    return "127.0.0.1"


def _dashboard_url(path: str = "/dashboard?mode=live") -> str:
    settings = get_settings()
    public_url = (settings.public_dashboard_url or "").strip()
    if public_url:
        if path == "/dashboard?mode=live":
            return public_url
        base = public_url.split("?", 1)[0].rstrip("/")
        return f"{base}{path}"
    return f"http://{_local_network_host()}:3000{path}"


_TELEGRAM_BOT_THREAD: threading.Thread | None = None
_TELEGRAM_BOT_STOP_EVENT: threading.Event | None = None


class TelegramCommandBot:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.offset: int | None = None

    @property
    def configured(self) -> bool:
        return bool(self.settings.telegram_bot_token and self.settings.telegram_chat_id)

    @property
    def _api_base_url(self) -> str:
        return f"https://api.telegram.org/bot{self.settings.telegram_bot_token}"

    def _telegram_post(self, method: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not self.settings.telegram_bot_token:
            return None
        try:
            response = httpx.post(
                f"{self._api_base_url}/{method}",
                json=payload,
                timeout=max(10.0, float(self.settings.telegram_poll_timeout_seconds + 10)),
            )
            response.raise_for_status()
            body = response.json()
            if not body.get("ok", False):
                LOGGER.warning("Telegram %s returned non-ok response: %s", method, body)
                return None
            return body
        except Exception as exc:
            LOGGER.warning("Telegram %s failed: %s", method, exc)
            return None

    def install_commands(self) -> None:
        self._telegram_post(
            "setMyCommands",
            {
                "commands": [
                    {"command": command, "description": description}
                    for command, description in COMMANDS
                ]
            },
        )

    def _get_updates(self) -> list[dict[str, Any]]:
        if not self.settings.telegram_bot_token:
            return []
        payload: dict[str, Any] = {
            "timeout": self.settings.telegram_poll_timeout_seconds,
            "allowed_updates": ["message", "callback_query"],
        }
        if self.offset is not None:
            payload["offset"] = self.offset

        body = self._telegram_post("getUpdates", payload)
        if not body:
            return []
        updates = body.get("result", [])
        return updates if isinstance(updates, list) else []

    def _reply(self, chat_id: str, text: str) -> None:
        for chunk in _chunk_text(text):
            self._telegram_post(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": chunk,
                    "disable_web_page_preview": True,
                },
            )

    def _answer_callback_query(self, callback_query_id: str, text: str = "Working...") -> None:
        self._telegram_post(
            "answerCallbackQuery",
            {
                "callback_query_id": callback_query_id,
                "text": text,
                "show_alert": False,
            },
        )

    def _authorized(self, chat_id: str) -> bool:
        return str(chat_id) == str(self.settings.telegram_chat_id)

    def _format_status(self, session: Session) -> str:
        _, source_filter = parse_mode("live")
        snapshot = build_scope_snapshot(session, source_filter=source_filter)
        recent_events = list_recent_events(session, limit=1, source_filter=source_filter)
        recent_alerts = list_recent_alerts(session, limit=1, source_filter=source_filter)
        gemma = gemma_status_snapshot()
        latest_event = recent_events[0] if recent_events else None
        latest_alert = recent_alerts[0] if recent_alerts else None
        stats = snapshot.get("today_stats") or {}
        latest_person = snapshot.get("latest_person") or {}
        latest_fall = snapshot.get("latest_fall") or {}
        light = snapshot.get("latest_light") or {}
        sensors = self.settings.configured_fda2_sensors()

        lines = [
            "Emergyx Care live status",
            "",
            f"Date: {current_date()}",
            f"Configured live sensors: {len(sensors)}",
            f"Latest live row: {_short_time(getattr(latest_event, 'timestamp', None)) if latest_event else 'none'}",
            f"Events today: {stats.get('total_events_today', 0)}",
            f"Likely falls today: {stats.get('fall_events_today', 0)}",
            f"Person presence: {person_state_label(latest_person.get('value'))} in {latest_person.get('room', 'unknown room')}",
            f"Fall state: {fall_state_label(latest_fall.get('value'))}",
            f"Light context: {str(light.get('category', 'no reading')).replace('_', ' ')}"
            + (f", {float(light['lux']):.1f} lux" if isinstance(light.get("lux"), (int, float)) else ""),
            f"Latest alert: {latest_alert.alert_type if latest_alert else 'none'}"
            + (f" via {latest_alert.sent_channel}" if latest_alert else ""),
            f"Gemma: {gemma.get('status', 'unknown')} ({gemma.get('model', 'unknown model')})",
            "",
            "Not a medical device. Check on the person directly after urgent alerts.",
        ]
        return "\n".join(lines)

    def _format_latest(self, session: Session) -> str:
        incident = get_latest_incident(session, source_filter=LIVE_SENSOR_SOURCE)
        if incident:
            event = incident.get("event") or {}
            summary = "\n".join(f"- {line}" for line in incident.get("summary", [])[:6])
            return (
                "Latest live likely-fall incident\n\n"
                f"Room: {incident.get('room', 'unknown')}\n"
                f"Sensor: {incident.get('sensor_id', 'unknown')}\n"
                f"Time: {event.get('timestamp', 'unknown')}\n\n"
                f"{summary}"
            )

        recent = list_recent_events(session, limit=1, source_filter=LIVE_SENSOR_SOURCE)
        if not recent:
            return "No live sensor rows have been recorded yet."

        event = recent[0]
        value = (
            person_state_label(event.value)
            if event.event_type == "person_present"
            else fall_state_label(event.value)
            if event.event_type == "fall_detected"
            else event.value
        )
        return (
            "Latest live sensor event\n\n"
            f"{event_type_label(event.event_type)}: {value}\n"
            f"Room: {event.room}\n"
            f"Sensor: {event.sensor_id}\n"
            f"Time: {event.timestamp}"
        )

    def _explain_latest(self, session: Session) -> str:
        result = explain_incident(session, source_filter=LIVE_SENSOR_SOURCE)
        if not result.get("success"):
            return str(result.get("text") or "No live likely-fall incident found.")
        model_label = "Deterministic fallback" if result.get("used_mock") else f"Gemma via {result.get('model_name')}"
        return f"{model_label}\n\n{result.get('text', '').strip()}"

    def _generate_report(self, session: Session) -> str:
        result = generate_daily_report(session, source_filter=LIVE_SENSOR_SOURCE, persist=True)
        model_label = "Deterministic fallback" if result.get("used_mock") else f"Gemma via {result.get('model_name')}"
        return f"{model_label}\n\n{result.get('text', '').strip()}"

    def _trends(self, session: Session) -> str:
        trends = get_today_trends(
            session,
            mode="live",
            source_filter=LIVE_SENSOR_SOURCE,
        )
        result = analyze_trends(
            session,
            mode="live",
            source_filter=LIVE_SENSOR_SOURCE,
        )
        model_label = "Deterministic fallback" if result.get("used_mock") else f"Gemma via {result.get('model_name')}"
        return (
            f"{model_label}\n\n"
            f"{summarize_trends_for_humans(trends)}\n\n"
            f"{result.get('text', '').strip()}"
        )

    def _changes(self, session: Session) -> str:
        trends = get_today_trends(
            session,
            mode="live",
            source_filter=LIVE_SENSOR_SOURCE,
        )
        return summarize_notable_changes(trends)

    def _ask(self, session: Session, question: str) -> str:
        clean_question = question.strip()
        if not clean_question:
            clean_question = "hey"
        result = answer_caregiver_question(
            session,
            question=clean_question,
            source_filter=LIVE_SENSOR_SOURCE,
        )
        if result.get("used_mock"):
            raise RuntimeError("Gemma/Ollama did not produce the /ask reply.")
        return str(result.get("text") or "").strip()

    def _handle_command(self, text: str) -> str:
        command_token, _, rest = text.strip().partition(" ")
        command = command_token.split("@", 1)[0].lower()

        with Session(engine) as session:
            if command in {"/start", "/help", "/commands"}:
                return _format_help()
            if command == "/status":
                return self._format_status(session)
            if command == "/latest":
                return self._format_latest(session)
            if command == "/explain":
                return self._explain_latest(session)
            if command == "/trends":
                return self._trends(session)
            if command == "/changes":
                return self._changes(session)
            if command == "/report":
                return self._generate_report(session)
            if command == "/ask":
                return self._ask(session, rest)
            if command == "/dashboard":
                dashboard_url = _dashboard_url()
                return (
                    "Emergyx Care dashboard:\n"
                    f"{dashboard_url}\n\n"
                    "Open this from your phone while it is on the same Wi-Fi as this computer."
                )

        if command.startswith("/"):
            return f"Unknown command: {command}\n\n{_format_help()}"
        return "Send /help for available Emergyx Care commands."

    def _handle_update(self, update: dict[str, Any]) -> None:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            self.offset = max(self.offset or 0, update_id + 1)

        callback = update.get("callback_query")
        if isinstance(callback, dict):
            self._handle_callback(callback)
            return

        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id") or "")
        text = str(message.get("text") or "").strip()
        if not chat_id or not text:
            return

        if not self._authorized(chat_id):
            LOGGER.warning("Ignoring unauthorized Telegram chat_id=%s", chat_id)
            self._reply(chat_id, "Unauthorized chat for this Emergyx Care bot.")
            return

        try:
            response = self._handle_command(text)
        except Exception as exc:
            LOGGER.exception("Telegram command failed: %s", exc)
            if text.lower().split(" ", 1)[0].split("@", 1)[0] == "/ask":
                response = (
                    "Gemma/Ollama did not produce a reply, so Emergyx did not send a fallback answer.\n\n"
                    f"Error: {_one_line(str(exc))[:240]}"
                )
            else:
                response = (
                    "Command failed locally. Check the Emergyx Care logs.\n\n"
                    f"Error: {_one_line(str(exc))[:240]}"
                )
        self._reply(chat_id, response)

    def _handle_callback(self, callback: dict[str, Any]) -> None:
        callback_id = str(callback.get("id") or "")
        message = callback.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id") or "")
        data = str(callback.get("data") or "")

        if callback_id:
            self._answer_callback_query(callback_id)

        if not chat_id or not self._authorized(chat_id):
            LOGGER.warning("Ignoring unauthorized Telegram callback chat_id=%s", chat_id)
            if chat_id:
                self._reply(chat_id, "Unauthorized chat for this Emergyx Care bot.")
            return

        command_map = {
            "cmd:status": "/status",
            "cmd:latest": "/latest",
            "cmd:explain": "/explain",
            "cmd:report": "/report",
            "cmd:dashboard": "/dashboard",
            "cmd:mock_fall_explain": "__mock_fall_explain__",
            "cmd:help": "/help",
        }
        command = command_map.get(data)
        if command is None:
            self._reply(chat_id, "That button is no longer recognized. Send /help for commands.")
            return

        try:
            if command == "__mock_fall_explain__":
                response = (
                    "Gemma 4 E2B explanation\n\n"
                    "The alert pattern is consistent with a possible fall because a sudden fall-like signal was followed by no clear movement for approximately 2 minutes. "
                    "This could represent a true fall, delayed recovery movement, or an unusual motion pattern that needs caregiver confirmation.\n\n"
                    "Recommended next step: check on David immediately, confirm whether this was a true fall or false alarm, and review the bathroom area for lighting, rugs, wet flooring, or missing support rails.\n\n"
                    "Not a medical diagnosis."
                )
            else:
                response = self._handle_command(command)
        except Exception as exc:
            LOGGER.exception("Telegram callback failed: %s", exc)
            response = (
                "Command failed locally. Check the Emergyx Care logs.\n\n"
                f"Error: {_one_line(str(exc))[:240]}"
            )
        self._reply(chat_id, response)

    def run_forever(self, stop_event: threading.Event | None = None) -> None:
        init_db()
        if not self.configured:
            LOGGER.warning("Telegram bot polling is not configured; set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
            return

        self.install_commands()
        LOGGER.info("Telegram command bot polling started for chat_id=%s", self.settings.telegram_chat_id)
        while stop_event is None or not stop_event.is_set():
            updates = self._get_updates()
            for update in updates:
                if stop_event is not None and stop_event.is_set():
                    break
                self._handle_update(update)
            if not updates:
                sleep_seconds = max(0, self.settings.telegram_poll_interval_seconds)
                if stop_event is not None:
                    stop_event.wait(sleep_seconds)
                else:
                    time.sleep(sleep_seconds)


def start_telegram_command_bot() -> None:
    global _TELEGRAM_BOT_THREAD, _TELEGRAM_BOT_STOP_EVENT
    if _TELEGRAM_BOT_THREAD is not None and _TELEGRAM_BOT_THREAD.is_alive():
        return

    bot = TelegramCommandBot()
    if not bot.configured:
        LOGGER.info("Telegram command bot not started because token/chat ID are not configured.")
        return

    stop_event = threading.Event()
    thread = threading.Thread(
        target=bot.run_forever,
        kwargs={"stop_event": stop_event},
        name="emergyx-telegram-command-bot",
        daemon=True,
    )
    _TELEGRAM_BOT_STOP_EVENT = stop_event
    _TELEGRAM_BOT_THREAD = thread
    thread.start()


def stop_telegram_command_bot() -> None:
    global _TELEGRAM_BOT_THREAD, _TELEGRAM_BOT_STOP_EVENT
    if _TELEGRAM_BOT_STOP_EVENT is not None:
        _TELEGRAM_BOT_STOP_EVENT.set()
    if _TELEGRAM_BOT_THREAD is not None and _TELEGRAM_BOT_THREAD.is_alive():
        _TELEGRAM_BOT_THREAD.join(timeout=5)
    _TELEGRAM_BOT_THREAD = None
    _TELEGRAM_BOT_STOP_EVENT = None


__all__ = ["TelegramCommandBot", "start_telegram_command_bot", "stop_telegram_command_bot"]
