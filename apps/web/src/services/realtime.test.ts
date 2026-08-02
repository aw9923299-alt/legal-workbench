import { describe, expect, it } from 'vitest';
import { nextRealtimeDelay, shouldUsePollingFallback } from './realtime';

describe('SSE reconnect policy', () => {
  it('uses bounded exponential backoff before polling fallback', () => {
    expect([0, 1, 2, 3, 4, 5, 9].map(nextRealtimeDelay)).toEqual([
      1000, 2000, 4000, 8000, 16000, 30000, 30000,
    ]);
  });

  it('switches to polling after repeated SSE failures', () => {
    expect(shouldUsePollingFallback(1)).toBe(false);
    expect(shouldUsePollingFallback(2)).toBe(true);
  });
});
