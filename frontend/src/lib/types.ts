export type Mode = 'live' | 'demo';

export interface EventRead {
  id: number;
  timestamp: string;
  sensor_id: string;
  room: string;
  event_type: string;
  value: string;
  source: string;
  metadata_json?: string | null;
}

export interface AlertRead {
  id: number;
  timestamp: string;
  event_id?: number | null;
  severity: string;
  alert_type: string;
  message: string;
  sent_channel: string;
  sent_success: boolean;
  metadata_json?: string | null;
}

export interface LightContext {
  lux?: number | null;
  category: string;
  timestamp: string;
  room: string;
  source: string;
  sensor_id?: string | null;
}

export interface TodayStats {
  total_events_today: number;
  fall_events_today: number;
  latest_person_present?: EventRead | null;
  latest_fall_state?: EventRead | null;
}

export interface SnapshotEvent {
  timestamp: string;
  value: string;
  sensor_id?: string | null;
  room: string;
}

export interface IncidentContext {
  room?: string;
  source?: string;
  sensor_id?: string;
  event?: {
    id?: number;
    timestamp?: string;
    value?: string;
    sensor_id?: string;
  } | null;
  person_before?: {
    timestamp?: string;
    value?: string;
    sensor_id?: string;
  } | null;
  before_person?: {
    timestamp?: string;
    value?: string;
    sensor_id?: string;
  } | null;
  after_person?: {
    timestamp?: string;
    value?: string;
    sensor_id?: string;
  } | null;
  fall_clear_after?: {
    timestamp?: string;
    value?: string;
    sensor_id?: string;
  } | null;
  after_fall_clear?: {
    timestamp?: string;
    value?: string;
    sensor_id?: string;
  } | null;
  alert?: {
    timestamp?: string;
    sent_channel?: string;
    sent_success?: boolean;
    severity?: string;
  } | null;
  light_context?: {
    timestamp?: string;
    lux?: number | null;
    category?: string;
    room?: string;
    source?: string;
    sensor_id?: string;
  } | null;
  duration_seconds?: number | null;
  summary?: string[];
}

export interface IncidentResponse {
  incident: IncidentContext | null;
  found: boolean;
}

export interface ModeSnapshot {
  mode: Mode;
  last_event_timestamp?: string | null;
  last_event_age_seconds?: number | null;
  last_event_age_human?: string;
  last_event_category?: string;
  light?: LightContext | null;
  latest_person?: SnapshotEvent | null;
  latest_fall?: SnapshotEvent | null;
  latest_incident?: IncidentContext | null;
  today_stats?: TodayStats | null;
}

export interface AgentStatus {
  gemma_enabled: boolean;
  model: string;
  ollama_base_url: string;
  checked_at: string;
  status: 'online' | 'disabled' | 'unreachable' | string;
  reachable: boolean;
  installed_models?: string[];
  error?: string;
}

export interface DailyReportRead {
  id: number;
  date: string;
  report_text: string;
  created_at: string;
  metadata_json?: string | null;
}

export interface AgentExplainResponse {
  success: boolean;
  used_mock: boolean;
  model_name: string;
  explanation: string;
  related_event_id?: number | null;
  tools_used: string[];
  incident?: IncidentContext | null;
}

export interface CaregiverAskResponse {
  success: boolean;
  used_mock: boolean;
  model_name: string;
  answer: string;
  question: string;
  tools_used: string[];
}

export interface DailyReportResponse {
  success: boolean;
  used_mock: boolean;
  model_name: string;
  date: string;
  report: string;
  report_id?: number | null;
  tools_used: string[];
}

export interface WeeklyReportRead {
  id: number;
  start_date: string;
  end_date: string;
  created_at: string;
  mode: Mode | string;
  filename: string;
  model_name: string;
  metadata_json?: string | null;
}

export interface ReportScheduleRead {
  daily_enabled: boolean;
  daily_time: string;
  daily_send_telegram: boolean;
  weekly_enabled: boolean;
  weekly_day: number;
  weekly_time: string;
  weekly_send_telegram: boolean;
  pattern_enabled: boolean;
  pattern_interval_minutes: number;
  pattern_send_telegram: boolean;
  last_pattern_run_at?: string | null;
  last_pattern_summary?: string | null;
  last_daily_run_date?: string | null;
  last_weekly_run_key?: string | null;
  last_run_at?: string | null;
  last_error?: string | null;
  scheduler_running: boolean;
}

