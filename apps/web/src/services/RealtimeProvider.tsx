import { useQueryClient } from '@tanstack/react-query';
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { apiEventStreamUrl } from './api';
import { nextRealtimeDelay, shouldUsePollingFallback } from './realtime';

interface RealtimeState {
  connected: boolean;
  pollingFallback: boolean;
  lastEventAt: string | null;
  pollingInterval: number | false;
}

const RealtimeContext = createContext<RealtimeState>({
  connected: false,
  pollingFallback: true,
  lastEventAt: null,
  pollingInterval: 15_000,
});

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [pollingFallback, setPollingFallback] = useState(false);
  const [lastEventAt, setLastEventAt] = useState<string | null>(null);

  useEffect(() => {
    let source: EventSource | undefined;
    let timer: number | undefined;
    let stopped = false;
    let attempt = 0;

    const connect = () => {
      if (stopped) return;
      source = new EventSource(apiEventStreamUrl, { withCredentials: true });
      source.onopen = () => {
        attempt = 0;
        setConnected(true);
        setPollingFallback(false);
      };
      const update = () => {
        setLastEventAt(new Date().toISOString());
        void queryClient.invalidateQueries({ queryKey: ['inbox'] });
        void queryClient.invalidateQueries({ queryKey: ['agent-runs'] });
        void queryClient.invalidateQueries({ queryKey: ['system'] });
        void queryClient.invalidateQueries({ queryKey: ['feishu-status'] });
      };
      source.onmessage = update;
      source.addEventListener('system.health', update);
      source.addEventListener('message.ingested', update);
      source.addEventListener('agent-run.updated', update);
      source.addEventListener('candidate.created', update);
      source.addEventListener('outbox.failed', update);
      source.onerror = () => {
        source?.close();
        setConnected(false);
        attempt += 1;
        if (shouldUsePollingFallback(attempt)) setPollingFallback(true);
        timer = window.setTimeout(connect, nextRealtimeDelay(attempt - 1));
      };
    };
    connect();
    return () => {
      stopped = true;
      source?.close();
      if (timer) window.clearTimeout(timer);
    };
  }, [queryClient]);

  const value = useMemo<RealtimeState>(() => ({
    connected,
    pollingFallback,
    lastEventAt,
    pollingInterval: connected ? false : 15_000,
  }), [connected, lastEventAt, pollingFallback]);

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
}

export function useRealtimeStatus(): RealtimeState {
  return useContext(RealtimeContext);
}
