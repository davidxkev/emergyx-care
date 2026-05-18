export const ROOM_DISPLAY_NAMES_STORAGE_KEY = 'emergyx-room-display-names-v1';

export type RoomDisplayNames = Record<string, string>;

function normalizeRoomKey(roomKey: string) {
  return roomKey.trim();
}

function normalizeDisplayName(displayName: string) {
  return displayName.trim().replace(/\s+/g, ' ');
}

export function loadRoomDisplayNames(): RoomDisplayNames {
  if (typeof window === 'undefined') {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(ROOM_DISPLAY_NAMES_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const names: RoomDisplayNames = {};
    for (const [roomKey, roomLabel] of Object.entries(parsed)) {
      if (typeof roomLabel !== 'string') {
        continue;
      }
      const cleanKey = normalizeRoomKey(roomKey);
      const cleanLabel = normalizeDisplayName(roomLabel);
      if (!cleanKey || !cleanLabel) {
        continue;
      }
      names[cleanKey] = cleanLabel;
    }
    return names;
  } catch {
    return {};
  }
}

export function saveRoomDisplayNames(displayNames: RoomDisplayNames) {
  if (typeof window === 'undefined') {
    return;
  }
  const clean: RoomDisplayNames = {};
  for (const [roomKey, roomLabel] of Object.entries(displayNames)) {
    const cleanKey = normalizeRoomKey(roomKey);
    const cleanLabel = normalizeDisplayName(roomLabel);
    if (!cleanKey || !cleanLabel) {
      continue;
    }
    clean[cleanKey] = cleanLabel;
  }
  window.localStorage.setItem(
    ROOM_DISPLAY_NAMES_STORAGE_KEY,
    JSON.stringify(clean),
  );
}

export function setRoomDisplayName(
  displayNames: RoomDisplayNames,
  roomKey: string,
  displayName: string,
) {
  const next = { ...displayNames };
  const cleanKey = normalizeRoomKey(roomKey);
  const cleanLabel = normalizeDisplayName(displayName);
  if (!cleanLabel) {
    delete next[cleanKey];
  } else {
    next[cleanKey] = cleanLabel;
  }
  saveRoomDisplayNames(next);
  return next;
}

