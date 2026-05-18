from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventCreate(BaseModel):
    sensor_id: str
    room: str
    event_type: str
    value: Any
    source: str = "manual"
    metadata_json: dict[str, Any] | list[Any] | str | None = None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: str
    sensor_id: str
    room: str
    event_type: str
    value: str
    source: str
    metadata_json: str | None = None


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: str
    event_id: int | None = None
    severity: str
    alert_type: str
    message: str
    sent_channel: str
    sent_success: bool
    metadata_json: str | None = None


class TodayStats(BaseModel):
    total_events_today: int
    fall_events_today: int
    latest_person_present: EventRead | None = None
    latest_fall_state: EventRead | None = None


class LightContextRead(BaseModel):
    lux: float | None = None
    category: str
    timestamp: str
    room: str
    source: str
    sensor_id: str | None = None


class LiveSnapshotResponse(BaseModel):
    last_live_timestamp: str | None = None
    last_live_age_seconds: int | None = None
    last_live_age_human: str
    last_live_category: str
    light: LightContextRead | None = None


class SimulateFallRequest(BaseModel):
    sensor_id: str | None = None
    room: str | None = None
    metadata_json: dict[str, Any] | list[Any] | str | None = None


class TelegramTestResponse(BaseModel):
    success: bool
    message: str


class TelegramSettingsRead(BaseModel):
    configured: bool
    bot_token_set: bool
    bot_token_masked: str | None = None
    chat_id: str | None = None
    send_gemma_explanations: bool
    poll_timeout_seconds: int
    poll_interval_seconds: int


class TelegramSettingsUpdate(BaseModel):
    bot_token: str | None = None
    chat_id: str | None = None
    send_gemma_explanations: bool = False
    poll_timeout_seconds: int = Field(default=25, ge=5, le=120)
    poll_interval_seconds: int = Field(default=2, ge=1, le=30)
    clear_bot_token: bool = False
    clear_chat_id: bool = False
    send_test_message: bool = False


class TelegramSettingsUpdateResponse(BaseModel):
    success: bool
    message: str
    settings: TelegramSettingsRead
    test_success: bool | None = None


class GemmaSettingsRead(BaseModel):
    enabled: bool
    model: str
    ollama_base_url: str
    gemma_first_notifications: bool = False
    status: str
    reachable: bool
    installed_models: list[str] = Field(default_factory=list)
    error: str | None = None


class GemmaSettingsUpdate(BaseModel):
    enabled: bool = True
    model: str = Field(default="gemma4:e2b", min_length=1, max_length=120)
    ollama_base_url: str = Field(default="http://localhost:11434", min_length=8, max_length=240)
    gemma_first_notifications: bool = False


class GemmaModelPullRequest(BaseModel):
    model: str = Field(default="gemma4:e2b", min_length=1, max_length=120)
    save_as_current: bool = True


class GemmaSettingsUpdateResponse(BaseModel):
    success: bool
    message: str
    settings: GemmaSettingsRead


class ResidentProfileRead(BaseModel):
    id: str
    name: str
    rooms: list[str] = Field(default_factory=list)
    context: str = ""
    created_at: str
    updated_at: str


class CareContextRead(BaseModel):
    residents: list[ResidentProfileRead] = Field(default_factory=list)
    manual_rooms: list[str] = Field(default_factory=list)
    deleted_rooms: list[str] = Field(default_factory=list)
    sensor_assignments: dict[str, str] = Field(default_factory=dict)
    sensor_names: dict[str, str] = Field(default_factory=dict)
    sensor_contexts: dict[str, str] = Field(default_factory=dict)
    sensor_led_colors: dict[str, str] = Field(default_factory=dict)
    room_display_names: dict[str, str] = Field(default_factory=dict)
    updated_at: str | None = None


class CareContextUpdate(CareContextRead):
    pass


class CareContextUpdateResponse(BaseModel):
    success: bool
    message: str
    context: CareContextRead


