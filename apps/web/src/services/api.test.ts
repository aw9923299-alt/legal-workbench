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

  it('sends WorkItem and dependency versions on lifecycle mutations', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      requests.push({ url: String(url), init });
      if (String(url).endsWith('/auth/session')) return new Response('{}', { status: 200 });
      return new Response(JSON.stringify({
        workItemId: 'work-item-1', dependencyId: 'dependency-1', status: 'satisfied',
        version: 4, workItemVersion: 4, dependencyVersion: 2, idempotentReplay: false,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));

    const mutation = { idempotencyKey: 'idem-work-item-1', correlationId: 'corr-work-item-1' };
    await legalApi.applyWorkItemAction(
      'work-item-1', 'pause', 3, { reason: '切换事项' }, mutation,
    );
    await legalApi.createDependency('work-item-1', {
      workItemVersion: 2,
      dependencyType: 'material',
      externalPartyId: 'business-owner',
      description: '等待材料',
    }, mutation);
    await legalApi.resolveDependency(
      'work-item-1', 'dependency-1', 4, 1, '材料已收到', mutation,
    );

    const pause = requests.find((value) => value.url.endsWith('/work-items/work-item-1/pause'));
    expect(new Headers(pause?.init?.headers).get('If-Match')).toBe('3');
    expect(JSON.parse(String(pause?.init?.body))).toEqual({ reason: '切换事项' });
    const create = requests.find((value) => value.url.endsWith('/work-items/work-item-1/dependencies'));
    expect(new Headers(create?.init?.headers).get('If-Match')).toBe('2');
    expect(new Headers(create?.init?.headers).get('Idempotency-Key')).toBe('idem-work-item-1');
    const resolve = requests.find((value) => value.url.includes('/dependencies/dependency-1/resolve'));
    expect(new Headers(resolve?.init?.headers).get('If-Match')).toBe('4');
    expect(JSON.parse(String(resolve?.init?.body))).toEqual({
      dependencyVersion: 1, reason: '材料已收到',
    });
  });
});
