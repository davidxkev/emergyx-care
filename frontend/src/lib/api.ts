import type {
  AgentExplainResponse,
  AgentStatus,
  AgentTrendAnalysisResponse,
  AlertRead,
  CareContextRead,
  CareContextUpdateResponse,
  ChatThread,
  DailyReportRead,
  DailyReportResponse,
  DemoScenarioResponse,
  EventRead,
  GemmaFindingRead,
  GemmaPatternScanResponse,
  GemmaModelPullRequest,
  GemmaSettingsRead,
  GemmaSettingsUpdate,
  GemmaSettingsUpdateResponse,
  HealthResponse,
  IncidentResponse,
  Mode,
  ModeSnapshot,
  ReportScheduleRead,
  ReportScheduleTelegramTestResponse,
  ReportScheduleUpdate,
  SensorLedCommandRequest,
  SensorAutoDetectResponse,
  SensorDeleteResponse,
  SensorIngestionRestartResponse,
  SensorLedCommandResponse,
  TelegramSettingsRead,
  TelegramSettingsUpdate,
  TelegramSettingsUpdateResponse,
  ThreadDeleteResponse,
  ThreadDetailResponse,
  ThreadListResponse,
  TrendsTodayResponse,
  TrendsWeekResponse,
  WeeklyReportRead,
} from '@/lib/types';