class SensorLedCommandRequest(BaseModel):
    sensor_id: str
    hex_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9a-fA-F]{6}$",
        description="RGB color to apply, for example #14b8a6.",
    )
    brightness: float = Field(default=0.85, ge=0.05, le=1.0)
    flash_seconds: float | None = Field(default=None, ge=0.1, le=30.0)
    turn_off: bool = False


class SensorLedCommandResponse(BaseModel):
    success: bool
    sensor_id: str
    room: str
    rgb_light_key: int
    discovered: bool
    hex_color: str | None = None
    message: str


class SensorAutoDetectRequest(BaseModel):
    hosts: list[str] | None = None
    include_subnet_scan: bool = True
    timeout_seconds: float = Field(default=1.5, ge=0.2, le=8.0)
    concurrency: int = Field(default=24, ge=1, le=64)
    room_hint: str | None = None


class SensorAutoDetectDevice(BaseModel):
    sensor_id: str
    sensor_family: str
    device_name: str
    host: str
    port: int
    configured_for_live_ingestion: bool
    added_to_runtime: bool
    person_key: int | None = None
    fall_key: int | None = None
    light_key: int | None = None
    rgb_light_key: int | None = None
    heart_rate_key: int | None = None
    respiration_rate_key: int | None = None
    distance_key: int | None = None
    target_number_key: int | None = None
    note: str


class SensorAutoDetectResponse(BaseModel):
    success: bool
    scanned_hosts: int
    discovered: list[SensorAutoDetectDevice]


class SensorIngestionRestartResponse(BaseModel):
    success: bool
    restarted: bool
    pid: int | None = None
    message: str


class SensorDeleteResponse(BaseModel):
    success: bool
    sensor_id: str
    removed: bool
    restarted: bool
    pid: int | None = None
    message: str


class AgentExplainResponse(BaseModel):
    success: bool
    used_mock: bool
    model_name: str
    explanation: str
    related_event_id: int | None = None
    tools_used: list[str] = Field(default_factory=list)
    incident: dict[str, Any] | None = None


class DashboardActionResult(BaseModel):
    status: str
    detail: str


class CaregiverAskRequest(BaseModel):
    question: str


class CaregiverAskResponse(BaseModel):
    success: bool
    used_mock: bool
    model_name: str
    answer: str
    question: str
    tools_used: list[str] = Field(default_factory=list)


class DailyReportRequest(BaseModel):
    date: str | None = None
    require_gemma: bool = False


