import type {
  AlertRead,
  AgentStatus,
  EventRead,
  IncidentContext,
  Mode,
  ModeSnapshot,
} from '@/lib/types';

export function formatTimestamp(timestamp?: string | null): string {
  if (!timestamp) {
    return 'No data';
  }
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return timestamp;
  }
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatTime(timestamp?: string | null): string {
  if (!timestamp) {
    return 'No time';
  }
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return timestamp;
  }
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function sourceLabel(source?: string | null): string {
  if (!source) {
    return 'Local';
  }
  if (source === 'live_sensor') {
    return 'Live sensor';
  }
  if (source === 'simulated_seed') {
    return 'Demo baseline';
  }
  if (source === 'simulated') {
    return 'Demo run';
  }
  return source.replace(/_/g, ' ');
}

export function eventLabel(event?: EventRead | null): string {
  if (!event) {
    return 'No timeline event';
  }
  if (event.event_type === 'person_present') {
    return event.value === 'true' ? 'Person detected' : 'No person detected';
  }
  if (event.event_type === 'fall_detected') {
    return event.value === 'true' ? 'Likely fall detected' : 'Fall state cleared';
  }
  if (event.event_type === 'illuminance') {
    return 'Light context updated';
  }
  return event.event_type.replace(/_/g, ' ');
}

export function snapshotState(snapshot: ModeSnapshot): {
  safety: string;
  safetyTone: 'positive' | 'negative';
  incident: string;
  presence: string;
  alert: string;
} {
  const activeFall = snapshot.latest_fall?.value === 'true';
  return {
    safety: activeFall ? 'Attention needed' : 'Stable',
    safetyTone: activeFall ? 'negative' : 'positive',
    incident: snapshot.latest_incident?.event?.timestamp
      ? `Likely fall at ${formatTime(snapshot.latest_incident.event.timestamp)}`
      : 'No urgent incident',
    presence:
      snapshot.latest_person?.value === 'true' ? 'Person detected' : 'Not detected',
    alert:
      snapshot.latest_incident?.alert?.sent_success === true
        ? 'Sent immediately'
        : 'Ready',
  };
}

export function gemmaStatusLabel(status: AgentStatus | null): string {
  if (!status) {
    return 'Unavailable';
  }
  if (status.status === 'online') {
    return 'Gemma via Ollama';
  }
  if (status.status === 'disabled') {
    return 'Gemma disabled';
  }
  return 'Deterministic fallback';
}

export function gemmaTone(status: AgentStatus | null): 'positive' | 'negative' {
  return status?.status === 'online' ? 'positive' : 'negative';
}

export function modeBadge(mode: Mode): { label: string; detail: string } {
  return mode === 'live'
    ? { label: 'LIVE', detail: 'Real sensor data only' }
    : { label: 'DEMO', detail: 'Simulated data only' };
}

export function incidentTimeline(incident?: IncidentContext | null) {
  if (!incident) {
    return [];
  }
  const room = incident.room ?? 'the room';
  const light = incident.light_context;
  return [
    {
      label: 'Before',
      value: (incident.person_before ?? incident.before_person)?.timestamp
        ? `Person detected at ${formatTime((incident.person_before ?? incident.before_person)?.timestamp)}`
        : 'No person-presence event recorded before this incident.',
    },
    {
      label: 'Event',
      value: incident.event?.timestamp
        ? `Likely fall detected at ${formatTime(incident.event.timestamp)} in ${room}`
        : 'No likely-fall event found.',
    },
    {
      label: 'After',
      value: (incident.fall_clear_after ?? incident.after_fall_clear)?.timestamp
        ? `Fall state cleared at ${formatTime((incident.fall_clear_after ?? incident.after_fall_clear)?.timestamp)}`
        : 'No fall-clear event recorded after this incident.',
    },
    {
      label: 'Context',
      value: light
        ? `Room was ${light.category ?? 'unknown'}, ${typeof light.lux === 'number' ? `${light.lux.toFixed(1)} lux` : 'no lux reading'}.`
        : 'No light context recorded for this incident.',
    },
    {
      label: 'Alert',
      value:
        incident.alert?.timestamp && incident.alert?.sent_success
          ? `Rule-based urgent alert sent via ${incident.alert.sent_channel ?? 'Telegram'} at ${formatTime(incident.alert.timestamp)}`
          : 'No remote alert delivery was recorded for this incident.',
    },
  ];
}

export function alertTone(alert?: AlertRead | null): 'positive' | 'negative' {
  if (!alert) {
    return 'positive';
  }
  return alert.severity === 'critical' || alert.severity === 'high'
    ? 'negative'
    : 'positive';
}

export function severityLabel(severity?: string | null): string {
  if (!severity) {
    return 'Standard';
  }
  if (severity === 'critical' || severity === 'high') {
    return 'Urgent';
  }
  if (severity === 'medium') {
    return 'Review';
  }
  return 'Normal';
}
