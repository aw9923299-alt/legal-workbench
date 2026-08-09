import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { legalApi } from '../services/api';
import type { ReviewPackage } from '../types/api';
import ReviewCenterPage from './ReviewCenterPage';

const sourceRef = 'knowledge:chunk:fixture-law';
const reviewPackage: ReviewPackage = {
  id: '11111111-1111-4111-8111-111111111111',
  matterId: '22222222-2222-4222-8222-222222222222',
  workItemId: null,
  packageType: 'legal_analysis',
  status: 'pending_review',
  title: '示例逐项 Grounding 审核包',
  background: '仅用于 UI 测试。',
  confirmedFacts: [{ fact: '存在示例合同', sourceRefs: [sourceRef] }],
  unconfirmedFacts: [],
  reasoning: '依据示例来源形成建议。',
  risks: [],
  alternatives: [],
  citations: [{
    sourceRef,
    title: '示例法规',
    sourceType: 'knowledge_document',
    locator: '第一条',
    contentHash: 'a'.repeat(64),
  }],
  proposedContent: '示例建议。',
  target: { channel: 'internal' },
  createdBy: 'fixture',
  submittedAt: '2026-08-09T10:00:00Z',
  approvedContentHash: null,
  groundingPayload: {
    coreFacts: [{ fact: '存在示例合同', sourceRefs: [sourceRef] }],
    integratedRisks: [{ description: '示例风险', severity: 'high', supportRefs: [sourceRef] }],
  },
  version: 1,
};

describe('Review package grounding', () => {
  afterEach(() => vi.restoreAllMocks());

  it('opens the original citation from each grounded conclusion', async () => {
    vi.spyOn(legalApi, 'listReviewPackages').mockResolvedValue([reviewPackage]);
    render(<MemoryRouter><ReviewCenterPage /></MemoryRouter>);

    expect(await screen.findByText(reviewPackage.title)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '审核' }));
    expect(await screen.findByText('逐项证据追溯')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: sourceRef })[0]);
    expect(await screen.findByText('原始授权来源')).toBeInTheDocument();
    expect(screen.getByText('示例法规')).toBeInTheDocument();
    expect(screen.getByText('第一条')).toBeInTheDocument();
  });
});
