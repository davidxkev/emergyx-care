export function confirmDestructiveAction(message: string) {
  if (typeof window === 'undefined') {
    return false;
  }
  return window.confirm(`${message}\n\nThis cannot be undone.`);
}
