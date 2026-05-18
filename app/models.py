from __future__ import annotations

from typing import Optional

from sqlmodel import Field, SQLModel


class Event(SQLModel, table=True):
    __tablename__ = "events"

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: str = Field(index=True)
    sensor_id: str = Field(index=True)
    room: str = Field(index=True)
    event_type: str = Field(index=True)
    value: str
    source: str = Field(index=True)
    metadata_json: str | None = None


class Alert(SQLModel, table=True):
    __tablename__ = "alerts"

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: str = Field(index=True)
    event_id: int | None = Field(default=None, foreign_key="events.id")
    severity: str = Field(index=True)
    alert_type: str = Field(index=True)
    message: str
    sent_channel: str = Field(index=True)
    sent_success: bool = Field(default=False, index=True)
    metadata_json: str | None = None


class AgentDecision(SQLModel, table=True):
    __tablename__ = "agent_decisions"

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: str = Field(index=True)
    related_event_id: int | None = Field(default=None, foreign_key="events.id")
    decision_type: str = Field(index=True)
    input_summary: str
    output_text: str
    model_name: str
    metadata_json: str | None = None


class GemmaFinding(SQLModel, table=True):
    __tablename__ = "gemma_findings"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: str = Field(index=True)
    mode: str = Field(index=True)
    source_filter: str | None = Field(default=None, index=True)
    pattern_type: str = Field(index=True)
    severity: str = Field(index=True)
    title: str
    summary: str
    evidence_json: str | None = None
    caregiver_action: str | None = None
    model_name: str
    send_alert: bool = Field(default=False, index=True)
    alert_id: int | None = Field(default=None, foreign_key="alerts.id")
    fingerprint: str = Field(index=True)
    metadata_json: str | None = None


class DailyReport(SQLModel, table=True):
    __tablename__ = "daily_reports"

    id: Optional[int] = Field(default=None, primary_key=True)
    date: str = Field(index=True)
    report_text: str
    created_at: str = Field(index=True)
    metadata_json: str | None = None


class WeeklyReport(SQLModel, table=True):
    __tablename__ = "weekly_reports"

    id: Optional[int] = Field(default=None, primary_key=True)
    start_date: str = Field(index=True)
    end_date: str = Field(index=True)
    created_at: str = Field(index=True)
    mode: str = Field(index=True)
    filename: str
    model_name: str
    pdf_bytes: bytes
    metadata_json: str | None = None


class ChatThread(SQLModel, table=True):
    __tablename__ = "chat_threads"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    mode: str = Field(index=True)
    created_at: str = Field(index=True)
    updated_at: str = Field(index=True)
    metadata_json: str | None = None


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    thread_id: int = Field(foreign_key="chat_threads.id", index=True)
    role: str = Field(index=True)
    content: str
    created_at: str = Field(index=True)
    model_name: str | None = None
    used_mock: bool | None = Field(default=None, index=True)
    metadata_json: str | None = None
