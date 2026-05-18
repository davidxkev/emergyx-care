'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Activity, AlertCircle, Lightbulb, Shield, ShieldAlert } from 'lucide-react';

import { DashboardCard } from '@/components/ui/dashboard-card';
import { DashboardHeader } from '@/components/ui/dashboard-header';
import { IncidentStory } from '@/components/ui/incident-story';
import { QuickActions } from '@/components/ui/quick-actions';
import { RecentActivity } from '@/components/ui/recent-activity';
import { RevenueChart } from '@/components/ui/revenue-chart';
import { AdminSidebar } from '@/components/ui/admin-sidebar';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import { SystemStatus } from '@/components/ui/system-status';
import { UsersTable } from '@/components/ui/users-table';
import { CareTrendsCard } from '@/components/ui/care-trends-card';
import {
  analyzeTrends,
  generateWeeklyReportPdf,
  getAgentStatus,
  getAlerts,
  getCareContext,
  getEvents,
  getModeSnapshot,
  getTrendsToday,
  runDemoScenario,
} from '@/lib/api';
import { formatTimestamp, gemmaStatusLabel, snapshotState } from '@/lib/format';
import {
  loadSensorRoomAssignments,
  type SensorRoomAssignments,
} from '@/lib/sensor-assignments';
import {
  loadRoomDisplayNames,
  type RoomDisplayNames,
} from '@/lib/room-names';
import { loadNightWindowPreference } from '@/lib/trends';
import type {
  AgentStatus,
  AgentTrendAnalysisResponse,
  AlertRead,
  EventRead,
  ModeSnapshot,
  TrendsTodayResponse,
} from '@/lib/types';

const LIVE_SENSOR_ONLINE_AGE_SECONDS = 45;

function lightValue(snapshot: ModeSnapshot | null) {
  if (!snapshot?.light?.category) {
    return 'No live light';
  }
  return snapshot.light.category
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function lightDetail(snapshot: ModeSnapshot | null) {
  if (typeof snapshot?.light?.lux === 'number') {
    return `${snapshot.light.lux.toFixed(1)} lux`;
  }
  return snapshot?.light?.timestamp ? formatTimestamp(snapshot.light.timestamp) : 'Awaiting sensor';
}

function hasFreshLiveData(snapshot: ModeSnapshot | null) {
  return (snapshot?.last_event_age_seconds ?? Number.POSITIVE_INFINITY) <= 15;
}

function uniqueValues(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.filter(Boolean) as string[]));
}

