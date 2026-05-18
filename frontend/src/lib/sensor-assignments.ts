export const SENSOR_ASSIGNMENTS_STORAGE_KEY = 'emergyx-sensor-room-assignments-v1';

export type SensorRoomAssignments = Record<string, string>;

function normalizeRoom(value: string) {
  return value.trim().replace(/\s+/g, ' ');
}

export function loadSensorRoomAssignments(): SensorRoomAssignments {
  if (typeof window === 'undefined') {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(SENSOR_ASSIGNMENTS_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const normalized: SensorRoomAssignments = {};
    for (const [sensorId, roomValue] of Object.entries(parsed)) {
      if (typeof roomValue !== 'string') {
        continue;
      }
      const room = normalizeRoom(roomValue);
      if (!room) {
        continue;
      }
      normalized[sensorId] = room;
    }
    return normalized;
  } catch {
    return {};
  }
}

export function saveSensorRoomAssignments(assignments: SensorRoomAssignments) {
  if (typeof window === 'undefined') {
    return;
  }
  const normalized: SensorRoomAssignments = {};
  for (const [sensorId, roomValue] of Object.entries(assignments)) {
    const room = normalizeRoom(roomValue);
    if (!room) {
      continue;
    }
    normalized[sensorId] = room;
  }
  window.localStorage.setItem(
    SENSOR_ASSIGNMENTS_STORAGE_KEY,
    JSON.stringify(normalized),
  );
}

export function setAssignedRoom(
  assignments: SensorRoomAssignments,
  sensorId: string,
  roomValue: string,
) {
  const next = { ...assignments };
  const room = normalizeRoom(roomValue);
  if (!room) {
    delete next[sensorId];
  } else {
    next[sensorId] = room;
  }
  saveSensorRoomAssignments(next);
  return next;
}

