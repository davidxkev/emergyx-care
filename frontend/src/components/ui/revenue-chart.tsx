'use client';

import { memo, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Activity,
  Home,
  Lightbulb,
  ShieldAlert,
  Wifi,
  WifiOff,
} from 'lucide-react';

import { loadRoomDisplayNames } from '@/lib/room-names';
import type { EventRead, ModeSnapshot } from '@/lib/types';

interface RevenueChartProps {
  events: EventRead[];
  snapshot: ModeSnapshot | null;
}

type Bucket = {
  index: number;
  startMs: number;
  endMs: number;
  label: string;
  eventCount: number;
  presenceCount: number;
  fallCount: number;
  lightCount: number;
  lightSum: number;
};

type SensorLane = {
  sensorId: string;
  room: string;
  lastTimestampMs: number;
  ageLabel: string;
  active: boolean;
  cells: Array<'empty' | 'activity' | 'fall'>;
};

const WINDOW_MINUTES = 30;
const BUCKET_COUNT = 12;
const SENSOR_ACTIVE_SECONDS = 45;
const WIDTH = 760;
const CHART_TOP = 82;
const CHART_HEIGHT = 150;
const SENSOR_LANE_TOP = 286;
const LEFT_PAD = 84;
const RIGHT_PAD = 24;
const PLOT_WIDTH = WIDTH - LEFT_PAD - RIGHT_PAD;
const BUCKET_GAP = 6;

function parseTimestampMs(timestamp?: string | null) {
  if (!timestamp) {
    return null;
  }
  const parsed = Date.parse(timestamp);
  return Number.isNaN(parsed) ? null : parsed;
}