function apiBaseUrl() {
  if (process.env.NEXT_PUBLIC_API_BASE_URL) {
    return process.env.NEXT_PUBLIC_API_BASE_URL;
  }
  if (typeof window !== 'undefined') {
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:8000`;
  }
  return 'http://127.0.0.1:8000';
}

function errorMessageFromBody(text: string, fallback: string) {
  if (!text) {
    return fallback;
  }

  try {
    const payload = JSON.parse(text) as { detail?: unknown };
    if (typeof payload.detail === 'string') {
      return payload.detail;
    }
    if (Array.isArray(payload.detail)) {
      return payload.detail
        .map((item) =>
          typeof item === 'object' && item !== null && 'msg' in item
            ? String(item.msg)
            : String(item),
        )
        .join(', ');
    }
  } catch {
    return text;
  }

  return text;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl()}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    cache: 'no-store',
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(errorMessageFromBody(text, `Request failed: ${response.status}`));
  }

  return response.json() as Promise<T>;
}

export function getHealth() {
  return apiFetch<HealthResponse>('/health');
}

export function getAgentStatus() {
  return apiFetch<AgentStatus>('/agent/status');
}

export function getModeSnapshot(mode: Mode) {
  return apiFetch<ModeSnapshot>(`/stats/mode-snapshot?mode=${mode}`);
}

export function getEvents(mode: Mode, limit = 50) {
  return apiFetch<EventRead[]>(`/events?mode=${mode}&limit=${limit}`);
}

export function getLatestEventsBySensor(mode: Mode, scanLimit = 5000) {
  return apiFetch<EventRead[]>(
    `/events/latest-by-sensor?mode=${mode}&scan_limit=${scanLimit}`,
  );
}

export function getAlerts(mode: Mode, limit = 20) {
  return apiFetch<AlertRead[]>(`/alerts?mode=${mode}&limit=${limit}`);
}

function trendsQuery(
  mode: Mode,
  options?: { nightStartHour?: number; nightEndHour?: number },
) {
  const params = new URLSearchParams();
  params.set('mode', mode);
  if (typeof options?.nightStartHour === 'number') {
    params.set('night_start_hour', String(options.nightStartHour));
  }
  if (typeof options?.nightEndHour === 'number') {
    params.set('night_end_hour', String(options.nightEndHour));
  }
  return params.toString();
}

export function getTrendsToday(
  mode: Mode,
  options?: { nightStartHour?: number; nightEndHour?: number },
) {
  return apiFetch<TrendsTodayResponse>(`/trends/today?${trendsQuery(mode, options)}`);
}

export function getTrendsWeek(
  mode: Mode,
  options?: { nightStartHour?: number; nightEndHour?: number },
) {
  return apiFetch<TrendsWeekResponse>(`/trends/week?${trendsQuery(mode, options)}`);
}

export function getLatestIncident(mode: Mode) {
  return apiFetch<IncidentResponse>(`/incidents/latest?mode=${mode}`);
}

export function getLatestReport(mode: Mode) {
  return apiFetch<DailyReportRead | null>(`/reports/daily/latest?mode=${mode}`);
}

export function getReports(mode: Mode, limit = 8) {
  return apiFetch<DailyReportRead[]>(`/reports/daily?mode=${mode}&limit=${limit}`);
}

export function getWeeklyReports(mode: Mode, limit = 20) {
  return apiFetch<WeeklyReportRead[]>(`/reports/weekly?mode=${mode}&limit=${limit}`);
}

export function getReportSchedule() {
  return apiFetch<ReportScheduleRead>('/reports/schedule');
}

export function updateReportSchedule(payload: ReportScheduleUpdate) {
  return apiFetch<ReportScheduleRead>('/reports/schedule', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function testReportScheduleTelegram(reportType: 'daily' | 'weekly') {
  return apiFetch<ReportScheduleTelegramTestResponse>('/reports/schedule/test-telegram', {
    method: 'POST',
    body: JSON.stringify({ report_type: reportType }),
  });
}

export function explainLatest(mode: Mode) {
  return apiFetch<AgentExplainResponse>(`/agent/explain-latest?mode=${mode}`, {
    method: 'POST',
  });
}

export function analyzeTrends(
  mode: Mode,
  options?: { nightStartHour?: number; nightEndHour?: number },
) {
  return apiFetch<AgentTrendAnalysisResponse>(
    `/agent/analyze-trends?${trendsQuery(mode, options)}`,
    {
      method: 'POST',
    },
  );
}

export function getGemmaFindings(mode: Mode, limit = 20) {
  return apiFetch<GemmaFindingRead[]>(`/reports/gemma-findings?mode=${mode}&limit=${limit}`);
}

export function runGemmaPatternScan(
  mode: Mode,
  options?: { sendTelegram?: boolean; nightStartHour?: number; nightEndHour?: number },
) {
  return apiFetch<GemmaPatternScanResponse>(`/reports/gemma-findings/scan?mode=${mode}`, {
    method: 'POST',
    body: JSON.stringify({
      send_telegram: Boolean(options?.sendTelegram),
      night_start_hour: options?.nightStartHour,
      night_end_hour: options?.nightEndHour,
    }),
  });
}

export function generateDailyReport(mode: Mode, options?: { requireGemma?: boolean }) {
  return apiFetch<DailyReportResponse>(`/reports/daily?mode=${mode}`, {
    method: 'POST',
    body: JSON.stringify({
      require_gemma: Boolean(options?.requireGemma),
    }),
  });
}

export async function generateWeeklyReportPdf(
  mode: Mode,
  options?: { nightStartHour?: number; nightEndHour?: number },
) {
  const body: Record<string, number> = {};
  if (typeof options?.nightStartHour === 'number') {
    body.night_start_hour = options.nightStartHour;
  }
  if (typeof options?.nightEndHour === 'number') {
    body.night_end_hour = options.nightEndHour;
  }

  const response = await fetch(`${apiBaseUrl()}/reports/weekly/pdf?mode=${mode}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    cache: 'no-store',
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(errorMessageFromBody(text, `Request failed: ${response.status}`));
  }

  const disposition = response.headers.get('Content-Disposition') ?? '';
  const filenameMatch = disposition.match(/filename="([^"]+)"/);
  return {
    blob: await response.blob(),
    filename: filenameMatch?.[1] ?? 'emergyx-weekly-report.pdf',
    modelName: response.headers.get('X-Emergyx-Model') ?? null,
    reportId: response.headers.get('X-Emergyx-Weekly-Report-Id') ?? null,
  };
}

export async function downloadWeeklyReportPdf(reportId: number) {
  const response = await fetch(`${apiBaseUrl()}/reports/weekly/${reportId}/pdf`, {
    method: 'GET',
    cache: 'no-store',
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(errorMessageFromBody(text, `Request failed: ${response.status}`));
  }

  const disposition = response.headers.get('Content-Disposition') ?? '';
  const filenameMatch = disposition.match(/filename="([^"]+)"/);
  return {
    blob: await response.blob(),
    filename: filenameMatch?.[1] ?? 'emergyx-weekly-report.pdf',
    modelName: response.headers.get('X-Emergyx-Model') ?? null,
    reportId: response.headers.get('X-Emergyx-Weekly-Report-Id') ?? String(reportId),
  };
}

export function simulateFall() {
  return apiFetch<EventRead>('/events/simulate-fall', {
    method: 'POST',
    body: JSON.stringify({}),
  });
}

export function testTelegram() {
  return apiFetch<{ success: boolean; message: string }>('/alerts/test-telegram', {
    method: 'POST',
  });
}

export function runDemoScenario(
  scenario: 'fall' | 'vitals-change' | 'night-activity' | 'pattern-scan' | 'reset',
) {
  return apiFetch<DemoScenarioResponse>(`/demo/scenarios/${scenario}`, {
    method: 'POST',
    body: JSON.stringify({}),
  });
}

