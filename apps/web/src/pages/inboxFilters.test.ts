import { describe, expect, it } from 'vitest';
import { matchesInboxView, statusesForInboxView } from './inboxFilters';

describe('inbox operational views', () => {
  it('maps queue views to durable message states', () => {
    expect(statusesForInboxView('queued')).toEqual([
      'queued_for_analysis',
      'context_prepared',
      'agent_queued',
    ]);
    expect(statusesForInboxView('all')).toBeUndefined();
  });

  it('separates pending confirmation, processed, failed and dead letters', () => {
    const base = { status: 'candidate_created', candidateStatus: 'pending_confirmation' };
    expect(matchesInboxView(base, 'pending_confirmation')).toBe(true);
    expect(matchesInboxView({ ...base, candidateStatus: 'confirmed' }, 'processed')).toBe(true);
    expect(matchesInboxView({ status: 'analysis_failed', candidateStatus: null }, 'failed')).toBe(true);
    expect(matchesInboxView({ status: 'dead_letter', candidateStatus: null }, 'dead_letter')).toBe(true);
  });
});