function parseNumber(value: string) {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatBucketTime(ms: number) {
  return new Date(ms).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatRoomName(room?: string | null) {
  if (!room) {
    return 'Unassigned';
  }
  const displayNames = loadRoomDisplayNames();
  if (displayNames[room]) {
    return displayNames[room];
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

function shortSensorId(sensorId: string) {
  if (sensorId.length <= 20) {
    return sensorId;
  }
  return `${sensorId.slice(0, 10)}...${sensorId.slice(-6)}`;
}

function ageFromAnchor(anchorMs: number, timestampMs: number) {
  const seconds = Math.max(0, Math.floor((anchorMs - timestampMs) / 1000));
  if (seconds < 60) {
    return 'just now';
  }
  if (seconds < 3600) {
    return `${Math.floor(seconds / 60)}m`;
  }
  if (seconds < 86400) {
    return `${Math.floor(seconds / 3600)}h`;
  }
  return `${Math.floor(seconds / 86400)}d`;
}

function findAnchorMs(events: EventRead[], snapshot: ModeSnapshot | null) {
  const snapshotMs = parseTimestampMs(snapshot?.last_event_timestamp);
  let latest: number | null = null;
  if (snapshotMs !== null) {
    latest = snapshotMs;
  }
  for (const event of events) {
    const ms = parseTimestampMs(event.timestamp);
    if (ms !== null && (latest === null || ms > latest)) {
      latest = ms;
    }
  }
  if (latest === null) {
    return null;
  }

  const nowMs = Date.now();
  return latest > nowMs + 5 * 60 * 1000 ? latest : nowMs;
}

function eventBucketIndex(timestampMs: number, startMs: number, bucketMs: number) {
  return Math.max(
    0,
    Math.min(BUCKET_COUNT - 1, Math.floor((timestampMs - startMs) / bucketMs)),
  );
}

function buildCareGraph(events: EventRead[], snapshot: ModeSnapshot | null) {
  const anchorMs = findAnchorMs(events, snapshot);
  if (anchorMs === null) {
    return null;
  }

  const windowMs = WINDOW_MINUTES * 60 * 1000;
  const bucketMs = windowMs / BUCKET_COUNT;
  const startMs = anchorMs - windowMs;
  const buckets: Bucket[] = Array.from({ length: BUCKET_COUNT }, (_, index) => {
    const bucketStart = startMs + index * bucketMs;
    return {
      index,
      startMs: bucketStart,
      endMs: bucketStart + bucketMs,
      label: formatBucketTime(bucketStart),
      eventCount: 0,
      presenceCount: 0,
      fallCount: 0,
      lightCount: 0,
      lightSum: 0,
    };
  });

  const latestBySensor = new Map<string, { timestampMs: number; room: string }>();
  const sensorCells = new Map<string, Array<'empty' | 'activity' | 'fall'>>();

  for (const event of events) {
    const timestampMs = parseTimestampMs(event.timestamp);
    if (timestampMs === null) {
      continue;
    }

    const current = latestBySensor.get(event.sensor_id);
    if (!current || timestampMs > current.timestampMs) {
      latestBySensor.set(event.sensor_id, {
        timestampMs,
        room: event.room,
      });
    }

    if (timestampMs < startMs || timestampMs > anchorMs) {
      continue;
    }

    const bucketIndex = eventBucketIndex(timestampMs, startMs, bucketMs);
    const bucket = buckets[bucketIndex];
    bucket.eventCount += 1;

    if (!sensorCells.has(event.sensor_id)) {
      sensorCells.set(event.sensor_id, new Array(BUCKET_COUNT).fill('empty'));
    }
    const cells = sensorCells.get(event.sensor_id);
    if (cells) {
      cells[bucketIndex] =
        event.event_type === 'fall_detected' && event.value === 'true'
          ? 'fall'
          : cells[bucketIndex] === 'fall'
            ? 'fall'
            : 'activity';
    }

    if (event.event_type === 'person_present' && event.value === 'true') {
      bucket.presenceCount += 1;
    } else if (event.event_type === 'fall_detected' && event.value === 'true') {
      bucket.fallCount += 1;
    } else if (event.event_type === 'illuminance') {
      const lux = parseNumber(event.value);
      bucket.lightCount += 1;
      if (lux !== null) {
        bucket.lightSum += lux;
      }
    }
  }

  const lanes: SensorLane[] = Array.from(latestBySensor.entries())
    .map(([sensorId, item]) => ({
      sensorId,
      room: item.room,
      lastTimestampMs: item.timestampMs,
      ageLabel: ageFromAnchor(anchorMs, item.timestampMs),
      active: anchorMs - item.timestampMs <= SENSOR_ACTIVE_SECONDS * 1000,
      cells: sensorCells.get(sensorId) ?? new Array(BUCKET_COUNT).fill('empty'),
    }))
    .sort((a, b) => Number(b.active) - Number(a.active) || b.lastTimestampMs - a.lastTimestampMs);

  const totalFalls = buckets.reduce((sum, bucket) => sum + bucket.fallCount, 0);
  const activeSensorCount = lanes.filter((lane) => lane.active).length;
  const activeRooms = Array.from(
    new Set(lanes.filter((lane) => lane.active).map((lane) => lane.room)),
  );
  const lightSamples = buckets.reduce((sum, bucket) => sum + bucket.lightCount, 0);
  const latestBucket = buckets[buckets.length - 1];

  return {
    anchorMs,
    buckets,
    lanes,
    totalFalls,
    activeSensorCount,
    activeRooms,
    lightSamples,
    latestBucket,
  };
}

function bucketScore(bucket: Bucket) {
  return (
    Math.min(bucket.lightCount, 8) +
    Math.min(bucket.presenceCount * 3, 12) +
    Math.min(bucket.fallCount * 8, 16)
  );
}

function lightAverage(bucket: Bucket) {
  if (bucket.lightCount === 0) {
    return null;
  }
  return bucket.lightSum / bucket.lightCount;
}

function lightCategory(lux: number | null) {
  if (lux === null) {
    return 'No light data';
  }
  if (lux < 10) {
    return 'Dark';
  }
  if (lux < 50) {
    return 'Dim';
  }
  if (lux < 200) {
    return 'Low indoor';
  }
  if (lux < 500) {
    return 'Normal indoor';
  }
  return 'Bright';
}

export const RevenueChart = memo(({ events, snapshot }: RevenueChartProps) => {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const graph = useMemo(() => buildCareGraph(events, snapshot), [events, snapshot]);

  if (!graph) {
    return (
      <div className="border-border bg-card/75 rounded-2xl border p-6 shadow-sm">
        <h3 className="text-lg font-semibold sm:text-xl">Live Care Graph</h3>
        <div className="text-muted-foreground mt-4 rounded-lg border border-dashed px-4 py-8 text-sm">
          No live sensor rows yet.
        </div>
      </div>
    );
  }

  const bucketWidth = PLOT_WIDTH / BUCKET_COUNT;
  const maxScore = Math.max(...graph.buckets.map(bucketScore), 1);
  const maxLux = Math.max(
    ...graph.buckets
      .map(lightAverage)
      .filter((value): value is number => value !== null),
    1,
  );
  const laneHeight = 30;
  const svgHeight = SENSOR_LANE_TOP + Math.max(graph.lanes.length, 1) * laneHeight + 28;
  const activeHover = hoveredIndex === null ? null : graph.buckets[hoveredIndex];
  const hoverTooltipLeft =
    hoveredIndex === null
      ? 0
      : `${((LEFT_PAD + hoveredIndex * bucketWidth + bucketWidth / 2) / WIDTH) * 100}%`;
  const latestLightAverage = lightAverage(graph.latestBucket);
  const latestLightText =
    latestLightAverage === null
      ? snapshot?.light?.lux != null
        ? `${snapshot.light.lux.toFixed(1)} lux`
        : 'No light'
      : `${latestLightAverage.toFixed(1)} lux`;

  return (
    <div className="border-border bg-card/75 w-full overflow-hidden rounded-2xl border shadow-sm">
      <div className="flex flex-col justify-between gap-4 px-6 pt-6 pb-4 sm:flex-row sm:items-start">
        <div>
          <h3 className="text-lg font-semibold sm:text-xl">Live Care Graph</h3>
          <p className="text-muted-foreground mt-1 text-sm">
            Last {WINDOW_MINUTES} minutes by event type and sensor stream
          </p>
        </div>
        <div className="grid grid-cols-3 gap-2 text-right text-xs sm:min-w-[24rem]">
          <div className="rounded-lg border border-border bg-background/70 px-3 py-2">
            <p className="text-muted-foreground">Active sensors</p>
            <p className="text-foreground text-lg font-semibold">
              {graph.activeSensorCount}/{graph.lanes.length}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-background/70 px-3 py-2">
            <p className="text-muted-foreground">Live rooms</p>
            <p className="text-foreground text-lg font-semibold">
              {graph.activeRooms.length}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-background/70 px-3 py-2">
            <p className="text-muted-foreground">Likely falls</p>
            <p className="text-foreground text-lg font-semibold">{graph.totalFalls}</p>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-3 px-6 pb-3 text-xs">
        <span className="inline-flex items-center gap-2 text-muted-foreground">
          <span className="h-2.5 w-2.5 rounded-sm bg-blue-500" />
          Presence
        </span>
        <span className="inline-flex items-center gap-2 text-muted-foreground">
          <span className="h-2.5 w-2.5 rounded-sm bg-amber-500" />
          Light stream
        </span>
        <span className="inline-flex items-center gap-2 text-muted-foreground">
          <span className="h-2.5 w-2.5 rounded-sm bg-red-500" />
          Likely fall
        </span>
        <span className="inline-flex items-center gap-2 text-muted-foreground">
          <span className="h-2.5 w-2.5 rounded-full border border-emerald-500 bg-emerald-500/20" />
          Sensor activity
        </span>
      </div>

      <div className="px-4 pb-4">
        <div className="relative">
          <svg
            viewBox={`0 0 ${WIDTH} ${svgHeight}`}
            className="h-auto w-full overflow-visible"
            role="img"
            aria-label="Live care graph showing recent presence, light, fall, and sensor stream activity"
            onMouseLeave={() => setHoveredIndex(null)}
          >
            <text x="0" y="38" className="fill-muted-foreground text-[12px]">
              Events
            </text>
            <text x="0" y={SENSOR_LANE_TOP - 16} className="fill-muted-foreground text-[12px]">
              Sensors
            </text>

            {[0, 1, 2, 3].map((line) => {
              const y = CHART_TOP + line * (CHART_HEIGHT / 3);
              return (
                <line
                  key={line}
                  x1={LEFT_PAD}
                  x2={WIDTH - RIGHT_PAD}
                  y1={y}
                  y2={y}
                  stroke="currentColor"
                  className="text-border"
                  strokeDasharray="4 8"
                />
              );
            })}

            {graph.buckets.map((bucket) => {
              const x = LEFT_PAD + bucket.index * bucketWidth + BUCKET_GAP / 2;
              const width = bucketWidth - BUCKET_GAP;
              const score = bucketScore(bucket);
              const totalHeight = (score / maxScore) * (CHART_HEIGHT - 20);
              const lightHeight =
                score > 0 ? (Math.min(bucket.lightCount, 8) / score) * totalHeight : 0;
              const presenceHeight =
                score > 0
                  ? (Math.min(bucket.presenceCount * 3, 12) / score) * totalHeight
                  : 0;
              const fallHeight =
                score > 0 ? (Math.min(bucket.fallCount * 8, 16) / score) * totalHeight : 0;
              let yCursor = CHART_TOP + CHART_HEIGHT;
              const selected = hoveredIndex === bucket.index;

              return (
                <g
                  key={bucket.index}
                  onMouseEnter={() => setHoveredIndex(bucket.index)}
                  onFocus={() => setHoveredIndex(bucket.index)}
                >
                  <rect
                    x={x}
                    y={CHART_TOP}
                    width={width}
                    height={CHART_HEIGHT}
                    rx="7"
                    className={selected ? 'fill-slate-500/10' : 'fill-transparent'}
                  />
                  <rect
                    x={x}
                    y={CHART_TOP + CHART_HEIGHT - 1}
                    width={width}
                    height="1"
                    className="fill-border"
                  />
                  {lightHeight > 0 ? (
                    <motion.rect
                      initial={{ height: 0, y: CHART_TOP + CHART_HEIGHT }}
                      animate={{ height: lightHeight, y: yCursor - lightHeight }}
                      transition={{ duration: 0.35, delay: bucket.index * 0.015 }}
                      x={x}
                      width={width}
                      rx="4"
                      className="fill-amber-500/80"
                    />
                  ) : null}
                  {(() => {
                    yCursor -= lightHeight;
                    return null;
                  })()}
                  {presenceHeight > 0 ? (
                    <motion.rect
                      initial={{ height: 0, y: CHART_TOP + CHART_HEIGHT }}
                      animate={{ height: presenceHeight, y: yCursor - presenceHeight }}
                      transition={{ duration: 0.35, delay: bucket.index * 0.015 + 0.03 }}
                      x={x}
                      width={width}
                      rx="4"
                      className="fill-blue-500/85"
                    />
                  ) : null}
                  {(() => {
                    yCursor -= presenceHeight;
                    return null;
                  })()}
                  {fallHeight > 0 ? (
                    <motion.rect
                      initial={{ height: 0, y: CHART_TOP + CHART_HEIGHT }}
                      animate={{ height: fallHeight, y: yCursor - fallHeight }}
                      transition={{ duration: 0.35, delay: bucket.index * 0.015 + 0.06 }}
                      x={x}
                      width={width}
                      rx="4"
                      className="fill-red-500"
                    />
                  ) : null}
                  <text
                    x={x + width / 2}
                    y={CHART_TOP + CHART_HEIGHT + 22}
                    textAnchor="middle"
                    className={
                      selected
                        ? 'fill-foreground text-[11px] font-semibold'
                        : 'fill-muted-foreground text-[11px]'
                    }
                  >
                    {bucket.index % 2 === 0 ? bucket.label : ''}
                  </text>
                </g>
              );
            })}

            <polyline
              points={graph.buckets
                .map((bucket) => {
                  const avg = lightAverage(bucket);
                  if (avg === null) {
                    return null;
                  }
                  const x = LEFT_PAD + bucket.index * bucketWidth + bucketWidth / 2;
                  const y =
                    CHART_TOP +
                    CHART_HEIGHT -
                    Math.max(6, Math.min(CHART_HEIGHT - 6, (avg / maxLux) * (CHART_HEIGHT - 18)));
                  return `${x},${y}`;
                })
                .filter(Boolean)
                .join(' ')}
              fill="none"
              stroke="rgb(245 158 11)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity="0.85"
            />

            {graph.lanes.map((lane, laneIndex) => {
              const y = SENSOR_LANE_TOP + laneIndex * laneHeight;
              const StatusIcon = lane.active ? Wifi : WifiOff;
              return (
                <g key={lane.sensorId}>
                  <text x="0" y={y + 15} className="fill-foreground text-[11px] font-medium">
                    {shortSensorId(lane.sensorId)}
                  </text>
                  <text x="0" y={y + 27} className="fill-muted-foreground text-[10px]">
                    {formatRoomName(lane.room)}
                  </text>
                  <StatusIcon
                    x={LEFT_PAD - 22}
                    y={y + 4}
                    width="14"
                    height="14"
                    className={lane.active ? 'text-emerald-500' : 'text-red-500'}
                  />
                  {lane.cells.map((cell, index) => {
                    const x = LEFT_PAD + index * bucketWidth + BUCKET_GAP / 2;
                    const width = bucketWidth - BUCKET_GAP;
                    return (
                      <rect
                        key={`${lane.sensorId}-${index}`}
                        x={x}
                        y={y}
                        width={width}
                        height="18"
                        rx="5"
                        className={
                          cell === 'fall'
                            ? 'fill-red-500'
                            : cell === 'activity'
                              ? 'fill-emerald-500/65'
                              : 'fill-muted'
                        }
                      />
                    );
                  })}
                  <text
                    x={WIDTH - RIGHT_PAD}
                    y={y + 14}
                    textAnchor="end"
                    className={lane.active ? 'fill-emerald-600 text-[11px]' : 'fill-red-500 text-[11px]'}
                  >
                    {lane.active ? 'active' : `${lane.ageLabel} quiet`}
                  </text>
                </g>
              );
            })}
          </svg>

          {activeHover ? (
            <motion.div
              key={activeHover.index}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.12 }}
              className="pointer-events-none absolute top-3 z-10 min-w-52 -translate-x-1/2 rounded-lg border border-border bg-background/95 px-3 py-2 text-xs shadow-sm backdrop-blur"
              style={{ left: hoverTooltipLeft }}
            >
              <div className="font-semibold text-foreground">{activeHover.label}</div>
              <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
                <span className="text-muted-foreground">Events</span>
                <span className="text-right font-medium">{activeHover.eventCount}</span>
                <span className="text-muted-foreground">Presence</span>
                <span className="text-right font-medium">{activeHover.presenceCount}</span>
                <span className="text-muted-foreground">Light</span>
                <span className="text-right font-medium">
                  {lightCategory(lightAverage(activeHover))}
                </span>
                <span className="text-muted-foreground">Likely falls</span>
                <span className="text-right font-medium">{activeHover.fallCount}</span>
              </div>
            </motion.div>
          ) : null}
        </div>
      </div>

      <div className="grid grid-cols-1 divide-y border-t border-border sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <div className="flex items-center gap-3 px-6 py-4">
          <div className="rounded-lg bg-blue-500/10 p-2 text-blue-500">
            <Home className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="text-muted-foreground text-xs">Current presence</p>
            <p className="truncate text-sm font-semibold">
              {snapshot?.latest_person?.value === 'true'
                ? `Detected in ${formatRoomName(snapshot.latest_person.room)}`
                : 'Not detected'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 px-6 py-4">
          <div className="rounded-lg bg-amber-500/10 p-2 text-amber-500">
            <Lightbulb className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="text-muted-foreground text-xs">Latest light</p>
            <p className="truncate text-sm font-semibold">{latestLightText}</p>
          </div>
        </div>
        <div className="flex items-center gap-3 px-6 py-4">
          <div className="rounded-lg bg-red-500/10 p-2 text-red-500">
            <ShieldAlert className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="text-muted-foreground text-xs">Urgent signal</p>
            <p className="truncate text-sm font-semibold">
              {graph.totalFalls > 0 ? `${graph.totalFalls} likely fall event(s)` : 'No likely fall in window'}
            </p>
          </div>
        </div>
      </div>

      <div className="border-t border-border px-6 py-3">
        <div className="text-muted-foreground flex items-center gap-2 text-xs">
          <Activity className="h-3.5 w-3.5" />
          <span>
            {graph.lightSamples} light samples in this window. Latest live row{' '}
            {snapshot?.last_event_age_human ?? 'unknown'}.
          </span>
        </div>
      </div>
    </div>
  );
});

RevenueChart.displayName = 'RevenueChart';