export interface ReportScheduleUpdate {
  daily_enabled: boolean;
  daily_time: string;
  daily_send_telegram: boolean;
  weekly_enabled: boolean;
  weekly_day: number;
  weekly_time: string;
  weekly_send_telegram: boolean;
  pattern_enabled: boolean;
  pattern_interval_minutes: number;
  pattern_send_telegram: boolean;
}

export interface ReportScheduleTelegramTestResponse {
  success: boolean;
  message: string;
}

export interface GemmaFindingRead {
  id: number;
  created_at: string;
  mode: Mode | string;
  source_filter?: string | null;
  pattern_type: string;
  severity: string;
  title: string;
  summary: string;
  evidence_json?: string | null;
  caregiver_action?: string | null;
  model_name: string;
  send_alert: boolean;
  alert_id?: number | null;
  fingerprint: string;
  metadata_json?: string | null;
}

export interface GemmaPatternScanResponse {
  success: boolean;
  model_name: string;
  created_at: string;
  overall_summary: string;
  findings: GemmaFindingRead[];
  alerts_created: number;
}

export interface DemoScenarioResponse {
  success: boolean;
  scenario: string;
  created_at: string;
  events?: EventRead[];
  alerts?: AlertRead[];
  findings_created?: number;
  alerts_created?: number;
  model_name?: string | null;
  overall_summary?: string | null;
  next_step: string;
}

export interface TrendMetric {
  today: number;
  baseline_total: number;
  baseline_average: number;
  delta: number;
  delta_percent?: number | null;
  direction: 'up' | 'down' | 'flat' | string;
}

export interface TrendWindow {
  today: string;
  baseline_start: string;
  baseline_end: string;
}

export interface TrendNightWindow {
  start_hour: number;
  end_hour: number;
}

export interface TrendLightSummary {
  latest_category: string;
  latest_lux?: number | null;
  latest_timestamp?: string | null;
  today_average_category: string;
  today_average_lux?: number | null;
  baseline_average_category: string;
  baseline_average_lux?: number | null;
}

export interface TrendActivitySummary {
  last_activity_timestamp?: string | null;
  last_activity_age_seconds?: number | null;
  last_activity_age_human: string;
  last_activity_staleness: string;
}

export interface TrendSensorFreshness {
  sensor_id: string;
  room: string;
  source: string;
  last_event_timestamp: string;
  age_seconds?: number | null;
  age_human: string;
  staleness: string;
  offline: boolean;
}

export interface TrendFreshness {
  offline: boolean;
  stale_sensor_count: number;
  sensors: TrendSensorFreshness[];
}

export interface TrendNotableChange {
  code: string;
  severity: 'info' | 'warning' | string;
  title: string;
  detail: string;
}

export interface TrendsTodayResponse {
  mode: Mode | string;
  window: TrendWindow;
  night_window: TrendNightWindow;
  metrics: Record<string, TrendMetric>;
  light: TrendLightSummary;
  activity: TrendActivitySummary;
  freshness: TrendFreshness;
  notable_changes: TrendNotableChange[];
  unusual_detected: boolean;
  generated_from: string;
  model_hint: string;
}

export interface TrendWeekWindow {
  start_date: string;
  end_date: string;
}

export interface TrendWeekDay {
  date: string;
  label: string;
  event_count: number;
  fall_count: number;
  alerts_sent: number;
  nighttime_movement_count: number;
  average_light_lux?: number | null;
  average_light_category: string;
}

export interface TrendsWeekResponse {
  mode: Mode | string;
  window: TrendWeekWindow;
  night_window: TrendNightWindow;
  days: TrendWeekDay[];
  generated_from: string;
}

export interface AgentTrendAnalysisResponse {
  success: boolean;
  used_mock: boolean;
  model_name: string;
  analysis: string;
  tools_used: string[];
  trends?: TrendsTodayResponse | null;
}

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  gemma: AgentStatus;
  fda2_sensors?: Array<{
    sensor_id: string;
    room: string;
    host: string;
    sensor_family?: string;
    rgb_light_configured?: boolean;
  }>;
  telegram_configured?: boolean;
  telegram_gemma_explanations?: boolean;
  dashboard_refresh_seconds?: number;
  environment?: string;
}