function formatRoomName(room?: string | null, displayNames: RoomDisplayNames = {}) {
  if (!room) {
    return 'Sensor Room';
  }
  const displayName = displayNames[room];
  if (displayName) {
    return displayName;
  }
  const autoRoomMatch = room.match(/^auto_room_(\d+)$/);
  if (autoRoomMatch) {
    return `Sensor Area ${autoRoomMatch[1]}`;
  }
  return room
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function parseTimestampMs(timestamp?: string | null) {
  if (!timestamp) {
    return null;
  }
  const parsed = Date.parse(timestamp);
  return Number.isNaN(parsed) ? null : parsed;
}

function collectLatestBySensor(events: EventRead[], snapshot: ModeSnapshot | null) {
  const latest = new Map<string, { timestampMs: number; room?: string | null }>();
  const consider = (sensorId?: string | null, room?: string | null, timestamp?: string | null) => {
    if (!sensorId) {
      return;
    }
    const timestampMs = parseTimestampMs(timestamp);
    if (timestampMs === null) {
      return;
    }
    const current = latest.get(sensorId);
    if (!current || timestampMs > current.timestampMs) {
      latest.set(sensorId, { timestampMs, room });
    }
  };

  for (const event of events) {
    consider(event.sensor_id, event.room, event.timestamp);
  }

  consider(
    snapshot?.latest_person?.sensor_id,
    snapshot?.latest_person?.room,
    snapshot?.latest_person?.timestamp,
  );
  consider(
    snapshot?.latest_fall?.sensor_id,
    snapshot?.latest_fall?.room,
    snapshot?.latest_fall?.timestamp,
  );
  consider(snapshot?.light?.sensor_id, snapshot?.light?.room, snapshot?.light?.timestamp);

  return latest;
}

function roomForSensor(
  sensorId: string | null | undefined,
  fallbackRoom: string | null | undefined,
  assignments: SensorRoomAssignments,
) {
  if (sensorId && assignments[sensorId]) {
    return assignments[sensorId];
  }
  return fallbackRoom ?? '';
}

function applyRoomAssignmentsToEvent(
  event: EventRead,
  assignments: SensorRoomAssignments,
): EventRead {
  const assignedRoom = roomForSensor(event.sensor_id, event.room, assignments);
  return assignedRoom && assignedRoom !== event.room
    ? { ...event, room: assignedRoom }
    : event;
}

function freshnessProgress(snapshot: ModeSnapshot | null) {
  const age = snapshot?.last_event_age_seconds;
  if (age == null) {
    return 18;
  }
  if (age <= 15) {
    return 96;
  }
  if (age <= 60) {
    return 82;
  }
  if (age <= 300) {
    return 58;
  }
  return 32;
}

function StatusPill({
  label,
  online,
  detail,
}: {
  label: string;
  online: boolean;
  detail: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold ${
        online
          ? 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-300'
          : 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300'
      }`}
      title={detail}
    >
      <span
        className={`h-2 w-2 rounded-full ${
          online ? 'bg-green-500 shadow-[0_0_0_3px_rgba(34,197,94,0.16)]' : 'bg-red-500'
        }`}
      />
      {label}
    </span>
  );
}

export default function AdminDashboard() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const mode = searchParams.get('mode') === 'live' ? 'live' : 'demo';
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [snapshot, setSnapshot] = useState<ModeSnapshot | null>(null);
  const [events, setEvents] = useState<EventRead[]>([]);
  const [alerts, setAlerts] = useState<AlertRead[]>([]);
  const [trends, setTrends] = useState<TrendsTodayResponse | null>(null);
  const [trendAnalysis, setTrendAnalysis] = useState<AgentTrendAnalysisResponse | null>(
    null,
  );
  const [analyzingTrends, setAnalyzingTrends] = useState(false);
  const [trendError, setTrendError] = useState<string | null>(null);
  const [weeklyPdfLoading, setWeeklyPdfLoading] = useState(false);
  const [weeklyPdfError, setWeeklyPdfError] = useState<string | null>(null);
  const [demoActionLoading, setDemoActionLoading] = useState(false);
  const [roomAssignments, setRoomAssignments] = useState<SensorRoomAssignments>(() =>
    loadSensorRoomAssignments(),
  );
  const [roomDisplayNames, setRoomDisplayNames] = useState<RoomDisplayNames>(() =>
    loadRoomDisplayNames(),
  );
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    setError(null);
    const localRoomAssignments = loadSensorRoomAssignments();
    const localRoomDisplayNames = loadRoomDisplayNames();
    const nightWindow = loadNightWindowPreference();
    const [
      agentStatus,
      liveSnapshot,
      liveEvents,
      liveAlerts,
      trendSnapshot,
      careContext,
    ] = await Promise.all([
      getAgentStatus(),
      getModeSnapshot(mode),
      getEvents(mode, 200),
      getAlerts(mode, 20),
      getTrendsToday(mode, {
        nightStartHour: nightWindow.startHour,
        nightEndHour: nightWindow.endHour,
      }),
      getCareContext(),
    ]);

    setStatus(agentStatus);
    setSnapshot(liveSnapshot);
    setEvents(liveEvents);
    setAlerts(liveAlerts);
    setTrends(trendSnapshot);
    setRoomAssignments({
      ...localRoomAssignments,
      ...careContext.sensor_assignments,
    });
    setRoomDisplayNames({
      ...localRoomDisplayNames,
      ...careContext.room_display_names,
    });
  }, [mode]);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      try {
        setIsRefreshing(true);
        await loadDashboard();
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : `Unable to load ${mode} sensor data.`,
          );
        }
      } finally {
        if (!cancelled) {
          setIsRefreshing(false);
        }
      }
    }

    void run();
    return () => {
      cancelled = true;
    };
  }, [loadDashboard, mode]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      if (document.visibilityState !== 'visible') {
        return;
      }

      void loadDashboard().catch((pollError) => {
        setError(
          pollError instanceof Error
            ? pollError.message
            : `Unable to refresh ${mode} sensor data.`,
        );
      });
    }, 5000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [loadDashboard, mode]);

  useEffect(() => {
    const refreshOnWake = () => {
      void loadDashboard().catch((wakeError) => {
        setError(
          wakeError instanceof Error
            ? wakeError.message
            : `Unable to refresh ${mode} sensor data.`,
        );
      });
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        refreshOnWake();
      }
    };

    window.addEventListener('focus', refreshOnWake);
    window.addEventListener('pageshow', refreshOnWake);
    window.addEventListener('online', refreshOnWake);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.removeEventListener('focus', refreshOnWake);
      window.removeEventListener('pageshow', refreshOnWake);
      window.removeEventListener('online', refreshOnWake);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [loadDashboard, mode]);

  const handleRefresh = async () => {
    try {
      setIsRefreshing(true);
      await loadDashboard();
    } catch (refreshError) {
      setError(
        refreshError instanceof Error
          ? refreshError.message
          : `Unable to refresh ${mode} sensor data.`,
      );
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleAnalyzeTrends = async () => {
    try {
      setTrendError(null);
      setAnalyzingTrends(true);
      const nightWindow = loadNightWindowPreference();
      const result = await analyzeTrends(mode, {
        nightStartHour: nightWindow.startHour,
        nightEndHour: nightWindow.endHour,
      });
      setTrendAnalysis(result);
      if (result.trends) {
        setTrends(result.trends);
      }
    } catch (analysisError) {
      setTrendError(
        analysisError instanceof Error
          ? analysisError.message
          : 'Unable to analyze trends right now.',
      );
    } finally {
      setAnalyzingTrends(false);
    }
  };

  const handleExport = () => {
    const rows = events.map((event) => ({
      timestamp: event.timestamp,
      sensor_id: event.sensor_id,
      room: event.room,
      type: event.event_type,
      value: event.value,
      source: event.source,
    }));
    const blob = new Blob([JSON.stringify(rows, null, 2)], {
      type: 'application/json;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `emergyx-${mode}-timeline.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const handleGenerateWeeklyPdf = async () => {
    try {
      setWeeklyPdfError(null);
      setWeeklyPdfLoading(true);
      const nightWindow = loadNightWindowPreference();
      const result = await generateWeeklyReportPdf(mode, {
        nightStartHour: nightWindow.startHour,
        nightEndHour: nightWindow.endHour,
      });
      const url = URL.createObjectURL(result.blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = result.filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (pdfError) {
      setWeeklyPdfError(
        pdfError instanceof Error
          ? pdfError.message
          : 'Unable to generate weekly PDF.',
      );
    } finally {
      setWeeklyPdfLoading(false);
    }
  };

  const handleDemoScenario = async (scenario: 'fall' | 'pattern-scan') => {
    try {
      setDemoActionLoading(true);
      setWeeklyPdfError(null);
      await runDemoScenario(scenario);
      await loadDashboard();
    } catch (scenarioError) {
      setWeeklyPdfError(
        scenarioError instanceof Error
          ? scenarioError.message
          : 'Unable to run demo scenario.',
      );
    } finally {
      setDemoActionLoading(false);
    }
  };

  const assignedEvents = useMemo(
    () => events.map((event) => applyRoomAssignmentsToEvent(event, roomAssignments)),
    [events, roomAssignments],
  );
  const assignedSnapshot = useMemo(() => {
    if (!snapshot) {
      return null;
    }
    return {
      ...snapshot,
      latest_person: snapshot.latest_person
        ? {
            ...snapshot.latest_person,
            room: roomForSensor(
              snapshot.latest_person.sensor_id,
              snapshot.latest_person.room,
              roomAssignments,
            ),
          }
        : snapshot.latest_person,
      latest_fall: snapshot.latest_fall
        ? {
            ...snapshot.latest_fall,
            room: roomForSensor(
              snapshot.latest_fall.sensor_id,
              snapshot.latest_fall.room,
              roomAssignments,
            ),
          }
        : snapshot.latest_fall,
      light: snapshot.light
        ? {
            ...snapshot.light,
            room: roomForSensor(snapshot.light.sensor_id, snapshot.light.room, roomAssignments),
          }
        : snapshot.light,
      latest_incident: snapshot.latest_incident
        ? {
            ...snapshot.latest_incident,
            room: roomForSensor(
              snapshot.latest_incident.sensor_id ?? snapshot.latest_incident.event?.sensor_id,
              snapshot.latest_incident.room,
              roomAssignments,
            ),
            event: snapshot.latest_incident.event
              ? {
                  ...snapshot.latest_incident.event,
                }
              : snapshot.latest_incident.event,
            light_context: snapshot.latest_incident.light_context
              ? {
                  ...snapshot.latest_incident.light_context,
                  room: roomForSensor(
                    snapshot.latest_incident.light_context.sensor_id,
                    snapshot.latest_incident.light_context.room,
                    roomAssignments,
                  ),
                }
              : snapshot.latest_incident.light_context,
          }
        : snapshot.latest_incident,
    };
  }, [snapshot, roomAssignments]);

  const search = searchQuery.trim().toLowerCase();
  const visibleEvents = useMemo(() => {
    if (!search) {
      return assignedEvents;
    }
    return assignedEvents.filter((event) =>
      [event.room, event.event_type, event.value, event.sensor_id]
        .join(' ')
        .toLowerCase()
        .includes(search),
    );
  }, [assignedEvents, search]);

  const visibleAlerts = useMemo(() => {
    if (!search) {
      return alerts;
    }
    return alerts.filter((alert) =>
      [alert.alert_type, alert.message, alert.sent_channel]
        .join(' ')
        .toLowerCase()
        .includes(search),
    );
  }, [alerts, search]);

  const stateSummary = assignedSnapshot ? snapshotState(assignedSnapshot) : null;
  const hasDemoData =
    mode === 'demo' &&
    (assignedEvents.length > 0 || Boolean(assignedSnapshot?.last_event_timestamp));
  const freshLiveData = mode === 'demo' ? hasDemoData : hasFreshLiveData(assignedSnapshot);
  const latestBySensor = useMemo(
    () => collectLatestBySensor(assignedEvents, assignedSnapshot),
    [assignedEvents, assignedSnapshot],
  );
  const latestLiveTimestampMs = parseTimestampMs(assignedSnapshot?.last_event_timestamp);
  const snapshotIsFreshEnough =
    mode === 'demo' ||
    (assignedSnapshot?.last_event_age_seconds ?? Number.POSITIVE_INFINITY) <=
      LIVE_SENSOR_ONLINE_AGE_SECONDS;
  const activeSensors = Array.from(latestBySensor.entries()).filter(([, item]) => {
    if (!snapshotIsFreshEnough || latestLiveTimestampMs === null) {
      return false;
    }
    if (mode === 'demo') {
      return true;
    }
    const ageMs = latestLiveTimestampMs - item.timestampMs;
    return ageMs >= 0 && ageMs <= LIVE_SENSOR_ONLINE_AGE_SECONDS * 1000;
  });
  const sensorIds = activeSensors.map(([sensorId]) => sensorId);
  const roomNames = uniqueValues(activeSensors.map(([, item]) => item.room));
  const sensorCount = sensorIds.length;
  const latestSensorId = sensorIds[0];
  const sensorOnline = sensorCount > 0;
  const gemmaOnline = status?.status === 'online';
  const telegramOnline =
    alerts.some((alert) => alert.sent_channel === 'telegram' && alert.sent_success) ||
    alerts.length > 0;
  const roomStatusLabel =
    roomNames.length === 1
      ? formatRoomName(roomNames[0], roomDisplayNames)
      : roomNames.length > 1
        ? `${roomNames.length} Rooms`
        : freshLiveData
          ? formatRoomName(
              assignedSnapshot?.latest_person?.room ?? assignedSnapshot?.light?.room,
              roomDisplayNames,
            )
          : mode === 'demo'
            ? 'No Demo Room'
            : 'No Live Room';

  const stats = [
    {
      title: 'Safety Status',
      value: freshLiveData ? (stateSummary?.safety ?? 'No data') : `Waiting for ${mode} data`,
      change:
        mode === 'demo' && freshLiveData
          ? 'Seeded demo timeline'
          : assignedSnapshot?.last_event_age_human != null
          ? `Updated ${assignedSnapshot.last_event_age_human}`
          : `Waiting for ${mode} data`,
      changeType: freshLiveData
        ? ((stateSummary?.safetyTone ?? 'positive') as 'positive' | 'negative')
        : ('negative' as const),
      icon: Shield,
      color: 'text-blue-500',
      bgColor: 'bg-blue-500/10',
      progressClass: 'bg-blue-500',
      progress: freshLiveData ? (stateSummary?.safetyTone === 'negative' ? 42 : 94) : 24,
    },
    {
      title: 'Sensor Coverage',
      value:
        sensorCount > 0
          ? `${sensorCount} ${mode} ${sensorCount === 1 ? 'sensor' : 'sensors'}`
          : `No ${mode} sensors`,
      change:
        roomNames.length > 0
          ? roomNames
              .slice(0, 2)
              .map((room) => formatRoomName(room, roomDisplayNames))
              .join(' · ')
          : latestSensorId
            ? latestSensorId
            : 'Waiting for sensors',
      changeType: sensorCount > 0 ? ('positive' as const) : ('negative' as const),
      icon: Activity,
      color: 'text-green-500',
      bgColor: 'bg-green-500/10',
      progressClass: 'bg-green-500',
      progress: sensorCount > 0 ? Math.min(100, 42 + sensorCount * 28) : 18,
    },
    {
      title: 'Light Status',
      value: freshLiveData ? lightValue(assignedSnapshot) : `No ${mode} data`,
      change: freshLiveData
        ? mode === 'demo'
          ? 'Seeded sensor context'
          : lightDetail(assignedSnapshot)
        : mode === 'demo'
          ? 'Waiting for seeded demo rows'
          : 'Waiting for sensor reconnect',
      changeType: freshLiveData ? ('positive' as const) : ('negative' as const),
      icon: Lightbulb,
      color: 'text-amber-500',
      bgColor: 'bg-amber-500/10',
      progressClass: 'bg-amber-500',
      progress: freshnessProgress(snapshot),
    },
    {
      title: 'Last Incident',
      value: freshLiveData ? (stateSummary?.incident ?? 'No urgent incident') : `No ${mode} data`,
      change:
        assignedSnapshot?.latest_incident?.room
          ? `${formatRoomName(assignedSnapshot.latest_incident.room, roomDisplayNames)} · ${assignedSnapshot.latest_incident.alert?.sent_success ? 'Alert sent' : 'No alert sent'}`
          : freshLiveData
            ? 'No likely fall recorded'
            : mode === 'demo'
              ? 'Waiting for seeded demo rows'
              : 'Waiting for sensor reconnect',
      changeType: freshLiveData
        ? snapshot?.latest_incident
          ? ('negative' as const)
          : ('positive' as const)
        : ('negative' as const),
      icon: ShieldAlert,
      color: assignedSnapshot?.latest_incident ? 'text-red-500' : 'text-orange-500',
      bgColor: assignedSnapshot?.latest_incident ? 'bg-red-500/10' : 'bg-orange-500/10',
      progressClass: assignedSnapshot?.latest_incident ? 'bg-red-500' : 'bg-orange-500',
      progress: assignedSnapshot?.latest_incident ? 76 : freshLiveData ? 92 : 28,
    },
  ];

  return (
    <SidebarProvider>
      <AdminSidebar />
      <SidebarInset>
        <DashboardHeader
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          onRefresh={() => void handleRefresh()}
          onExport={handleExport}
          isRefreshing={isRefreshing}
          searchPlaceholder={`Search ${mode} sensor events...`}
        />

        <div className="flex flex-1 flex-col gap-2 bg-[radial-gradient(circle_at_top_left,rgba(37,99,235,0.08),transparent_32rem),linear-gradient(180deg,var(--background),rgba(241,245,249,0.72))] p-2 pt-0 sm:gap-4 sm:p-4 dark:bg-[radial-gradient(circle_at_top_left,rgba(59,130,246,0.18),transparent_30rem),linear-gradient(180deg,var(--background),#09090b)]">
          <div className="min-h-[calc(100vh-4rem)] flex-1 rounded-lg p-3 sm:rounded-xl sm:p-4 md:p-6">
            <div className="mx-auto max-w-6xl space-y-4 sm:space-y-6">
              <div className="flex flex-col gap-3 px-2 sm:px-0">
                <div className="flex flex-wrap items-center gap-3">
                  <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
                    Caregiver Command Center
                  </h1>
                  <StatusPill
                    label={roomStatusLabel}
                    online={sensorOnline}
                    detail={
                      assignedSnapshot?.last_event_age_human
                        ? `Latest ${mode} row ${assignedSnapshot.last_event_age_human}`
                        : `No ${mode} sensor rows yet`
                    }
                  />
                  <StatusPill
                    label="Gemma4"
                    online={gemmaOnline}
                    detail={gemmaStatusLabel(status)}
                  />
                  <StatusPill
                    label="Telegram"
                    online={telegramOnline}
                    detail={
                      telegramOnline
                        ? 'Telegram alert channel has recent local alert activity'
                        : 'No Telegram alert activity is visible yet'
                    }
                  />
                </div>
                <p className="text-muted-foreground text-sm sm:text-base">
                  {mode === 'demo'
                    ? 'Reproducible judge demo data. Person presence, light context, incidents, Gemma findings, and alerts are seeded locally.'
                    : 'Real sensor data only. Person presence, light context, and incident state are all scoped to the live sensor stream.'}
                </p>
              </div>

              {error ? (
                <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{error}</span>
                </div>
              ) : null}

              {weeklyPdfError ? (
                <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{weeklyPdfError}</span>
                </div>
              ) : null}

              <div className="grid auto-rows-fr grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-4">
                {stats.map((stat, index) => (
                  <DashboardCard key={stat.title} stat={stat} index={index} />
                ))}
              </div>

              <CareTrendsCard
                trends={trends}
                analysis={trendAnalysis}
                analyzing={analyzingTrends}
                error={trendError}
                onAnalyze={() => void handleAnalyzeTrends()}
              />

              <IncidentStory snapshot={assignedSnapshot} events={assignedEvents} />

              <div className="grid grid-cols-1 gap-4 sm:gap-6 xl:grid-cols-3">
                <div className="space-y-4 sm:space-y-6 xl:col-span-2">
                  <RevenueChart events={assignedEvents} snapshot={assignedSnapshot} />
                  <UsersTable
                    events={visibleEvents}
                    onOpenResidents={() => router.push(`/residents?mode=${mode}`)}
                  />
                </div>

                <div className="space-y-4 sm:space-y-6">
                  <QuickActions
                    onRefresh={() => void handleRefresh()}
                    onExport={handleExport}
                    onGenerateWeeklyPdf={() => void handleGenerateWeeklyPdf()}
                    onOpenResidents={() => router.push(`/residents?mode=${mode}`)}
                    onOpenChat={() => router.push(`/chat?mode=${mode}`)}
                    onRunDemoFall={() => void handleDemoScenario('fall')}
                    onRunDemoScan={() => void handleDemoScenario('pattern-scan')}
                    weeklyPdfLoading={weeklyPdfLoading}
                    demoMode={mode === 'demo'}
                    demoActionLoading={demoActionLoading}
                  />
                  <SystemStatus status={status} snapshot={assignedSnapshot} />
                  <RecentActivity events={visibleEvents} alerts={visibleAlerts} />
                </div>
              </div>
            </div>
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
