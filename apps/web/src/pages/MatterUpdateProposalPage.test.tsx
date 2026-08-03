import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, legalApi } from '../services/api';
import type { LegalMatter, MatterUpdateProposal } from '../types/api';
import MatterUpdateProposalPage from './MatterUpdateProposalPage';

const proposal: MatterUpdateProposal = {
  id: 'proposal-1', candidateId: 'candidate-1', matterId: 'matter-1',
  baseMatterVersion: 1,
  proposedChanges: {
    title: {
      currentValue: '当前标题', messageExtractedValue: '消息标题', aiSuggestedValue: 'AI 标题',
    },
  },
  finalChanges: {}, fieldDecisions: [], reason: '消息提出了标题更新', status: 'pending',
  createdBy: 'legal', reviewedBy: null, reviewedAt: null, rejectionReason: null,
  createdAt: '2026-08-03T09:00:00Z', version: 1,
};

const matter: LegalMatter = {
  id: 'matter-1', matterNumber: 'LW-2026-001', title: '当前标题',
  primaryCategory: 'contract', secondaryCategories: [], lifecycleStatus: 'open',
  workStatus: 'ready', ownerId: 'legal', collaboratorIds: [], requesterIds: [], entityIds: [],
  legalRisk: 'medium', businessImpact: 'project', priority: 'medium',
  prioritySource: 'legal_confirmed', targetDeadlineAt: null, nextAction: '核实消息',
  confidentiality: 'internal', summary: null, objective: null, currentStage: null,
  version: 1, openedAt: '2026-08-01T09:00:00Z', resolvedAt: null, closedAt: null,
  reopenedAt: null,
};

describe('MatterUpdateProposalPage', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('refreshes a 409 conflict while preserving the legal final-value draft', async () => {
    vi.spyOn(legalApi, 'getMatterUpdateProposal').mockResolvedValue(proposal);
    vi.spyOn(legalApi, 'getMatter')
      .mockResolvedValueOnce(matter)
      .mockResolvedValue({ ...matter, title: '他人已更新标题', version: 2 });
    const review = vi.spyOn(legalApi, 'reviewMatterUpdateProposal').mockRejectedValue(
      new ApiError('Matter version conflict', 409, 'ENTITY_VERSION_CONFLICT', 'corr-conflict'),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <MemoryRouter initialEntries={['/matter-update-proposals/proposal-1']}>
        <QueryClientProvider client={client}>
          <Routes>
            <Route path="/matter-update-proposals/:proposalId" element={<MatterUpdateProposalPage />} />
          </Routes>
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await screen.findByLabelText('标题 逐项决定');
    fireEvent.click(screen.getByRole('radio', { name: '批准' }));
    const finalValue = screen.getByLabelText('标题 法务最终值');
    await waitFor(() => expect(finalValue).not.toBeDisabled());
    fireEvent.change(finalValue, { target: { value: '法务保留草稿' } });
    fireEvent.click(screen.getByRole('button', { name: /提交逐项审核/ }));

    await waitFor(() => expect(review).toHaveBeenCalledOnce());
    expect(await screen.findByText('版本冲突，未修改 Matter')).toBeInTheDocument();
    expect(screen.getByLabelText('标题 法务最终值')).toHaveValue('法务保留草稿');
    expect(review.mock.calls[0]?.[1].decisions[0]).toEqual({
      fieldName: 'title', decision: 'approve', finalValue: '法务保留草稿',
    });
  });

  it('shows loading and a correlated load error, then retries successfully', async () => {
    const request = vi.spyOn(legalApi, 'getMatterUpdateProposal')
      .mockRejectedValueOnce(
        new ApiError('加载更新建议失败', 500, 'PROPOSAL_LOAD_FAILED', 'corr-proposal'),
      )
      .mockResolvedValueOnce(proposal);
    vi.spyOn(legalApi, 'getMatter').mockResolvedValue(matter);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const { container } = render(
      <MemoryRouter initialEntries={['/matter-update-proposals/proposal-1']}>
        <QueryClientProvider client={client}>
          <Routes>
            <Route path="/matter-update-proposals/:proposalId" element={<MatterUpdateProposalPage />} />
          </Routes>
        </QueryClientProvider>
      </MemoryRouter>,
    );

    expect(container.querySelector('.ant-spin')).toBeInTheDocument();
    expect(await screen.findByText('加载更新建议失败')).toBeInTheDocument();
    expect(screen.getByText('Correlation ID：corr-proposal')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /重\s*试/ }));

    expect(await screen.findByText('Matter 更新建议审核')).toBeInTheDocument();
    expect(screen.getByLabelText('标题 逐项决定')).toBeInTheDocument();
    expect(request).toHaveBeenCalledTimes(2);
  });
});