export function getTelegramSettings() {
  return apiFetch<TelegramSettingsRead>('/settings/telegram');
}

export function updateTelegramSettings(payload: TelegramSettingsUpdate) {
  return apiFetch<TelegramSettingsUpdateResponse>('/settings/telegram', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getGemmaSettings() {
  return apiFetch<GemmaSettingsRead>('/settings/gemma');
}

export function updateGemmaSettings(payload: GemmaSettingsUpdate) {
  return apiFetch<GemmaSettingsUpdateResponse>('/settings/gemma', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function pullGemmaModel(payload: GemmaModelPullRequest) {
  return apiFetch<GemmaSettingsUpdateResponse>('/settings/gemma/pull', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getCareContext() {
  return apiFetch<CareContextRead>('/settings/care-context');
}

export function updateCareContext(payload: CareContextRead) {
  return apiFetch<CareContextUpdateResponse>('/settings/care-context', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function setSensorLed(payload: SensorLedCommandRequest) {
  return apiFetch<SensorLedCommandResponse>('/settings/led', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function autoDetectNetworkSensors(payload?: {
  hosts?: string[];
  include_subnet_scan?: boolean;
  timeout_seconds?: number;
  concurrency?: number;
  room_hint?: string;
}) {
  return apiFetch<SensorAutoDetectResponse>('/settings/sensors/auto-detect', {
    method: 'POST',
    body: JSON.stringify(payload ?? {}),
  });
}

export function restartSensorIngestion() {
  return apiFetch<SensorIngestionRestartResponse>('/settings/sensors/restart-ingestion', {
    method: 'POST',
    body: JSON.stringify({}),
  });
}

export function deleteSensor(sensorId: string) {
  return apiFetch<SensorDeleteResponse>(
    `/settings/sensors/${encodeURIComponent(sensorId)}`,
    {
      method: 'DELETE',
    },
  );
}

export function getThreads(mode: Mode) {
  return apiFetch<ThreadListResponse>(`/chat/threads?mode=${mode}`);
}

export function createThread(mode: Mode, title?: string) {
  return apiFetch<{ thread: ChatThread }>(`/chat/threads?mode=${mode}`, {
    method: 'POST',
    body: JSON.stringify(title ? { title } : {}),
  });
}

export function getThread(mode: Mode, threadId: number) {
  return apiFetch<ThreadDetailResponse>(`/chat/threads/${threadId}?mode=${mode}`);
}

export function deleteThread(mode: Mode, threadId: number) {
  return apiFetch<ThreadDeleteResponse>(`/chat/threads/${threadId}?mode=${mode}`, {
    method: 'DELETE',
  });
}

export function postThreadMessage(
  mode: Mode,
  threadId: number,
  content: string,
  think = false,
) {
  return apiFetch<ThreadDetailResponse>(
    `/chat/threads/${threadId}/messages?mode=${mode}`,
    {
      method: 'POST',
      body: JSON.stringify({ content, think }),
    },
  );
}

export async function streamThreadMessage(
  mode: Mode,
  threadId: number,
  content: string,
  think = false,
  handlers?: {
    onChunk?: (delta: string) => void;
    onThinking?: (delta: string) => void;
  },
) {
  const response = await fetch(
    `${apiBaseUrl()}/chat/threads/${threadId}/messages/stream?mode=${mode}`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ content, think }),
      cache: 'no-store',
    },
  );

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  if (!response.body) {
    throw new Error('Streaming response body was not available.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let detail: ThreadDetailResponse | null = null;

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });

    let newlineIndex = buffer.indexOf('\n');
    while (newlineIndex >= 0) {
      const line = buffer.slice(0, newlineIndex).trim();
      buffer = buffer.slice(newlineIndex + 1);

      if (line) {
        const event = JSON.parse(line) as
          | { type: 'thinking'; delta: string }
          | { type: 'chunk'; delta: string }
          | { type: 'done'; detail: ThreadDetailResponse }
          | { type: 'error'; error: string };

        if (event.type === 'thinking') {
          handlers?.onThinking?.(event.delta);
        } else if (event.type === 'chunk') {
          handlers?.onChunk?.(event.delta);
        } else if (event.type === 'done') {
          detail = event.detail;
        } else if (event.type === 'error') {
          throw new Error(event.error || 'Streaming request failed.');
        }
      }

      newlineIndex = buffer.indexOf('\n');
    }

    if (done) {
      break;
    }
  }

  if (!detail) {
    throw new Error('Streaming finished without a final thread detail payload.');
  }

  return detail;
}
