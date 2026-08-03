import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearMutationContext,
  formatApiErrorPayload,
  getOrCreateMutationContext,
  legalApi,
} from './api';

describe('API reliability helpers', () => {
  beforeEach(() => sessionStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it('reuses one idempotency key for the same unresolved business action', () => {
    const first = getOrCreateMutationContext('confirm:1', { title: '事项' });
    const retry = getOrCreateMutationContext('confirm:1', { title: '事项' });
    expect(retry).toEqual(first);

    clearMutationContext('confirm:1');
    const nextAction = getOrCreateMutationContext('confirm:1', { title: '事项' });
    expect(nextAction.idempotencyKey).not.toBe(first.idempotencyKey);
  });

  it('renders structured validation errors without object coercion', () => {
    const formatted = formatApiErrorPayload(
      {
        detail: [
          { loc: ['body', 'title'], msg: 'Field required', type: 'missing' },
        ],
      },
      422,
    );
    expect(formatted.message).toContain('body.title');
    expect(formatted.message).toContain('Field required');
    expect(formatted.message).not.toContain('[object Object]');
  });

  it('sends explicit idempotency and correlation identities for candidate confirmation', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      requests.push({ url: String(url), init });
      if (String(url).endsWith('/auth/session')) return new Response('{}', { status: 200 });
      return new Response(JSON.stringify({ candidateId: 'candidate-1', status: 'ignored', matterId: null, version: 2, idempotentReplay: false }), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      });
    }));
    await legalApi.resolveCandidate('candidate-1', {
      candidateVersion: 1, action: 'ignore',
    }, { idempotencyKey: 'idem-confirm-1', correlationId: 'corr-confirm-1' });
    const mutation = requests.find((value) => value.url.includes('/resolve'));
    const headers = new Headers(mutation?.init?.headers);
    expect(headers.get('Idempotency-Key')).toBe('idem-confirm-1');
    expect(headers.get('X-Correlation-ID')).toBe('corr-confirm-1');
  });

  it('uses the dedicated human-review endpoint for matter updates', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      requests.push({ url: String(url), init });
      if (String(url).endsWith('/auth/session')) return new Response('{}', { status: 200 });
      return new Response(JSON.stringify({
        proposalId: 'proposal-1', candidateId: 'candidate-1', matterId: 'matter-1',
        status: 'pending', version: 1, idempotentReplay: false,
      }), { status: 201, headers: { 'Content-Type': 'application/json' } });
    }));

    await legalApi.createMatterUpdateProposal('candidate-1', {
      candidateVersion: 1,
      matterId: 'matter-1',
      proposedChanges: {
        title: { currentValue: null, messageExtractedValue: null, aiSuggestedValue: null },
      },
      reason: '消息包含事项更新',
    }, { idempotencyKey: 'idem-proposal-1', correlationId: 'corr-proposal-1' });

    const mutation = requests.find((value) => value.url.includes('/matter-update-proposals'));
    expect(mutation?.url).toContain('/inbox/candidates/candidate-1/matter-update-proposals');
    expect(new Headers(mutation?.init?.headers).get('Idempotency-Key')).toBe('idem-proposal-1');
    expect(JSON.parse(String(mutation?.init?.body))).toMatchObject({ matterId: 'matter-1' });
  });
});
