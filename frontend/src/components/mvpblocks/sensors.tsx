'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Database,
  HeartPulse,
  Home,
  Loader2,
  Radio,
  ScanSearch,
  RotateCcw,
  Save,
  Shield,
  Tags,
  Palette,
  Trash2,
  TriangleAlert,
  Wind,
} from 'lucide-react';

import { AdminSidebar } from '@/components/ui/admin-sidebar';
import { DashboardHeader } from '@/components/ui/dashboard-header';
import { Button } from '@/components/ui/button';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import { confirmDestructiveAction } from '@/lib/confirm';
import {
  autoDetectNetworkSensors,
  deleteSensor,
  getCareContext,
  getEvents,
  getHealth,
  getLatestEventsBySensor,
  restartSensorIngestion,
  setSensorLed,
  updateCareContext,
} from '@/lib/api';
import {
  loadSensorRoomAssignments,
  saveSensorRoomAssignments,
  setAssignedRoom,
  type SensorRoomAssignments,
} from '@/lib/sensor-assignments';
import type {
  EventRead,
  CareContextRead,
  HealthResponse,
  SensorAutoDetectDevice,
} from '@/lib/types';

interface SensorRecord {
  sensorId: string;
  sensorType: string;
  configuredRoom?: string;
  host?: string;
  configuredLive: boolean;
  rgbLightConfigured: boolean;
  detectedRooms: string[];
  capabilities: string[];
  sources: string[];
  lastSeen?: string;
}

interface LiveReading {
  eventType: string;
  label: string;
  value: string;
  unit?: string;
  timestamp: string;
  ageSeconds: number | null;
}

const COMMON_ROOM_OPTIONS = [
  'living_room',
  'bedroom',
  'hallway',
  'bathroom',
  'kitchen',
  'demo_room',
  'bedside',
];

const MANUAL_ROOMS_STORAGE_KEY = 'emergyx-manual-rooms-v1';
const DELETED_ROOMS_STORAGE_KEY = 'emergyx-deleted-rooms-v1';
const DELETED_SENSORS_STORAGE_KEY = 'emergyx-deleted-sensors-v1';
const SENSOR_CONTEXT_STORAGE_KEY = 'emergyx-sensor-context-v1';
const SENSOR_NAMES_STORAGE_KEY = 'emergyx-sensor-names-v1';
const SENSOR_LED_COLORS_STORAGE_KEY = 'emergyx-sensor-led-colors-v1';
const LIVE_SENSOR_REFRESH_MS = 5000;
const LIVE_SENSOR_ONLINE_AGE_SECONDS = 15;
const DEFAULT_LED_COLOR = '#14b8a6';

