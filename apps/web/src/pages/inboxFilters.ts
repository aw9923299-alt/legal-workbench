export type InboxView =
  | 'all'
  | 'pending_analysis'
  | 'queued'
  | 'analysing'
  | 'pending_confirmation'
  | 'processed'
  | 'ignored'
  | 'failed'
  | 'dead_letter';

export interface InboxFilterItem {
  status: string;
  candidateStatus: string | null;
}

export function statusesForInboxView(view: InboxView): string[] | undefined {
  const mapping: Partial<Record<InboxView, string[]>> = {
    pending_analysis: ['received'],
    queued: ['queued_for_analysis', 'context_prepared', 'agent_queued'],
    analysing: ['analysing'],
    pending_confirmation: ['candidate_created'],
    processed: ['candidate_created', 'ignored'],
    ignored: ['ignored'],
    failed: ['analysis_failed'],
    dead_letter: ['dead_letter'],
  };
  return mapping[view];
}

export function matchesInboxView(item: InboxFilterItem, view: InboxView): boolean {
  if (view === 'all') return true;
  if (view === 'pending_confirmation') {
    return item.status === 'candidate_created'
      && ['pending_analysis', 'pending_confirmation'].includes(item.candidateStatus ?? '');
  }
  if (view === 'processed') {
    return ['confirmed', 'linked', 'information_only'].includes(item.candidateStatus ?? '');
  }
  if (view === 'ignored') {
    return item.status === 'ignored' || item.candidateStatus === 'ignored';
  }
  return statusesForInboxView(view)?.includes(item.status) ?? false;
}
