export function nextRealtimeDelay(attempt: number): number {
  return Math.min(1000 * (2 ** Math.max(attempt, 0)), 30_000);
}

export function shouldUsePollingFallback(failedAttempts: number): boolean {
  return failedAttempts >= 2;
}