class WeeklyReportRequest(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
    night_start_hour: int | None = Field(default=None, ge=0, le=23)
    night_end_hour: int | None = Field(default=None, ge=0, le=23)


class DailyReportResponse(BaseModel):
    success: bool
    used_mock: bool
    model_name: str
    date: str
    report: str
    report_id: int | None = None
    tools_used: list[str] = Field(default_factory=list)


class GemmaFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: str
    mode: str
    source_filter: str | None = None
    pattern_type: str
    severity: str
    title: str
    summary: str
    evidence_json: str | None = None
    caregiver_action: str | None = None
    model_name: str
    send_alert: bool
    alert_id: int | None = None
    fingerprint: str
    metadata_json: str | None = None


class GemmaPatternScanRequest(BaseModel):
    send_telegram: bool = False
    night_start_hour: int | None = Field(default=None, ge=0, le=23)
    night_end_hour: int | None = Field(default=None, ge=0, le=23)


class GemmaPatternScanResponse(BaseModel):
    success: bool
    model_name: str
    created_at: str
    overall_summary: str
    findings: list[GemmaFindingRead] = Field(default_factory=list)
    alerts_created: int = 0


class WeeklyReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    start_date: str
    end_date: str
    created_at: str
    mode: str
    filename: str
    model_name: str
    metadata_json: str | None = None


class ReportScheduleRead(BaseModel):
    daily_enabled: bool = False
    daily_time: str = "20:00"
    daily_send_telegram: bool = False
    weekly_enabled: bool = False
    weekly_day: int = Field(default=0, ge=0, le=6)
    weekly_time: str = "09:00"
    weekly_send_telegram: bool = False
    pattern_enabled: bool = True
    pattern_interval_minutes: int = Field(default=60, ge=15, le=1440)
    pattern_send_telegram: bool = False
    last_pattern_run_at: str | None = None
    last_pattern_summary: str | None = None
    last_daily_run_date: str | None = None
    last_weekly_run_key: str | None = None
    last_run_at: str | None = None
    last_error: str | None = None
    scheduler_running: bool = False


class ReportScheduleUpdate(BaseModel):
    daily_enabled: bool
    daily_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    daily_send_telegram: bool
    weekly_enabled: bool
    weekly_day: int = Field(ge=0, le=6)
    weekly_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    weekly_send_telegram: bool
    pattern_enabled: bool = True
    pattern_interval_minutes: int = Field(default=60, ge=15, le=1440)
    pattern_send_telegram: bool = False


class ReportScheduleTelegramTestRequest(BaseModel):
    report_type: str = Field(pattern=r"^(daily|weekly)$")


class ReportScheduleTelegramTestResponse(BaseModel):
    success: bool
    message: str


class TrendMetricRead(BaseModel):
    today: int
    baseline_total: int
    baseline_average: float
    delta: float
    delta_percent: float | None = None
    direction: str


class TrendWindowRead(BaseModel):
    today: str
    baseline_start: str
    baseline_end: str


class TrendNightWindowRead(BaseModel):
    start_hour: int
    end_hour: int


class TrendLightRead(BaseModel):
    latest_category: str
    latest_lux: float | None = None
    latest_timestamp: str | None = None
    today_average_category: str
    today_average_lux: float | None = None
    baseline_average_category: str
    baseline_average_lux: float | None = None


class TrendActivityRead(BaseModel):
    last_activity_timestamp: str | None = None
    last_activity_age_seconds: int | None = None
    last_activity_age_human: str
    last_activity_staleness: str


class TrendSensorFreshnessRead(BaseModel):
    sensor_id: str
    room: str
    source: str
    last_event_timestamp: str
    age_seconds: int | None = None
    age_human: str
    staleness: str
    offline: bool


class TrendFreshnessRead(BaseModel):
    offline: bool
    stale_sensor_count: int
    sensors: list[TrendSensorFreshnessRead] = Field(default_factory=list)


class TrendNotableChangeRead(BaseModel):
    code: str
    severity: str
    title: str
    detail: str


class TrendsTodayResponse(BaseModel):
    mode: str
    window: TrendWindowRead
    night_window: TrendNightWindowRead
    metrics: dict[str, TrendMetricRead]
    light: TrendLightRead
    activity: TrendActivityRead
    freshness: TrendFreshnessRead
    notable_changes: list[TrendNotableChangeRead] = Field(default_factory=list)
    unusual_detected: bool
    generated_from: str
    model_hint: str


class TrendWeekWindowRead(BaseModel):
    start_date: str
    end_date: str


class TrendWeekDayRead(BaseModel):
    date: str
    label: str
    event_count: int
    fall_count: int
    alerts_sent: int
    nighttime_movement_count: int
    average_light_lux: float | None = None
    average_light_category: str


class TrendsWeekResponse(BaseModel):
    mode: str
    window: TrendWeekWindowRead
    night_window: TrendNightWindowRead
    days: list[TrendWeekDayRead] = Field(default_factory=list)
    generated_from: str


class AgentTrendAnalysisResponse(BaseModel):
    success: bool
    used_mock: bool
    model_name: str
    analysis: str
    tools_used: list[str] = Field(default_factory=list)
    trends: TrendsTodayResponse | None = None


class DailyReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: str
    report_text: str
    created_at: str
    metadata_json: str | None = None


class IncidentResponse(BaseModel):
    incident: dict[str, Any] | None
    found: bool


class ChatThreadCreateRequest(BaseModel):
    title: str | None = None


class ChatMessageCreateRequest(BaseModel):
    content: str
    think: bool = False
