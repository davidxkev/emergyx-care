type ClassValue =
  | string
  | number
  | false
  | null
  | undefined
  | ClassValue[]
  | Record<string, boolean | null | undefined>;

function flatten(input: ClassValue): string[] {
  if (!input) {
    return [];
  }
  if (typeof input === 'string' || typeof input === 'number') {
    return [String(input)];
  }
  if (Array.isArray(input)) {
    return input.flatMap(flatten);
  }
  return Object.entries(input)
    .filter(([, value]) => Boolean(value))
    .map(([key]) => key);
}

export function cn(...inputs: ClassValue[]) {
  return inputs.flatMap(flatten).join(' ');
}