export interface TelegramSettingsRead {
  configured: boolean;
  bot_token_set: boolean;
  bot_token_masked?: string | null;
  chat_id?: string | null;
  send_gemma_explanations: boolean;
  poll_timeout_seconds: number;
  poll_interval_seconds: number;
}

export interface TelegramSettingsUpdate {
  bot_token?: string | null;
  chat_id?: string | null;
  send_gemma_explanations: boolean;
  poll_timeout_seconds: number;
  poll_interval_seconds: number;
  clear_bot_token?: boolean;
  clear_chat_id?: boolean;
  send_test_message?: boolean;
}

export interface TelegramSettingsUpdateResponse {
  success: boolean;
  message: string;
  settings: TelegramSettingsRead;
  test_success?: boolean | null;
}

export interface GemmaSettingsRead {
  enabled: boolean;
  model: string;
  ollama_base_url: string;
  gemma_first_notifications: boolean;
  status: string;
  reachable: boolean;
  installed_models: string[];
  error?: string | null;
}

export interface GemmaSettingsUpdate {
  enabled: boolean;
  model: string;
  ollama_base_url: string;
  gemma_first_notifications: boolean;
}

export interface GemmaModelPullRequest {
  model: string;
  save_as_current?: boolean;
}

export interface GemmaSettingsUpdateResponse {
  success: boolean;
  message: string;
  settings: GemmaSettingsRead;
}

export interface ResidentProfileRead {
  id: string;
  name: string;
  rooms: string[];
  context: string;
  created_at: string;
  updated_at: string;
}

export interface CareContextRead {
  residents: ResidentProfileRead[];
  manual_rooms: string[];
  deleted_rooms: string[];
  sensor_assignments: Record<string, string>;
  sensor_names: Record<string, string>;
  sensor_contexts: Record<string, string>;
  sensor_led_colors: Record<string, string>;
  room_display_names: Record<string, string>;
  updated_at?: string | null;
}

export interface CareContextUpdateResponse {
  success: boolean;
  message: string;
  context: CareContextRead;
}

export interface SensorLedCommandRequest {
  sensor_id: string;
  hex_color?: string | null;
  brightness?: number;
  flash_seconds?: number | null;
  turn_off?: boolean;
}

export interface SensorLedCommandResponse {
  success: boolean;
  sensor_id: string;
  room: string;
  rgb_light_key: number;
  discovered: boolean;
  hex_color?: string | null;
  message: string;
}

export interface SensorAutoDetectDevice {
  sensor_id: string;
  sensor_family: 'fall_fda2' | 'heart_breath_bha2' | 'unknown' | string;
  device_name: string;
  host: string;
  port: number;
  configured_for_live_ingestion: boolean;
  added_to_runtime: boolean;
  person_key?: number | null;
  fall_key?: number | null;
  light_key?: number | null;
  rgb_light_key?: number | null;
  heart_rate_key?: number | null;
  respiration_rate_key?: number | null;
  distance_key?: number | null;
  target_number_key?: number | null;
  note: string;
}

export interface SensorAutoDetectResponse {
  success: boolean;
  scanned_hosts: number;
  discovered: SensorAutoDetectDevice[];
}

export interface SensorIngestionRestartResponse {
  success: boolean;
  restarted: boolean;
  pid?: number | null;
  message: string;
}

export interface SensorDeleteResponse {
  success: boolean;
  sensor_id: string;
  removed: boolean;
  restarted: boolean;
  pid?: number | null;
  message: string;
}

export interface ChatThread {
  id: number;
  title: string;
  mode: Mode;
  created_at: string;
  updated_at: string;
  metadata?: Record<string, unknown> | null;
}

export interface EvidenceItem {
  kind: string;
  label: string;
  timestamp?: string | null;
  text: string;
  related_event_id?: number | null;
  metadata?: Record<string, unknown> | null;
}

export interface ChatMessage {
  id: number;
  thread_id: number;
  role: 'user' | 'assistant' | string;
  content: string;
  created_at: string;
  model_name?: string | null;
  used_mock?: boolean | null;
  metadata?: {
    tools_used?: string[];
    evidence?: EvidenceItem[];
    snapshot?: Record<string, unknown>;
    thinking?: string | null;
  } | null;
}

export interface ThreadListResponse {
  threads: ChatThread[];
}

export interface ThreadDetailResponse {
  thread: ChatThread;
  messages: ChatMessage[];
}

export interface ThreadDeleteResponse {
  success: boolean;
  thread_id: number;
}
