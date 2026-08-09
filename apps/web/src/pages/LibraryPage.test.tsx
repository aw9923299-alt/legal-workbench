import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { legalApi } from '../services/api';
import type { KnowledgeDocument, KnowledgeDocumentDetails } from '../types/api';
import LibraryPage from './LibraryPage';

const document: KnowledgeDocument = {
  id: '11111111-1111-4111-8111-111111111111',
  sourceType: 'local_document',
  sourceId: '22222222-2222-4222-8222-222222222222',
  documentVersionId: '33333333-3333-4333-8333-333333333333',
  matterId: null,
  title: '示例公司制度',
  documentType: 'company_policy',
  agentTypes: ['contract_review'],
  matterTypes: ['contract'],
  jurisdiction: 'CN',
  effectiveFrom: '2026-01-01',
  effectiveTo: null,
  status: 'active',
  sourcePriority: 50,
  internalPrecedent: false,
  confidentiality: 'internal',
  approvedBy: null,
  authorityType: 'company_policy',
  authorityRole: 'internal_basis',
  authorityStatus: 'effective',
  metadataStatus: 'ready',
  issuer: '示例公司',
  documentNumber: null,
  enabled: true,
  createdAt: '2026-08-09T10:00:00Z',
  updatedAt: '2026-08-09T10:00:00Z',
  version: 1,
};

const details: KnowledgeDocumentDetails = {
  document,
  chunks: [{
    id: '44444444-4444-4444-8444-444444444444', knowledgeDocumentId: document.id,
    documentSegmentId: null, sequence: 1, locator: '第1段', text: '示例制度正文。',
    textHash: 'a'.repeat(64), estimatedTokenCount: 8,
    tokenEstimator: 'utf8-bytes-ceil-div-4-v1', tokenCountEstimated: true,
    createdAt: '2026-08-09T10:00:00Z',
  }],
  retrievalLogs: [{
    id: '55555555-5555-4555-8555-555555555555', queryHash: 'b'.repeat(64),
    filters: { matterType: 'contract' }, selectedChunkIds: ['44444444-4444-4444-8444-444444444444'],
    componentScores: {}, correlationId: 'fixture', agentRunId: null,
    candidateCount: 3, selectedChunkCount: 1, selectedTokenCount: 8,
    excludedByTokenBudgetCount: 2, excludedDuplicateCount: 0,
    budget: { maxChunks: 1 }, createdAt: '2026-08-09T10:00:00Z',
  }],
};

describe('Knowledge library', () => {
  afterEach(() => vi.restoreAllMocks());

  it('shows durable authority metadata, chunks, and retrieval hits', async () => {
    vi.spyOn(legalApi, 'listKnowledgeDocuments').mockResolvedValue([document]);
    vi.spyOn(legalApi, 'getKnowledgeDocument').mockResolvedValue(details);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><LibraryPage /></QueryClientProvider>);

    expect(await screen.findByText('示例公司制度')).toBeInTheDocument();
    fireEvent.click(screen.getByText('示例公司制度'));

    expect(await screen.findByRole('tab', { name: /Chunk（1）/ })).toBeInTheDocument();
    expect(screen.getByText('内部依据')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /Chunk（1）/ }));
    expect(await screen.findByText('示例制度正文。')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /检索命中（1）/ }));
    expect(await screen.findByText('候选/选中')).toBeInTheDocument();
    expect(screen.getByText('3 / 1')).toBeInTheDocument();
  });
});
