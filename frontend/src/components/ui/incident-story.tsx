'use client';

import { memo } from 'react';
import { motion } from 'framer-motion';
import {
  BellRing,
  Brain,
  CheckCircle2,
  Clock3,
  Radio,
  ShieldAlert,
  UserRound,
  type LucideIcon,
} from 'lucide-react';

import { eventLabel, formatTime, formatTimestamp } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { EventRead, IncidentContext, ModeSnapshot } from '@/lib/types';

interface IncidentStoryProps {
  snapshot: ModeSnapshot | null;
  events: EventRead[];
}

type StoryStep = {
  label: string;
  title: string;
  detail: string;
  icon: LucideIcon;
  tone: 'neutral' | 'blue' | 'red' | 'green' | 'amber';
};

function toneClasses(tone: StoryStep['tone']) {
  return {
    neutral: 'border-slate-300/70 bg-slate-500/10 text-slate-600 dark:border-slate-700 dark:text-slate-300',
    blue: 'border-blue-300/70 bg-blue-500/10 text-blue-600 dark:border-blue-900/70 dark:text-blue-300',
    red: 'border-red-300/70 bg-red-500/10 text-red-600 dark:border-red-900/70 dark:text-red-300',
    green: 'border-green-300/70 bg-green-500/10 text-green-600 dark:border-green-900/70 dark:text-green-300',
    amber: 'border-amber-300/70 bg-amber-500/10 text-amber-600 dark:border-amber-900/70 dark:text-amber-300',
  }[tone];
}

function sensorCount(events: EventRead[], snapshot: ModeSnapshot | null) {
  const sensors = new Set<string>();
  for (const event of events) {
    sensors.add(event.sensor_id);
  }
  if (snapshot?.latest_person?.sensor_id) {
    sensors.add(snapshot.latest_person.sensor_id);
  }
  if (snapshot?.latest_fall?.sensor_id) {
    sensors.add(snapshot.latest_fall.sensor_id);
  }
  if (snapshot?.light?.sensor_id) {
    sensors.add(snapshot.light.sensor_id);
  }
  return sensors.size;
}

function incidentHeadline(incident: IncidentContext) {
  const eventTime = formatTime(incident.event?.timestamp);
  const room = incident.room ?? 'the room';
  return `Likely fall in ${room} at ${eventTime}`;
}

function storySteps(incident: IncidentContext): StoryStep[] {
  const before = incident.person_before ?? incident.before_person;
  const clear = incident.fall_clear_after ?? incident.after_fall_clear;
  const room = incident.room ?? 'the room';
  const light = incident.light_context;

  return [
    {
      label: 'Before',
      title: before?.timestamp ? 'Presence seen first' : 'No prior presence row',
      detail: before?.timestamp
        ? `Person signal was ${before.value === 'true' ? 'detected' : 'not detected'} at ${formatTime(before.timestamp)}.`
        : 'No earlier person-presence event was found for this same sensor.',
      icon: UserRound,
      tone: 'blue',
    },
    {
      label: 'Event',
      title: 'Likely fall detected',
      detail: `${room} · ${formatTimestamp(incident.event?.timestamp)} · ${incident.sensor_id ?? 'live sensor'}`,
      icon: ShieldAlert,
      tone: 'red',
    },
    {
      label: 'Alert',
      title: incident.alert?.sent_success ? 'Telegram alert sent' : 'Alert logged locally',
      detail: incident.alert?.timestamp
        ? `${incident.alert.sent_channel ?? 'local log'} at ${formatTime(incident.alert.timestamp)}.`
        : 'No linked alert record yet.',
      icon: BellRing,
      tone: incident.alert?.sent_success ? 'green' : 'amber',
    },
    {
      label: 'Context',
      title: light?.category ? light.category.replace(/_/g, ' ') : 'No light reading',
      detail:
        light && typeof light.lux === 'number'
          ? `${light.lux.toFixed(1)} lux from the same sensor room. Context only, not a cause.`
          : 'Light context will appear here when the sensor reports illuminance.',
      icon: Radio,
      tone: 'neutral',
    },
    {
      label: 'After',
      title: clear?.timestamp ? 'Fall state cleared' : 'Caregiver check needed',
      detail: clear?.timestamp
        ? `Cleared at ${formatTime(clear.timestamp)}${incident.duration_seconds != null ? ` after ~${incident.duration_seconds}s` : ''}.`
        : 'Check on the person directly. Emergyx Care is not a medical device.',
      icon: clear?.timestamp ? CheckCircle2 : Clock3,
      tone: clear?.timestamp ? 'green' : 'amber',
    },
  ];
}