function formatRoomName(room?: string | null) {
  if (!room) {
    return 'Unassigned';
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

function normalizeRoomName(roomName: string) {
  return roomName.trim().replace(/\s+/g, ' ');
}

function loadManualRooms(): string[] {
  if (typeof window === 'undefined') {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(MANUAL_ROOMS_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as unknown[];
    if (!Array.isArray(parsed)) {
      return [];
    }
    const rooms = parsed
      .map((item) => (typeof item === 'string' ? normalizeRoomName(item) : ''))
      .filter((item) => item.length > 0);
    return Array.from(new Set(rooms)).sort((a, b) => a.localeCompare(b));
  } catch {
    return [];
  }
}

function saveManualRooms(rooms: string[]) {
  if (typeof window === 'undefined') {
    return;
  }
  const clean = Array.from(
    new Set(
      rooms
        .map((item) => normalizeRoomName(item))
        .filter((item) => item.length > 0),
    ),
  ).sort((a, b) => a.localeCompare(b));
  window.localStorage.setItem(MANUAL_ROOMS_STORAGE_KEY, JSON.stringify(clean));
}

function loadDeletedRooms(): string[] {
  if (typeof window === 'undefined') {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(DELETED_ROOMS_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as unknown[];
    if (!Array.isArray(parsed)) {
      return [];
    }
    const rooms = parsed
      .map((item) => (typeof item === 'string' ? normalizeRoomName(item) : ''))
      .filter((item) => item.length > 0);
    return Array.from(new Set(rooms)).sort((a, b) => a.localeCompare(b));
  } catch {
    return [];
  }
}

function saveDeletedRooms(rooms: string[]) {
  if (typeof window === 'undefined') {
    return;
  }
  const clean = Array.from(
    new Set(
      rooms
        .map((item) => normalizeRoomName(item))
        .filter((item) => item.length > 0),
    ),
  ).sort((a, b) => a.localeCompare(b));
  window.localStorage.setItem(DELETED_ROOMS_STORAGE_KEY, JSON.stringify(clean));
}

function loadDeletedSensorIds(): string[] {
  if (typeof window === 'undefined') {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(DELETED_SENSORS_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as unknown[];
    if (!Array.isArray(parsed)) {
      return [];
    }
    return Array.from(
      new Set(parsed.filter((item): item is string => typeof item === 'string')),
    ).sort();
  } catch {
    return [];
  }
}

function saveDeletedSensorIds(sensorIds: string[]) {
  if (typeof window === 'undefined') {
    return;
  }
  const clean = Array.from(new Set(sensorIds)).sort();
  window.localStorage.setItem(DELETED_SENSORS_STORAGE_KEY, JSON.stringify(clean));
}

function normalizeSensorContext(value: string) {
  return value.trim().replace(/\s+/g, ' ');
}

function normalizeSensorName(value: string) {
  return value.trim().replace(/\s+/g, ' ');
}

function loadSensorNames(): Record<string, string> {
  if (typeof window === 'undefined') {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(SENSOR_NAMES_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const names: Record<string, string> = {};
    for (const [sensorId, nameValue] of Object.entries(parsed)) {
      if (typeof nameValue !== 'string') {
        continue;
      }
      const name = normalizeSensorName(nameValue);
      if (sensorId && name) {
        names[sensorId] = name;
      }
    }
    return names;
  } catch {
    return {};
  }
}

function saveSensorNames(names: Record<string, string>) {
  if (typeof window === 'undefined') {
    return;
  }
  const clean: Record<string, string> = {};
  for (const [sensorId, nameValue] of Object.entries(names)) {
    const name = normalizeSensorName(nameValue);
    if (sensorId && name) {
      clean[sensorId] = name;
    }
  }
  window.localStorage.setItem(SENSOR_NAMES_STORAGE_KEY, JSON.stringify(clean));
}

function loadSensorContexts(): Record<string, string> {
  if (typeof window === 'undefined') {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(SENSOR_CONTEXT_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const contexts: Record<string, string> = {};
    for (const [sensorId, contextValue] of Object.entries(parsed)) {
      if (typeof contextValue !== 'string') {
        continue;
      }
      const context = normalizeSensorContext(contextValue);
      if (sensorId && context) {
        contexts[sensorId] = context;
      }
    }
    return contexts;
  } catch {
    return {};
  }
}

function saveSensorContexts(contexts: Record<string, string>) {
  if (typeof window === 'undefined') {
    return;
  }
  const clean: Record<string, string> = {};
  for (const [sensorId, contextValue] of Object.entries(contexts)) {
    const context = normalizeSensorContext(contextValue);
    if (sensorId && context) {
      clean[sensorId] = context;
    }
  }
  window.localStorage.setItem(SENSOR_CONTEXT_STORAGE_KEY, JSON.stringify(clean));
}

function normalizeLedColor(value: string) {
  const clean = value.trim();
  return /^#[0-9a-fA-F]{6}$/.test(clean) ? clean.toLowerCase() : '';
}

function loadSensorLedColors(): Record<string, string> {
  if (typeof window === 'undefined') {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(SENSOR_LED_COLORS_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const colors: Record<string, string> = {};
    for (const [sensorId, colorValue] of Object.entries(parsed)) {
      if (typeof colorValue !== 'string') {
        continue;
      }
      const color = normalizeLedColor(colorValue);
      if (sensorId && color) {
        colors[sensorId] = color;
      }
    }
    return colors;
  } catch {
    return {};
  }
}

function saveSensorLedColors(colors: Record<string, string>) {
  if (typeof window === 'undefined') {
    return;
  }
  const clean: Record<string, string> = {};
  for (const [sensorId, colorValue] of Object.entries(colors)) {
    const color = normalizeLedColor(colorValue);
    if (sensorId && color) {
      clean[sensorId] = color;
    }
  }
  window.localStorage.setItem(SENSOR_LED_COLORS_STORAGE_KEY, JSON.stringify(clean));
}

function sensorAgeSeconds(lastSeen?: string) {
  if (!lastSeen) {
    return null;
  }
  const parsed = Date.parse(lastSeen);
  if (Number.isNaN(parsed)) {
    return null;
  }
  const age = Math.floor((Date.now() - parsed) / 1000);
  return age < 0 ? 0 : age;
}

function isSensorOnline(lastSeen: string | undefined, maxAgeSeconds: number) {
  const ageSeconds = sensorAgeSeconds(lastSeen);
  if (ageSeconds === null) {
    return false;
  }
  return ageSeconds < maxAgeSeconds;
}

function prettySource(source: string) {
  if (source === 'live_sensor') {
    return 'Live';
  }
  if (source === 'manual') {
    return 'Manual';
  }
  if (source === 'simulated_seed') {
    return 'Demo baseline';
  }
  if (source === 'simulated') {
    return 'Demo';
  }
  return source.replace(/_/g, ' ');
}

function inferType(
  sensorId: string,
  capabilities: Set<string>,
  configuredByHealth: boolean,
  sensorFamily?: string,
) {
  const family = (sensorFamily ?? '').toLowerCase();
  if (family === 'heart_breath_bha2') {
    return 'Heart/respiration sensor';
  }
  if (configuredByHealth) {
    return 'mmWave fall sensor';
  }
  const lowered = sensorId.toLowerCase();
  if (lowered.includes('bha2') || capabilities.has('Sleep summary')) {
    return 'Bedside heart/respiration sensor';
  }
  if (capabilities.has('Likely fall') || capabilities.has('Presence')) {
    return 'mmWave fall/presence sensor';
  }
  return 'Local timeline sensor';
}

function capabilityForEventType(eventType: string) {
  if (eventType === 'heart_rate') {
    return 'Heart rate';
  }
  if (eventType === 'respiration_rate') {
    return 'Respiration';
  }
  if (eventType === 'target_distance') {
    return 'Distance';
  }
  if (eventType === 'target_number') {
    return 'Targets';
  }
  if (eventType === 'person_present') {
    return 'Presence';
  }
  if (eventType === 'fall_detected') {
    return 'Likely fall';
  }
  if (eventType === 'illuminance') {
    return 'Light';
  }
  if (eventType === 'sleep_summary_placeholder') {
    return 'Sleep summary';
  }
  return eventType.replace(/_/g, ' ');
}

function liveReadingLabel(eventType: string) {
  if (eventType === 'heart_rate') {
    return 'Heart rate';
  }
  if (eventType === 'respiration_rate') {
    return 'Breathing rate';
  }
  if (eventType === 'target_distance') {
    return 'Distance';
  }
  if (eventType === 'target_number') {
    return 'Targets';
  }
  if (eventType === 'person_present') {
    return 'Presence';
  }
  if (eventType === 'fall_detected') {
    return 'Fall state';
  }
  if (eventType === 'illuminance') {
    return 'Light';
  }
  return capabilityForEventType(eventType);
}

function liveReadingUnit(eventType: string) {
  if (eventType === 'heart_rate') {
    return 'bpm';
  }
  if (eventType === 'respiration_rate') {
    return 'br/min';
  }
  if (eventType === 'illuminance') {
    return 'lux';
  }
  if (eventType === 'target_distance') {
    return 'cm';
  }
  return undefined;
}

function formatLiveReadingValue(reading: LiveReading) {
  if (reading.eventType === 'person_present') {
    return ['true', '1', 'yes'].includes(reading.value.toLowerCase())
      ? 'Present'
      : 'Clear';
  }

  const parsed = Number(reading.value);
  if (!Number.isFinite(parsed)) {
    return reading.value;
  }
  if (reading.eventType === 'target_distance') {
    return parsed.toFixed(1);
  }
  if (
    reading.eventType === 'heart_rate' ||
    reading.eventType === 'respiration_rate' ||
    reading.eventType === 'target_number'
  ) {
    return String(Math.round(parsed));
  }
  if (reading.eventType === 'illuminance') {
    return parsed.toFixed(0);
  }
  return reading.value;
}

function isPrimaryLiveReading(eventType: string) {
  return (
    eventType === 'heart_rate' ||
    eventType === 'respiration_rate' ||
    eventType === 'person_present' ||
    eventType === 'fall_detected' ||
    eventType === 'illuminance' ||
    eventType === 'target_distance' ||
    eventType === 'target_number'
  );
}

function latestLiveReadingsForSensor(events: EventRead[], sensorId: string) {
  const latest = new Map<string, EventRead>();
  const latestMs = new Map<string, number>();
  for (const event of events) {
    if (event.sensor_id !== sensorId || !isPrimaryLiveReading(event.event_type)) {
      continue;
    }
    const parsedMs = Date.parse(event.timestamp);
    if (Number.isNaN(parsedMs)) {
      continue;
    }
    const currentMs = latestMs.get(event.event_type);
    if (currentMs === undefined || parsedMs > currentMs) {
      latestMs.set(event.event_type, parsedMs);
      latest.set(event.event_type, event);
    }
  }

  const priority = [
    'heart_rate',
    'respiration_rate',
    'person_present',
    'fall_detected',
    'target_distance',
    'target_number',
    'illuminance',
  ];
  return Array.from(latest.values())
    .sort((a, b) => {
      const priorityDelta =
        priority.indexOf(a.event_type) - priority.indexOf(b.event_type);
      if (priorityDelta !== 0) {
        return priorityDelta;
      }
      return Date.parse(b.timestamp) - Date.parse(a.timestamp);
    })
    .map((event): LiveReading => ({
      eventType: event.event_type,
      label: liveReadingLabel(event.event_type),
      value: event.value,
      unit: liveReadingUnit(event.event_type),
      timestamp: event.timestamp,
      ageSeconds: sensorAgeSeconds(event.timestamp),
    }));
}

function LiveReadingIcon({ eventType }: { eventType: string }) {
  if (eventType === 'heart_rate') {
    return <HeartPulse className="h-4 w-4" />;
  }
  if (eventType === 'respiration_rate') {
    return <Wind className="h-4 w-4" />;
  }
  return <Activity className="h-4 w-4" />;
}

function buildSensorRecords(
  health: HealthResponse | null,
  events: EventRead[],
): SensorRecord[] {
  const bySensor = new Map<
    string,
    {
      configuredRoom?: string;
      host?: string;
      capabilities: Set<string>;
      sources: Set<string>;
      detectedRooms: Set<string>;
      lastSeen?: string;
      configuredByHealth: boolean;
      rgbLightConfigured: boolean;
      sensorFamily?: string;
    }
  >();

  for (const sensor of health?.fda2_sensors ?? []) {
    const sensorFamily = sensor.sensor_family ?? 'fall_fda2';
    const defaultCapabilities =
      sensorFamily === 'heart_breath_bha2'
        ? new Set(['Respiration', 'Heart rate'])
        : new Set(['Presence', 'Likely fall', 'Light']);
    bySensor.set(sensor.sensor_id, {
      configuredRoom: sensor.room,
      host: sensor.host,
      capabilities: defaultCapabilities,
      sources: new Set(['live_sensor']),
      detectedRooms: new Set(sensor.room ? [sensor.room] : []),
      configuredByHealth: true,
      rgbLightConfigured: Boolean(sensor.rgb_light_configured),
      sensorFamily,
    });
  }

  for (const event of events) {
    const current = bySensor.get(event.sensor_id) ?? {
      capabilities: new Set<string>(),
      sources: new Set<string>(),
      detectedRooms: new Set<string>(),
      configuredByHealth: false,
      rgbLightConfigured: false,
      sensorFamily: undefined,
    };
    current.capabilities.add(capabilityForEventType(event.event_type));
    current.sources.add(event.source);
    if (event.room) {
      current.detectedRooms.add(event.room);
    }
    if (!current.lastSeen || event.timestamp > current.lastSeen) {
      current.lastSeen = event.timestamp;
    }
    bySensor.set(event.sensor_id, current);
  }

  return Array.from(bySensor.entries())
    .map(([sensorId, record]) => ({
      sensorId,
      sensorType: inferType(
        sensorId,
        record.capabilities,
        record.configuredByHealth,
        record.sensorFamily,
      ),
      configuredRoom: record.configuredRoom,
      host: record.host,
      configuredLive: record.configuredByHealth,
      rgbLightConfigured: record.rgbLightConfigured,
      detectedRooms: Array.from(record.detectedRooms).sort(),
      capabilities: Array.from(record.capabilities).sort(),
      sources: Array.from(record.sources).sort(),
      lastSeen: record.lastSeen,
    }))
    .sort((a, b) => a.sensorId.localeCompare(b.sensorId));
}

export function SensorsDashboard() {
  const isLivePollingRef = useRef(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isAutoDetecting, setIsAutoDetecting] = useState(false);
  const [isRestartingIngestion, setIsRestartingIngestion] = useState(false);
  const [deletingSensorId, setDeletingSensorId] = useState<string | null>(null);
  const [configuringSensorId, setConfiguringSensorId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [careContext, setCareContext] = useState<CareContextRead | null>(null);
  const [liveEvents, setLiveEvents] = useState<EventRead[]>([]);
  const [latestLiveEvents, setLatestLiveEvents] = useState<EventRead[]>([]);
  const [demoEvents, setDemoEvents] = useState<EventRead[]>([]);
  const [assignments, setAssignments] = useState<SensorRoomAssignments>(() =>
    loadSensorRoomAssignments(),
  );
  const [manualRooms, setManualRooms] = useState<string[]>(() => loadManualRooms());
  const [deletedRooms, setDeletedRooms] = useState<string[]>(() => loadDeletedRooms());
  const [deletedSensorIds, setDeletedSensorIds] = useState<string[]>(() =>
    loadDeletedSensorIds(),
  );
  const [draftRooms, setDraftRooms] = useState<Record<string, string>>({});
  const [sensorNames, setSensorNames] = useState<Record<string, string>>(() =>
    loadSensorNames(),
  );
  const [sensorContexts, setSensorContexts] = useState<Record<string, string>>(() =>
    loadSensorContexts(),
  );
  const [expandedSensorData, setExpandedSensorData] = useState<Record<string, boolean>>({});
  const [expandedSensorSetup, setExpandedSensorSetup] = useState<Record<string, boolean>>({});
  const [expandedSensorContext, setExpandedSensorContext] = useState<Record<string, boolean>>({});
  const [expandedSensorControls, setExpandedSensorControls] = useState<Record<string, boolean>>({});
  const [roomsExpanded, setRoomsExpanded] = useState(false);
  const [addRoomName, setAddRoomName] = useState('');
  const [roomFeedback, setRoomFeedback] = useState<string | null>(null);
  const [savedSensor, setSavedSensor] = useState<string | null>(null);
  const [ledColors, setLedColors] = useState<Record<string, string>>(() =>
    loadSensorLedColors(),
  );
  const [ledPending, setLedPending] = useState<string | null>(null);
  const [ledFeedback, setLedFeedback] = useState<
    Record<string, { tone: 'success' | 'error'; message: string }>
  >({});
  const [autoDetectedSensors, setAutoDetectedSensors] = useState<SensorRecord[]>([]);
  const [autoDetectStatus, setAutoDetectStatus] = useState<string | null>(null);

  const fetchSensorData = useCallback(async () => {
    const [healthPayload, liveEvents, latestLiveEvents, demoEvents, careContextPayload] = await Promise.all([
      getHealth(),
      getEvents('live', 200),
      getLatestEventsBySensor('live'),
      getEvents('demo', 250),
      getCareContext(),
    ]);
    return {
      healthPayload,
      liveEvents,
      latestLiveEvents,
      demoEvents,
      careContextPayload,
      allEvents: [...latestLiveEvents, ...liveEvents, ...demoEvents],
    };
  }, []);

  const loadPage = useCallback(async () => {
    setError(null);
    const payload = await fetchSensorData();
    setHealth(payload.healthPayload);
    setLiveEvents(payload.liveEvents);
    setLatestLiveEvents(payload.latestLiveEvents);
    setDemoEvents(payload.demoEvents);
    let nextContext = payload.careContextPayload;
    const needsMigration =
      nextContext.manual_rooms.length === 0 &&
      nextContext.deleted_rooms.length === 0 &&
      Object.keys(nextContext.sensor_assignments).length === 0 &&
      Object.keys(nextContext.sensor_names).length === 0 &&
      Object.keys(nextContext.sensor_contexts).length === 0 &&
      Object.keys(nextContext.sensor_led_colors).length === 0;
    if (needsMigration) {
      const migrated = {
        ...nextContext,
        manual_rooms: loadManualRooms(),
        deleted_rooms: loadDeletedRooms(),
        sensor_assignments: loadSensorRoomAssignments(),
        sensor_names: loadSensorNames(),
        sensor_contexts: loadSensorContexts(),
        sensor_led_colors: loadSensorLedColors(),
      };
      const response = await updateCareContext(migrated);
      nextContext = response.context;
    }
    setCareContext(nextContext);
    setManualRooms(nextContext.manual_rooms);
    setDeletedRooms(nextContext.deleted_rooms);
    setAssignments(nextContext.sensor_assignments);
    setSensorNames(nextContext.sensor_names);
    setSensorContexts(nextContext.sensor_contexts);
    setLedColors(nextContext.sensor_led_colors);
  }, [fetchSensorData]);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      try {
        setIsRefreshing(true);
        await loadPage();
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : 'Unable to load sensors.',
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
  }, [loadPage]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      if (isLivePollingRef.current || document.hidden) {
        return;
      }
      isLivePollingRef.current = true;
      void loadPage()
        .catch((pollError) => {
          setError(
            pollError instanceof Error
              ? pollError.message
              : 'Unable to refresh live sensors.',
          );
        })
        .finally(() => {
          isLivePollingRef.current = false;
        });
    }, LIVE_SENSOR_REFRESH_MS);

    return () => window.clearInterval(intervalId);
  }, [loadPage]);

  const allEvents = useMemo(
    () => [...latestLiveEvents, ...liveEvents, ...demoEvents],
    [latestLiveEvents, liveEvents, demoEvents],
  );
  const allSensors = useMemo(() => buildSensorRecords(health, allEvents), [health, allEvents]);

  const liveConfiguredSensorIds = useMemo(() => {
    const ids = new Set<string>();
    for (const sensor of health?.fda2_sensors ?? []) {
      ids.add(sensor.sensor_id);
    }
    return ids;
  }, [health]);
  const onlineAgeSeconds = LIVE_SENSOR_ONLINE_AGE_SECONDS;

  const latestLiveTimestampBySensor = useMemo(() => {
    const bySensor = new Map<string, string>();
    const bySensorMs = new Map<string, number>();
    for (const event of liveEvents) {
      const parsedMs = Date.parse(event.timestamp);
      if (Number.isNaN(parsedMs)) {
        continue;
      }
      const currentMs = bySensorMs.get(event.sensor_id);
      if (currentMs === undefined || parsedMs > currentMs) {
        bySensorMs.set(event.sensor_id, parsedMs);
        bySensor.set(event.sensor_id, event.timestamp);
      }
    }
    return bySensor;
  }, [liveEvents]);

  const latestLiveTimestamp = useMemo(() => {
    let latestMs = -1;
    let latestTs: string | null = null;
    for (const event of liveEvents) {
      const parsedMs = Date.parse(event.timestamp);
      if (!Number.isNaN(parsedMs) && parsedMs > latestMs) {
        latestMs = parsedMs;
        latestTs = event.timestamp;
      }
    }
    return latestTs;
  }, [liveEvents]);

  const connectedSensorIds = useMemo(() => {
    const ids = new Set<string>();
    const deleted = new Set(deletedSensorIds);
    for (const sensor of health?.fda2_sensors ?? []) {
      if (!deleted.has(sensor.sensor_id)) {
        ids.add(sensor.sensor_id);
      }
    }
    for (const event of liveEvents) {
      if (!deleted.has(event.sensor_id)) {
        ids.add(event.sensor_id);
      }
    }
    return ids;
  }, [health, liveEvents, deletedSensorIds]);

  const sensors = useMemo(() => {
    const recordsById = new Map(allSensors.map((sensor) => [sensor.sensorId, sensor]));
    const connectedRecords: SensorRecord[] = [];
    for (const sensorId of connectedSensorIds) {
      const record = recordsById.get(sensorId);
      if (record) {
        connectedRecords.push(record);
      }
    }
    return connectedRecords.sort((a, b) => a.sensorId.localeCompare(b.sensorId));
  }, [allSensors, connectedSensorIds]);

  const filteredSensors = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) {
      return sensors;
    }
    return sensors.filter((sensor) =>
      [
        sensor.sensorId,
        sensor.sensorType,
        sensor.configuredRoom,
        ...sensor.detectedRooms,
        ...sensor.capabilities,
      ]
        .join(' ')
        .toLowerCase()
        .includes(q),
    );
  }, [sensors, searchQuery]);

  const roomOptions = useMemo(() => {
    const deleted = new Set(deletedRooms);
    const set = new Set<string>(COMMON_ROOM_OPTIONS);
    for (const sensor of sensors) {
      if (sensor.configuredRoom) {
        set.add(sensor.configuredRoom);
      }
      for (const room of sensor.detectedRooms) {
        set.add(room);
      }
      if (assignments[sensor.sensorId]) {
        set.add(assignments[sensor.sensorId]);
      }
    }
    for (const room of manualRooms) {
      set.add(room);
    }
    return Array.from(set)
      .filter((room) => !deleted.has(room))
      .sort();
  }, [sensors, assignments, manualRooms, deletedRooms]);

  const roomRows = useMemo(() => {
    const manualSet = new Set(manualRooms);
    const commonSet = new Set(COMMON_ROOM_OPTIONS);
    return roomOptions.map((room) => {
      const assignedSensors = sensors.filter((sensor) => {
        const assignedRoom =
          assignments[sensor.sensorId] ??
          sensor.configuredRoom ??
          sensor.detectedRooms[0] ??
          '';
        return assignedRoom === room;
      });
      const detectedSensorCount = sensors.filter((sensor) =>
        sensor.detectedRooms.includes(room),
      ).length;
      const sources = [
        manualSet.has(room) ? 'Custom' : null,
        commonSet.has(room) ? 'Default' : null,
        detectedSensorCount > 0 ? 'Detected' : null,
        assignedSensors.length > 0 ? 'Assigned' : null,
      ].filter(Boolean) as string[];
      return {
        room,
        label: formatRoomName(room),
        assignedSensorCount: assignedSensors.length,
        detectedSensorCount,
        sources,
      };
    });
  }, [assignments, manualRooms, roomOptions, sensors]);

  const refresh = async () => {
    try {
      setIsRefreshing(true);
      await loadPage();
    } catch (refreshError) {
      setError(
        refreshError instanceof Error
          ? refreshError.message
          : 'Unable to refresh sensors.',
      );
    } finally {
      setIsRefreshing(false);
    }
  };

  const exportAssignments = () => {
    const payload = {
      exported_at: new Date().toISOString(),
      assignments,
      manual_rooms: manualRooms,
      deleted_rooms: deletedRooms,
      sensor_names: sensorNames,
      sensor_contexts: sensorContexts,
      sensor_led_colors: ledColors,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: 'application/json;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'sensor-room-assignments.json';
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const persistCareContext = async (partial: Partial<CareContextRead>) => {
    const base = careContext ?? (await getCareContext());
    const response = await updateCareContext({
      ...base,
      residents: base.residents,
      manual_rooms: manualRooms,
      deleted_rooms: deletedRooms,
      sensor_assignments: assignments,
      sensor_names: sensorNames,
      sensor_contexts: sensorContexts,
      sensor_led_colors: ledColors,
      room_display_names: base.room_display_names,
      ...partial,
    });
    setCareContext(response.context);
    return response.context;
  };

  const draftValueFor = (sensor: SensorRecord) =>
    draftRooms[sensor.sensorId] ??
    assignments[sensor.sensorId] ??
    sensor.configuredRoom ??
    sensor.detectedRooms[0] ??
    '';

  const saveRoom = (sensor: SensorRecord) => {
    void saveRoomValue(sensor.sensorId, draftValueFor(sensor));
  };

  const saveRoomValue = async (sensorId: string, roomValue: string) => {
    const nextAssignments = setAssignedRoom(
      assignments,
      sensorId,
      roomValue,
    );
    setAssignments(nextAssignments);
    saveSensorRoomAssignments(nextAssignments);
    try {
      await persistCareContext({ sensor_assignments: nextAssignments });
      setSavedSensor(sensorId);
      window.setTimeout(() => setSavedSensor(null), 2000);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Unable to save sensor room.');
    }
  };

  const updateSensorContext = (sensorId: string, value: string) => {
    setSensorContexts((current) => {
      const next = { ...current };
      const normalized = normalizeSensorContext(value);
      if (normalized) {
        next[sensorId] = value;
      } else {
        delete next[sensorId];
      }
      saveSensorContexts(next);
      void persistCareContext({ sensor_contexts: next }).catch((saveError) => {
        setError(saveError instanceof Error ? saveError.message : 'Unable to save sensor context.');
      });
      return next;
    });
  };

  const updateSensorName = (sensorId: string, value: string) => {
    setSensorNames((current) => {
      const next = { ...current };
      const normalized = normalizeSensorName(value);
      if (normalized) {
        next[sensorId] = value;
      } else {
        delete next[sensorId];
      }
      saveSensorNames(next);
      void persistCareContext({ sensor_names: next }).catch((saveError) => {
        setError(saveError instanceof Error ? saveError.message : 'Unable to save sensor name.');
      });
      return next;
    });
  };

  const toggleSensorData = (sensorId: string) => {
    setExpandedSensorData((current) => ({
      ...current,
      [sensorId]: !current[sensorId],
    }));
  };

  const toggleSensorSetup = (sensorId: string) => {
    setExpandedSensorSetup((current) => ({
      ...current,
      [sensorId]: !current[sensorId],
    }));
  };

  const toggleSensorContext = (sensorId: string) => {
    setExpandedSensorContext((current) => ({
      ...current,
      [sensorId]: !current[sensorId],
    }));
  };

  const toggleSensorControls = (sensorId: string) => {
    setExpandedSensorControls((current) => ({
      ...current,
      [sensorId]: !current[sensorId],
    }));
  };

  const addRoom = async () => {
    const clean = normalizeRoomName(addRoomName);
    if (!clean) {
      return;
    }
    if (deletedRooms.includes(clean)) {
      const nextDeleted = deletedRooms.filter((room) => room !== clean);
      setDeletedRooms(nextDeleted);
      saveDeletedRooms(nextDeleted);
      try {
        await persistCareContext({ deleted_rooms: nextDeleted });
      } catch (saveError) {
        setError(saveError instanceof Error ? saveError.message : 'Unable to restore room.');
      }
    }
    if (roomOptions.includes(clean)) {
      setRoomFeedback(`${formatRoomName(clean)} already exists.`);
      setAddRoomName('');
      return;
    }
    const merged = Array.from(new Set([...manualRooms, clean])).sort((a, b) =>
      a.localeCompare(b),
    );
    setManualRooms(merged);
    saveManualRooms(merged);
    try {
      await persistCareContext({ manual_rooms: merged });
      setAddRoomName('');
      setRoomFeedback(`${formatRoomName(clean)} added.`);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Unable to add room.');
    }
  };

  const colorForSensor = (sensorId: string) =>
    ledColors[sensorId] ?? DEFAULT_LED_COLOR;

  const updateLedColor = (sensorId: string, value: string) => {
    const color = normalizeLedColor(value);
    if (!color) {
      return;
    }
    setLedColors((current) => {
      const next = {
        ...current,
        [sensorId]: color,
      };
      saveSensorLedColors(next);
      void persistCareContext({ sensor_led_colors: next }).catch((saveError) => {
        setLedFeedback((feedbackBySensor) => ({
          ...feedbackBySensor,
          [sensorId]: {
            tone: 'error',
            message:
              saveError instanceof Error
                ? saveError.message
                : 'Unable to save RGB color.',
          },
        }));
      });
      return next;
    });
  };

  const runLedCommand = async (
    sensorId: string,
    action: 'detect' | 'off',
    configuredLive: boolean,
  ) => {
    if (!configuredLive) {
      setLedFeedback((current) => ({
        ...current,
        [sensorId]: {
          tone: 'error',
          message:
            'Not configured for live ingestion yet. Add this sensor in Settings or the sensor environment config, then restart ingestion.',
        },
      }));
      return;
    }

    const actionKey = `${sensorId}:${action}`;
    setLedPending(actionKey);
    setLedFeedback((current) => {
      const next = { ...current };
      delete next[sensorId];
      return next;
    });

    try {
      const response = await setSensorLed({
        sensor_id: sensorId,
        hex_color: action === 'off' ? null : colorForSensor(sensorId),
        brightness: 0.85,
        flash_seconds: action === 'detect' ? 10 : null,
        turn_off: action === 'off',
      });
      setLedFeedback((current) => ({
        ...current,
        [sensorId]: {
          tone: 'success',
          message: response.discovered
            ? `${response.message} RGB key auto-discovered.`
            : response.message,
        },
      }));
    } catch (ledError) {
      setLedFeedback((current) => ({
        ...current,
        [sensorId]: {
          tone: 'error',
          message:
            ledError instanceof Error
              ? ledError.message
              : 'Unable to send LED command.',
        },
      }));
    } finally {
      setLedPending(null);
    }
  };

  const removeRoom = async (room: string) => {
    const assignedCount = Object.values(assignments).filter(
      (assignedRoom) => assignedRoom === room,
    ).length;
    const message =
      assignedCount > 0
        ? `Delete ${formatRoomName(room)}? This will also unassign ${assignedCount} sensor${assignedCount === 1 ? '' : 's'} currently using this room.`
        : `Delete ${formatRoomName(room)}?`;
    if (!confirmDestructiveAction(message)) {
      return;
    }
    const nextRooms = manualRooms.filter((item) => item !== room);
    setManualRooms(nextRooms);
    saveManualRooms(nextRooms);
    if (!deletedRooms.includes(room)) {
      const nextDeletedRooms = [...deletedRooms, room].sort((a, b) => a.localeCompare(b));
      setDeletedRooms(nextDeletedRooms);
      saveDeletedRooms(nextDeletedRooms);
      try {
        await persistCareContext({
          manual_rooms: nextRooms,
          deleted_rooms: nextDeletedRooms,
        });
      } catch (saveError) {
        setError(saveError instanceof Error ? saveError.message : 'Unable to delete room.');
      }
    }

    // Clear assignments that referenced the removed manual room.
    const nextAssignments: SensorRoomAssignments = { ...assignments };
    let changed = false;
    for (const [sensorId, assignedRoom] of Object.entries(nextAssignments)) {
      if (assignedRoom === room) {
        delete nextAssignments[sensorId];
        changed = true;
      }
    }
    if (changed) {
      setAssignments(nextAssignments);
      saveSensorRoomAssignments(nextAssignments);
      try {
        await persistCareContext({
          manual_rooms: nextRooms,
          deleted_rooms: deletedRooms.includes(room)
            ? deletedRooms
            : [...deletedRooms, room].sort((a, b) => a.localeCompare(b)),
          sensor_assignments: nextAssignments,
        });
      } catch (saveError) {
        setError(saveError instanceof Error ? saveError.message : 'Unable to clear room assignments.');
      }
    }
    setRoomFeedback(`${formatRoomName(room)} deleted.`);
  };

  const autoDetectSensors = async () => {
    setAutoDetectedSensors([]);
    setAutoDetectStatus('Scanning local network and timeline...');
    setIsAutoDetecting(true);

    try {
      const baselineIds = new Set(connectedSensorIds);
      const discovery = await autoDetectNetworkSensors({
        include_subnet_scan: true,
        timeout_seconds: 1.5,
        concurrency: 24,
      });
      const payload = await fetchSensorData();
      setHealth(payload.healthPayload);
      setLiveEvents(payload.liveEvents);
      setLatestLiveEvents(payload.latestLiveEvents);
      setDemoEvents(payload.demoEvents);

      const scanned = buildSensorRecords(payload.healthPayload, payload.allEvents);
      const scannedById = new Map(scanned.map((sensor) => [sensor.sensorId, sensor]));
      const found = new Map<string, SensorRecord>();

      for (const sensor of scanned) {
        if (!baselineIds.has(sensor.sensorId)) {
          found.set(sensor.sensorId, sensor);
        }
      }

      const fallbackRecordFromDiscovery = (device: SensorAutoDetectDevice): SensorRecord => {
        const discoveredType =
          device.sensor_family === 'heart_breath_bha2'
            ? 'Heart/respiration sensor'
            : device.sensor_family === 'fall_fda2'
              ? 'mmWave fall sensor'
              : 'Detected local sensor';
        const capabilities =
          device.sensor_family === 'heart_breath_bha2'
            ? ['Respiration', 'Heart rate']
            : device.sensor_family === 'fall_fda2'
              ? ['Presence', 'Likely fall', 'Light']
              : [];
        return {
          sensorId: device.sensor_id,
          sensorType: discoveredType,
          configuredRoom: undefined,
          host: device.host,
          configuredLive: device.configured_for_live_ingestion,
          rgbLightConfigured: typeof device.rgb_light_key === 'number',
          detectedRooms: [],
          capabilities,
          sources: [device.configured_for_live_ingestion ? 'live_sensor' : 'manual'],
          lastSeen: undefined,
        };
      };

      for (const device of discovery.discovered) {
        const sensorId = device.sensor_id.trim();
        if (!sensorId || baselineIds.has(sensorId)) {
          continue;
        }
        found.set(
          sensorId,
          scannedById.get(sensorId) ?? fallbackRecordFromDiscovery(device),
        );
      }

      const foundSensors = Array.from(found.values()).sort((a, b) => a.sensorId.localeCompare(b.sensorId));
      setAutoDetectedSensors(foundSensors);
      if (foundSensors.length > 0 && deletedSensorIds.length > 0) {
        const foundIds = new Set(foundSensors.map((sensor) => sensor.sensorId));
        const nextDeleted = deletedSensorIds.filter((sensorId) => !foundIds.has(sensorId));
        if (nextDeleted.length !== deletedSensorIds.length) {
          setDeletedSensorIds(nextDeleted);
          saveDeletedSensorIds(nextDeleted);
        }
      }

      const totalDetected = discovery.discovered.length;
      const fallDetected = discovery.discovered.filter(
        (device) => device.sensor_family === 'fall_fda2',
      ).length;
      const bha2Detected = discovery.discovered.filter(
        (device) => device.sensor_family === 'heart_breath_bha2',
      ).length;
      const configuredDetected = discovery.discovered.filter(
        (device) => device.configured_for_live_ingestion,
      ).length;
      if (configuredDetected > 0) {
        try {
          await restartSensorIngestion();
          await refresh();
        } catch {
          // Ingestion manager is dynamic; explicit restart is best-effort only.
        }
      }
      if (totalDetected > 0) {
        setAutoDetectStatus(
          `Detected ${totalDetected} device(s): ${fallDetected} fall, ${bha2Detected} heart/respiration. ${configuredDetected} configured for live ingestion.`,
        );
      } else {
        setAutoDetectStatus('No sensors discovered on this network scan.');
      }
    } catch (scanError) {
      setAutoDetectStatus(
        scanError instanceof Error
          ? scanError.message
          : 'Auto-detect failed.',
      );
    } finally {
      setIsAutoDetecting(false);
    }
  };

  const configureSensor = async (sensor: SensorRecord) => {
    if (!sensor.host) {
      setAutoDetectStatus(
        `Sensor ${sensor.sensorId} has no host address yet. Run auto-detect first.`,
      );
      return;
    }
    setConfiguringSensorId(sensor.sensorId);
    try {
      const roomHint =
        assignments[sensor.sensorId] ??
        sensor.configuredRoom ??
        sensor.detectedRooms[0] ??
        '';
      const response = await autoDetectNetworkSensors({
        hosts: [sensor.host],
        include_subnet_scan: false,
        timeout_seconds: 2.0,
        concurrency: 1,
        room_hint: roomHint || undefined,
      });
      await refresh();
      const matched = response.discovered.find(
        (item) => item.host === sensor.host || item.sensor_id === sensor.sensorId,
      );
      setAutoDetectStatus(
        matched
          ? `${matched.device_name}: ${matched.note}`
          : `Configuration scan finished for ${sensor.sensorId}.`,
      );
    } catch (configureError) {
      setAutoDetectStatus(
        configureError instanceof Error
          ? configureError.message
          : `Unable to configure sensor ${sensor.sensorId}.`,
      );
    } finally {
      setConfiguringSensorId(null);
    }
  };

  const restartIngestion = async () => {
    setIsRestartingIngestion(true);
    try {
      const response = await restartSensorIngestion();
      await refresh();
      setAutoDetectStatus(response.message);
    } catch (restartError) {
      setAutoDetectStatus(
        restartError instanceof Error
          ? restartError.message
          : 'Unable to restart ingestion.',
      );
    } finally {
      setIsRestartingIngestion(false);
    }
  };

  const removeSensor = async (sensor: SensorRecord) => {
    const confirmed = confirmDestructiveAction(
      `Delete ${sensor.sensorId} from this dashboard? This removes runtime ingestion config and clears its room assignment. Historical events are kept.`,
    );
    if (!confirmed) {
      return;
    }

    setDeletingSensorId(sensor.sensorId);
    try {
      const response = await deleteSensor(sensor.sensorId);
      const nextDeleted = Array.from(new Set([...deletedSensorIds, sensor.sensorId]));
      setDeletedSensorIds(nextDeleted);
      saveDeletedSensorIds(nextDeleted);

      const nextAssignments = { ...assignments };
      delete nextAssignments[sensor.sensorId];
      setAssignments(nextAssignments);
      saveSensorRoomAssignments(nextAssignments);

      const nextContexts = { ...sensorContexts };
      delete nextContexts[sensor.sensorId];
      setSensorContexts(nextContexts);
      saveSensorContexts(nextContexts);

      const nextNames = { ...sensorNames };
      delete nextNames[sensor.sensorId];
      setSensorNames(nextNames);
      saveSensorNames(nextNames);

      setAutoDetectStatus(response.message);
      await refresh();
    } catch (deleteError) {
      setAutoDetectStatus(
        deleteError instanceof Error
          ? deleteError.message
          : `Unable to delete sensor ${sensor.sensorId}.`,
      );
    } finally {
      setDeletingSensorId(null);
    }
  };

  const stats = [
    {
      label: 'Sensors found',
      value: String(sensors.length),
      icon: Database,
    },
    {
      label: 'Sensor types',
      value: String(new Set(sensors.map((sensor) => sensor.sensorType)).size),
      icon: Tags,
    },
    {
      label: 'Room overrides',
      value: String(Object.keys(assignments).length),
      icon: Home,
    },
    {
      label: 'Configured live sensors',
      value: String(health?.fda2_sensors?.length ?? 0),
      icon: Shield,
    },
  ];

  const unconfiguredSensorCount = sensors.filter((sensor) => {
    if (sensor.configuredLive) {
      return false;
    }
    if (!sensor.host) {
      return false;
    }
    return !sensor.sensorType.toLowerCase().includes('heart/respiration');
  }).length;
  const latestLiveAgeSeconds = sensorAgeSeconds(latestLiveTimestamp ?? undefined);
  const hasConfiguredLiveSensors = liveConfiguredSensorIds.size > 0;
  const liveTimelineStale =
    hasConfiguredLiveSensors &&
    (latestLiveAgeSeconds === null ||
      latestLiveAgeSeconds >= onlineAgeSeconds);

  return (
    <SidebarProvider>
      <AdminSidebar />
      <SidebarInset>
        <DashboardHeader
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          onRefresh={() => void refresh()}
          onExport={exportAssignments}
          isRefreshing={isRefreshing}
          searchPlaceholder="Search sensors, types, capabilities..."
        />

        <div className="flex flex-1 flex-col gap-2 bg-[radial-gradient(circle_at_top_left,rgba(37,99,235,0.08),transparent_32rem),linear-gradient(180deg,var(--background),rgba(241,245,249,0.72))] p-2 pt-0 sm:gap-4 sm:p-4 dark:bg-[radial-gradient(circle_at_top_left,rgba(59,130,246,0.18),transparent_30rem),linear-gradient(180deg,var(--background),#09090b)]">
          <div className="min-h-[calc(100vh-4rem)] flex-1 rounded-lg p-3 sm:rounded-xl sm:p-4 md:p-6">
            <div className="mx-auto max-w-6xl space-y-6">
              <section className="rounded-2xl border border-border bg-card/75 p-6 shadow-sm">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="flex flex-col gap-3">
                    <div className="inline-flex items-center gap-2 rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-1 text-xs font-semibold text-blue-700 dark:text-blue-300">
                      <Radio className="h-3.5 w-3.5" />
                      Rooms & Sensors
                    </div>
                    <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
                      Sensor inventory and room assignment
                    </h1>
                    <p className="max-w-3xl text-sm text-muted-foreground sm:text-base">
                      Review detected sensor types, rename room labels, and assign
                      each sensor to a room. These mappings are local to this
                      dashboard host.
                    </p>
                  </div>
                  <div className="w-full max-w-sm space-y-3 rounded-xl border border-border bg-background/70 p-4">
                    <Button
                      type="button"
                      onClick={() => void autoDetectSensors()}
                      disabled={isAutoDetecting || isRestartingIngestion}
                      className="w-full"
                    >
                      {isAutoDetecting ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <ScanSearch className="h-4 w-4" />
                      )}
                      Auto-detect & configure
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => void restartIngestion()}
                      disabled={isRestartingIngestion || isAutoDetecting}
                      className="w-full"
                    >
                      {isRestartingIngestion ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <RotateCcw className="h-4 w-4" />
                      )}
                      Restart live ingestion
                    </Button>
                    <p className="text-xs text-muted-foreground">
                      Scans the local network, identifies fall vs heart/respiration
                      devices, and auto-configures supported sensors for live ingestion.
                    </p>
                    {autoDetectStatus ? (
                      <p className="text-xs font-medium text-blue-700 dark:text-blue-300">
                        {autoDetectStatus}
                      </p>
                    ) : null}
                  </div>
                </div>
              </section>

              {error ? (
                <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{error}</span>
                </div>
              ) : null}

              {liveTimelineStale ? (
                <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-200">
                  <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>
                    No fresh live sensor data detected. Latest live update:{' '}
                    {latestLiveTimestamp ?? 'none yet'}.
                  </span>
                </div>
              ) : null}

              {unconfiguredSensorCount > 0 ? (
                <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-200">
                  <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>
                    {unconfiguredSensorCount} sensor(s) are listed but not configured
                    for backend live ingestion. They will not stream live data until
                    a supported fall sensor profile is discovered.
                  </span>
                </div>
              ) : null}

              <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {stats.map((stat) => {
                  const Icon = stat.icon;
                  return (
                    <article
                      key={stat.label}
                      className="rounded-2xl border border-border bg-card/75 p-4 shadow-sm"
                    >
                      <div className="flex items-start justify-between">
                        <div>
                          <p className="text-sm text-muted-foreground">{stat.label}</p>
                          <p className="mt-1 text-3xl font-bold">{stat.value}</p>
                        </div>
                        <div className="rounded-xl bg-primary/10 p-2 text-primary">
                          <Icon className="h-4 w-4" />
                        </div>
                      </div>
                    </article>
                  );
                })}
              </section>

              {autoDetectedSensors.length > 0 ? (
                <section className="rounded-2xl border border-border bg-card/75 p-5 shadow-sm sm:p-6">
                  <div className="mb-4 flex items-center gap-2">
                    <div className="flex items-center gap-2">
                      <ScanSearch className="h-4 w-4 text-blue-500" />
                      <h2 className="text-lg font-bold">Newly detected sensors</h2>
                    </div>
                  </div>
                  <div className="space-y-2">
                    {autoDetectedSensors.map((sensor) => (
                      <article
                        key={sensor.sensorId}
                        className="flex flex-col gap-2 rounded-lg border border-border bg-background/70 px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
                      >
                        <div>
                          <p className="font-medium">{sensor.sensorId}</p>
                          <p className="text-xs text-muted-foreground">
                            {sensor.sensorType} · Last seen{' '}
                            {sensor.lastSeen ?? 'unknown'}
                          </p>
                        </div>
                        <span
                          className={
                            sensor.configuredLive
                              ? 'rounded-md border border-green-200 bg-green-50 px-2 py-1 text-xs font-semibold text-green-700 dark:border-green-900/50 dark:bg-green-900/20 dark:text-green-300'
                              : 'rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-700 dark:border-amber-900/50 dark:bg-amber-900/20 dark:text-amber-300'
                          }
                        >
                          {sensor.configuredLive ? 'Configured' : 'Detection only'}
                        </span>
                      </article>
                    ))}
                  </div>
                </section>
              ) : null}

              <section className="rounded-2xl border border-border bg-card/75 p-5 shadow-sm sm:p-6">
                <div className="mb-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                  <div className="flex items-center gap-2">
                    <Home className="h-4 w-4 text-blue-500" />
                    <div>
                      <h2 className="text-lg font-bold">Rooms</h2>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Add custom rooms, review detected rooms, and delete rooms you no
                        longer want in the sensor assignment dropdown.
                      </p>
                    </div>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setRoomsExpanded((current) => !current)}
                    aria-expanded={roomsExpanded}
                  >
                    {roomsExpanded ? (
                      <ChevronDown className="h-4 w-4" />
                    ) : (
                      <ChevronRight className="h-4 w-4" />
                    )}
                    {roomsExpanded ? 'Hide rooms' : `Show ${roomRows.length} room${roomRows.length === 1 ? '' : 's'}`}
                  </Button>
                </div>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <input
                    type="text"
                    value={addRoomName}
                    onChange={(event) => setAddRoomName(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        void addRoom();
                      }
                    }}
                    placeholder="e.g. Upstairs Hallway"
                    className="h-10 w-full rounded-lg border border-border bg-card px-3 text-sm"
                  />
                  <Button type="button" variant="outline" onClick={() => void addRoom()}>
                    <Save className="h-4 w-4" />
                    Add room
                  </Button>
                </div>

                {roomFeedback ? (
                  <p className="mt-3 rounded-xl border border-border bg-background px-3 py-2 text-xs font-medium">
                    {roomFeedback}
                  </p>
                ) : null}

                {roomsExpanded && roomRows.length > 0 ? (
                  <div className="mt-4 grid gap-2">
                    {roomRows.map((room) => (
                      <div
                        key={room.room}
                        className="flex flex-col gap-3 rounded-xl border border-border bg-background/70 p-3 sm:flex-row sm:items-center sm:justify-between"
                      >
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="font-semibold">{room.label}</p>
                            {room.sources.map((source) => (
                              <span
                                key={source}
                                className="rounded-full border border-border bg-card px-2 py-0.5 text-[11px] font-semibold text-muted-foreground"
                              >
                                {source}
                              </span>
                            ))}
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {room.assignedSensorCount} assigned sensor{room.assignedSensorCount === 1 ? '' : 's'}
                            {room.detectedSensorCount > 0
                              ? ` · ${room.detectedSensorCount} sensor${room.detectedSensorCount === 1 ? '' : 's'} detected this room`
                              : ''}
                          </p>
                        </div>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => void removeRoom(room.room)}
                          title={`Delete ${room.label}`}
                        >
                          <Trash2 className="h-4 w-4" />
                          Delete
                        </Button>
                      </div>
                    ))}
                  </div>
                ) : null}
              </section>

              <section className="rounded-2xl border border-border bg-card/75 p-5 shadow-sm sm:p-6">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <h2 className="text-xl font-bold">Sensors</h2>
                  <p className="text-sm text-muted-foreground">
                    {filteredSensors.length} visible
                  </p>
                </div>

                <div className="space-y-3">
                  {filteredSensors.map((sensor) => {
                    const assignedRoom = assignments[sensor.sensorId];
                    const selectedRoom = draftValueFor(sensor);
                    const effectiveRoom =
                      assignedRoom ||
                      selectedRoom ||
                      sensor.configuredRoom ||
                      sensor.detectedRooms[0] ||
                      '';
                    const liveTimestampForSensor = latestLiveTimestampBySensor.get(
                      sensor.sensorId,
                    );
                    const sensorConfiguredLive = sensor.configuredLive;
                    const sensorStatusTimestamp = sensorConfiguredLive
                      ? liveTimestampForSensor
                      : sensor.lastSeen;
                    const sensorOnline = isSensorOnline(
                      sensorStatusTimestamp,
                      onlineAgeSeconds,
                    );
                    const statusClass = !sensorConfiguredLive
                      ? 'rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-700 dark:border-amber-900/50 dark:bg-amber-900/20 dark:text-amber-300'
                      : sensorOnline
                        ? 'rounded-md border border-green-200 bg-green-50 px-2 py-1 text-xs font-semibold text-green-700 dark:border-green-900/50 dark:bg-green-900/20 dark:text-green-300'
                        : 'rounded-md border border-red-200 bg-red-50 px-2 py-1 text-xs font-semibold text-red-700 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-300';
                    const statusTitle = !sensorConfiguredLive
                      ? 'Sensor is not configured in backend live ingestion yet'
                      : sensorOnline
                        ? 'Receiving recent sensor events'
                        : 'No recent live sensor events detected';
                    const statusLabel = !sensorConfiguredLive
                      ? 'Not configured'
                      : sensorOnline
                        ? 'Online'
                        : 'Offline';
                    const pendingDetect = ledPending === `${sensor.sensorId}:detect`;
                    const pendingOff = ledPending === `${sensor.sensorId}:off`;
                    const pendingAny = pendingDetect || pendingOff;
                    const configuringThisSensor = configuringSensorId === sensor.sensorId;
                    const selectedColor = colorForSensor(sensor.sensorId);
                    const feedback = ledFeedback[sensor.sensorId];
                    const liveReadings = latestLiveReadingsForSensor(
                      latestLiveEvents,
                      sensor.sensorId,
                    );
                    const deletingThisSensor = deletingSensorId === sensor.sensorId;
                    const dataExpanded = Boolean(expandedSensorData[sensor.sensorId]);
                    const setupExpanded = Boolean(expandedSensorSetup[sensor.sensorId]);
                    const contextExpanded = Boolean(expandedSensorContext[sensor.sensorId]);
                    const controlsExpanded = Boolean(expandedSensorControls[sensor.sensorId]);
                    const contextValue = sensorContexts[sensor.sensorId] ?? '';
                    const sensorName = sensorNames[sensor.sensorId] ?? '';
                    const displayName = sensorName || sensor.sensorId;
                    return (
                      <article
                        key={sensor.sensorId}
                        className="rounded-xl border border-border bg-background/70 p-4"
                      >
                        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                          <div className="space-y-2">
                            <div className="flex flex-wrap items-center gap-2">
                              <div>
                                <p className="font-semibold">{displayName}</p>
                                {sensorName ? (
                                  <p className="text-[11px] text-muted-foreground">
                                    {sensor.sensorId}
                                  </p>
                                ) : null}
                              </div>
                              <button
                                type="button"
                                className={statusClass}
                                title={statusTitle}
                              >
                                {statusLabel}
                              </button>
                              {!sensorConfiguredLive ? (
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="outline"
                                  disabled={configuringThisSensor}
                                  onClick={() => void configureSensor(sensor)}
                                >
                                  {configuringThisSensor ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                  ) : (
                                    <Save className="h-4 w-4" />
                                  )}
                                  Configure
                                </Button>
                              ) : null}
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                disabled={deletingThisSensor}
                                onClick={() => void removeSensor(sensor)}
                                className="border-red-200 text-red-700 hover:bg-red-50 hover:text-red-800 dark:border-red-900/60 dark:text-red-300 dark:hover:bg-red-950/30"
                              >
                                {deletingThisSensor ? (
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                  <Trash2 className="h-4 w-4" />
                                )}
                                Delete
                              </Button>
                            </div>
                            <p className="text-sm text-muted-foreground">
                              {sensor.sensorType}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              Configured room:{' '}
                              <span className="font-medium text-foreground">
                                {formatRoomName(effectiveRoom)}
                              </span>
                            </p>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              onClick={() => toggleSensorData(sensor.sensorId)}
                              className="w-fit"
                              aria-expanded={dataExpanded}
                            >
                              {dataExpanded ? (
                                <ChevronDown className="h-4 w-4" />
                              ) : (
                                <ChevronRight className="h-4 w-4" />
                              )}
                              {dataExpanded ? 'Hide sensor data' : 'Show sensor data'}
                            </Button>
                            {dataExpanded ? (
                              <div className="space-y-2">
                                <div className="flex flex-wrap gap-2">
                                  {sensor.capabilities.length > 0 ? (
                                    sensor.capabilities.map((capability) => (
                                      <span
                                        key={capability}
                                        className="rounded-full border border-border bg-card px-2 py-1 text-xs font-medium"
                                      >
                                        {capability}
                                      </span>
                                    ))
                                  ) : (
                                    <span className="rounded-full border border-border bg-card px-2 py-1 text-xs text-muted-foreground">
                                      No capability data yet
                                    </span>
                                  )}
                                </div>
                                <p className="text-xs text-muted-foreground">
                                  Sources: {sensor.sources.map(prettySource).join(', ')}
                                </p>
                                <p className="text-xs text-muted-foreground">
                                  Last live update: {liveTimestampForSensor ?? 'none yet'}
                                </p>
                                {sensor.host ? (
                                  <p className="text-xs text-muted-foreground">
                                    Host: {sensor.host}
                                  </p>
                                ) : null}
                                {liveReadings.length > 0 ? (
                                  <div className="grid max-w-xl grid-cols-1 gap-2 pt-1 sm:grid-cols-2">
                                    {liveReadings.map((reading) => {
                                      const readingFresh =
                                        reading.ageSeconds !== null &&
                                        reading.ageSeconds < onlineAgeSeconds;
                                      return (
                                        <div
                                          key={reading.eventType}
                                          className="rounded-lg border border-border bg-card p-3"
                                        >
                                          <div className="flex items-center justify-between gap-2">
                                            <div className="flex min-w-0 items-center gap-2 text-xs font-medium text-muted-foreground">
                                              <span
                                                className={
                                                  readingFresh
                                                    ? 'text-green-600 dark:text-green-300'
                                                    : 'text-amber-600 dark:text-amber-300'
                                                }
                                              >
                                                <LiveReadingIcon
                                                  eventType={reading.eventType}
                                                />
                                              </span>
                                              <span className="truncate">
                                                {reading.label}
                                              </span>
                                            </div>
                                            <span
                                              className={
                                                readingFresh
                                                  ? 'rounded-full bg-green-500/10 px-2 py-0.5 text-[11px] font-semibold text-green-700 dark:text-green-300'
                                                  : 'rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:text-amber-300'
                                              }
                                            >
                                              {readingFresh ? 'Live' : 'Stale'}
                                            </span>
                                          </div>
                                          <p className="mt-2 text-2xl font-bold tracking-tight">
                                            {formatLiveReadingValue(reading)}
                                            {reading.unit ? (
                                              <span className="ml-1 text-sm font-medium text-muted-foreground">
                                                {reading.unit}
                                              </span>
                                            ) : null}
                                          </p>
                                          <p className="mt-1 text-[11px] text-muted-foreground">
                                            {reading.ageSeconds === null
                                              ? reading.timestamp
                                              : `${reading.ageSeconds}s ago`}
                                          </p>
                                        </div>
                                      );
                                    })}
                                  </div>
                                ) : sensorConfiguredLive ? (
                                  <div className="max-w-xl rounded-lg border border-dashed border-border bg-card/70 p-3 text-xs text-muted-foreground">
                                    Waiting for live telemetry values from this sensor.
                                  </div>
                                ) : null}
                              </div>
                            ) : null}
                            {!sensorConfiguredLive ? (
                              <p className="text-xs text-amber-700 dark:text-amber-300">
                                Live setup pending for this sensor.
                              </p>
                            ) : null}
                          </div>

                          <div className="w-full max-w-md space-y-3">
                            <div className="rounded-lg border border-border bg-card p-3">
                              <button
                                type="button"
                                onClick={() => toggleSensorSetup(sensor.sensorId)}
                                className="flex w-full items-center justify-between gap-3 text-left"
                                aria-expanded={setupExpanded}
                              >
                                <span>
                                  <span className="block text-sm font-semibold">
                                    Sensor setup
                                  </span>
                                  <span className="text-xs text-muted-foreground">
                                    Name and configured room
                                  </span>
                                </span>
                                {setupExpanded ? (
                                  <ChevronDown className="h-4 w-4" />
                                ) : (
                                  <ChevronRight className="h-4 w-4" />
                                )}
                              </button>
                              {setupExpanded ? (
                                <div className="mt-3 space-y-3">
                                  <div>
                                    <label
                                      htmlFor={`sensor-name-${sensor.sensorId}`}
                                      className="text-xs font-medium text-muted-foreground"
                                    >
                                      Sensor name
                                    </label>
                                    <input
                                      id={`sensor-name-${sensor.sensorId}`}
                                      type="text"
                                      value={sensorName}
                                      onChange={(event) =>
                                        updateSensorName(
                                          sensor.sensorId,
                                          event.target.value,
                                        )
                                      }
                                      placeholder="e.g. Bedroom bedside sensor"
                                      className="mt-2 h-10 w-full rounded-lg border border-border bg-background px-3 text-sm"
                                    />
                                  </div>
                                  <div>
                                    <p className="text-xs text-muted-foreground">
                                      Configured room
                                    </p>
                                    <p className="mt-1 text-sm font-medium">
                                      {formatRoomName(effectiveRoom)}
                                    </p>
                                  </div>
                                  <div className="flex flex-col gap-2 sm:flex-row">
                                    <select
                                      className="h-10 w-full rounded-lg border border-border bg-background px-3 text-sm"
                                      value={draftValueFor(sensor)}
                                      onChange={(event) => {
                                        const roomValue = event.target.value;
                                        setDraftRooms((current) => ({
                                          ...current,
                                          [sensor.sensorId]: roomValue,
                                        }));
                                        void saveRoomValue(sensor.sensorId, roomValue);
                                      }}
                                    >
                                      <option value="">Unassigned</option>
                                      {roomOptions.map((room) => (
                                        <option key={room} value={room}>
                                          {formatRoomName(room)}
                                        </option>
                                      ))}
                                    </select>
                                    <Button
                                      type="button"
                                      variant="outline"
                                      onClick={() => saveRoom(sensor)}
                                    >
                                      <Save className="h-4 w-4" />
                                      Save
                                    </Button>
                                  </div>
                                </div>
                              ) : null}
                            </div>

                            <div className="rounded-lg border border-border bg-card p-3">
                              <button
                                type="button"
                                onClick={() => toggleSensorContext(sensor.sensorId)}
                                className="flex w-full items-center justify-between gap-3 text-left"
                                aria-expanded={contextExpanded}
                              >
                                <span>
                                  <span className="block text-sm font-semibold">
                                    Context for Gemma
                                  </span>
                                  <span className="text-xs text-muted-foreground">
                                    Resident and location notes
                                  </span>
                                </span>
                                {contextExpanded ? (
                                  <ChevronDown className="h-4 w-4" />
                                ) : (
                                  <ChevronRight className="h-4 w-4" />
                                )}
                              </button>
                              {contextExpanded ? (
                                <div className="mt-3">
                                  <textarea
                                    id={`sensor-context-${sensor.sensorId}`}
                                    value={contextValue}
                                    onChange={(event) =>
                                      updateSensorContext(
                                        sensor.sensorId,
                                        event.target.value,
                                      )
                                    }
                                    placeholder="e.g. Bedroom sensor above bed; resident uses walker; doorway is near bathroom."
                                    className="min-h-24 w-full resize-y rounded-lg border border-border bg-background px-3 py-2 text-sm"
                                  />
                                  <p className="mt-2 text-[11px] text-muted-foreground">
                                    Saved with this sensor and included in
                                    caregiver/Gemma context.
                                  </p>
                                </div>
                              ) : null}
                            </div>

                            <div className="rounded-lg border border-border bg-card p-3">
                              <button
                                type="button"
                                onClick={() => toggleSensorControls(sensor.sensorId)}
                                className="flex w-full items-center justify-between gap-3 text-left"
                                aria-expanded={controlsExpanded}
                              >
                                <span>
                                  <span className="block text-sm font-semibold">
                                    Sensor detection RGB
                                  </span>
                                  <span className="text-xs text-muted-foreground">
                                    Flash this sensor to identify it
                                  </span>
                                </span>
                                {controlsExpanded ? (
                                  <ChevronDown className="h-4 w-4" />
                                ) : (
                                  <ChevronRight className="h-4 w-4" />
                                )}
                              </button>
                              {controlsExpanded ? (
                                <div className="mt-3">
                                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                                    <label className="flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5">
                                      <input
                                        aria-label={`${sensor.sensorId} RGB color`}
                                        className="h-8 w-10 cursor-pointer rounded border border-border bg-transparent"
                                        type="color"
                                        value={selectedColor}
                                        disabled={pendingAny}
                                        onChange={(event) =>
                                          updateLedColor(
                                            sensor.sensorId,
                                            event.target.value,
                                          )
                                        }
                                      />
                                      <span className="text-xs font-medium">
                                        {selectedColor}
                                      </span>
                                    </label>
                                    <div className="flex flex-wrap gap-2">
                                      <Button
                                        type="button"
                                        size="sm"
                                        variant="outline"
                                        disabled={!sensorConfiguredLive || pendingAny}
                                        onClick={() =>
                                          void runLedCommand(
                                            sensor.sensorId,
                                            'detect',
                                            sensorConfiguredLive,
                                          )
                                        }
                                      >
                                        {pendingDetect ? (
                                          <Loader2 className="h-4 w-4 animate-spin" />
                                        ) : (
                                          <Palette className="h-4 w-4" />
                                        )}
                                        Detect
                                      </Button>
                                      <Button
                                        type="button"
                                        size="sm"
                                        variant="outline"
                                        disabled={!sensorConfiguredLive || pendingAny}
                                        onClick={() =>
                                          void runLedCommand(
                                            sensor.sensorId,
                                            'off',
                                            sensorConfiguredLive,
                                          )
                                        }
                                      >
                                        Off
                                      </Button>
                                    </div>
                                  </div>
                                  <p className="mt-2 text-[11px] text-muted-foreground">
                                    {sensor.rgbLightConfigured
                                      ? 'RGB key configured.'
                                      : 'RGB key auto-discovered on first detect.'}
                                  </p>
                                  {feedback ? (
                                    <p
                                      className={`mt-2 text-xs ${
                                        feedback.tone === 'success'
                                          ? 'text-green-700 dark:text-green-300'
                                          : 'text-red-700 dark:text-red-300'
                                      }`}
                                    >
                                      {feedback.message}
                                    </p>
                                  ) : null}
                                </div>
                              ) : null}
                            </div>

                            {savedSensor === sensor.sensorId ? (
                              <p className="flex items-center gap-1 text-xs text-green-600 dark:text-green-300">
                                <CheckCircle2 className="h-3.5 w-3.5" />
                                Room assignment saved.
                              </p>
                            ) : null}
                          </div>
                        </div>
                      </article>
                    );
                  })}
                  {filteredSensors.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
                      No sensors match this filter.
                    </div>
                  ) : null}
                </div>
              </section>
            </div>
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}

export default SensorsDashboard;
