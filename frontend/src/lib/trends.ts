export const NIGHT_WINDOW_STORAGE_KEY = 'emergyx-trends-night-window-v1';
export const DEFAULT_NIGHT_START_HOUR = 22;
export const DEFAULT_NIGHT_END_HOUR = 6;

export interface NightWindowPreference {
  startHour: number;
  endHour: number;
}

function normalizeHour(value: unknown, fallback: number): number {
  const parsed =
    typeof value === 'number'
      ? value
      : typeof value === 'string'
        ? Number.parseInt(value, 10)
        : Number.NaN;
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(23, Math.max(0, Math.trunc(parsed)));
}

export function getDefaultNightWindow(): NightWindowPreference {
  return {
    startHour: DEFAULT_NIGHT_START_HOUR,
    endHour: DEFAULT_NIGHT_END_HOUR,
  };
}

export function loadNightWindowPreference(): NightWindowPreference {
  if (typeof window === 'undefined') {
    return getDefaultNightWindow();
  }
  try {
    const raw = window.localStorage.getItem(NIGHT_WINDOW_STORAGE_KEY);
    if (!raw) {
      return getDefaultNightWindow();
    }
    const parsed = JSON.parse(raw) as Partial<NightWindowPreference> | null;
    return {
      startHour: normalizeHour(parsed?.startHour, DEFAULT_NIGHT_START_HOUR),
      endHour: normalizeHour(parsed?.endHour, DEFAULT_NIGHT_END_HOUR),
    };
  } catch {
    return getDefaultNightWindow();
  }
}

export function saveNightWindowPreference(input: Partial<NightWindowPreference>) {
  if (typeof window === 'undefined') {
    return getDefaultNightWindow();
  }
  const next = {
    startHour: normalizeHour(input.startHour, DEFAULT_NIGHT_START_HOUR),
    endHour: normalizeHour(input.endHour, DEFAULT_NIGHT_END_HOUR),
  };
  window.localStorage.setItem(NIGHT_WINDOW_STORAGE_KEY, JSON.stringify(next));
  return next;
}