export const IncidentStory = memo(({ snapshot, events }: IncidentStoryProps) => {
  const incident = snapshot?.latest_incident ?? null;
  const latestEvent = events[0] ?? null;
  const count = sensorCount(events, snapshot);

  if (!incident) {
    return (
      <motion.section
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative overflow-hidden rounded-2xl border border-border bg-card/75 p-5 shadow-sm sm:p-6"
      >
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(34,197,94,0.16),transparent_28rem)]" />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="max-w-2xl">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-green-500/30 bg-green-500/10 px-3 py-1 text-xs font-semibold text-green-600 dark:text-green-300">
              <Radio className="h-3.5 w-3.5" />
              Live monitoring
            </div>
            <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
              Ready to build the next incident story.
            </h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground sm:text-base">
              When a sensor reports a likely fall, this card will show the full chain:
              prior presence, event, Telegram alert, context, and next caregiver step.
            </p>
          </div>

          <div className="grid min-w-[260px] gap-3 rounded-2xl border border-border bg-background/70 p-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                Sensor coverage
              </p>
              <p className="mt-1 text-3xl font-bold">{count || 0}</p>
              <p className="text-sm text-muted-foreground">
                {count === 1 ? 'live sensor seen' : 'live sensors seen'}
              </p>
            </div>
            <div className="h-px bg-border" />
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                Latest signal
              </p>
              <p className="mt-1 text-sm font-semibold">
                {latestEvent ? eventLabel(latestEvent) : 'No live rows yet'}
              </p>
              <p className="text-sm text-muted-foreground">
                {latestEvent
                  ? `${latestEvent.room} · ${formatTimestamp(latestEvent.timestamp)}`
                  : 'Start ingestion to populate live data.'}
              </p>
            </div>
          </div>
        </div>
      </motion.section>
    );
  }

  const steps = storySteps(incident);

  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      className="relative overflow-hidden rounded-2xl border border-red-200/80 bg-card/80 p-5 shadow-sm dark:border-red-950/70 sm:p-6"
    >
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(244,63,94,0.18),transparent_30rem),radial-gradient(circle_at_bottom_left,rgba(20,184,166,0.12),transparent_24rem)]" />
      <div className="relative">
        <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-start">
          <div className="max-w-3xl">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-red-500/30 bg-red-500/10 px-3 py-1 text-xs font-semibold text-red-600 dark:text-red-300">
              <ShieldAlert className="h-3.5 w-3.5" />
              Live incident story
            </div>
            <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
              {incidentHeadline(incident)}
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground sm:text-base">
              This is the caregiver-readable chain of evidence from the same live
              sensor. The alert was rule-based; Gemma explanations stay
              separate from the urgent path.
            </p>
          </div>

          <div className="rounded-2xl border border-border bg-background/70 p-4 lg:min-w-[250px]">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              Caregiver action
            </p>
            <div className="mt-3 flex items-start gap-3">
              <div className="rounded-xl bg-amber-500/10 p-2 text-amber-600 dark:text-amber-300">
                <Brain className="h-5 w-5" />
              </div>
              <div>
                <p className="font-semibold">Explain in Telegram or chat</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Use `/explain` or the alert button for a local-data summary.
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-6 grid gap-3 md:grid-cols-5">
          {steps.map((step, index) => {
            const Icon = step.icon;
            return (
              <motion.article
                key={step.label}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.06 }}
                className="relative rounded-2xl border border-border bg-background/78 p-4"
              >
                {index < steps.length - 1 ? (
                  <div className="absolute left-[calc(100%-0.25rem)] top-8 hidden h-px w-4 bg-border md:block" />
                ) : null}
                <div className={cn('mb-4 inline-flex rounded-xl border p-2', toneClasses(step.tone))}>
                  <Icon className="h-4 w-4" />
                </div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  {step.label}
                </p>
                <h3 className="mt-2 text-sm font-bold">{step.title}</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  {step.detail}
                </p>
              </motion.article>
            );
          })}
        </div>
      </div>
    </motion.section>
  );
});

IncidentStory.displayName = 'IncidentStory';
