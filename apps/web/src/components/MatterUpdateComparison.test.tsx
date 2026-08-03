import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { MatterUpdateProposal } from '../types/api';
import MatterUpdateComparison, { buildProposalFieldDecisions } from './MatterUpdateComparison';

const proposal: MatterUpdateProposal = {
  id: 'proposal-1',
  candidateId: 'candidate-1',
  matterId: 'matter-1',
  baseMatterVersion: 3,
  proposedChanges: {
    title: {
      currentValue: '当前标题',
      messageExtractedValue: '消息中的标题',
      aiSuggestedValue: 'AI 建议标题',
    },
  },
  finalChanges: {},
  fieldDecisions: [],
  reason: '消息包含事项更新',
  status: 'pending',
  createdBy: 'legal',
  reviewedBy: null,
  reviewedAt: null,
  rejectionReason: null,
  createdAt: '2026-08-03T09:00:00Z',
  version: 1,
};

describe('MatterUpdateComparison', () => {
  afterEach(cleanup);

  it('keeps current, extracted, AI and human values visibly distinct', () => {
    render(
      <MatterUpdateComparison
        proposal={proposal}
        decisions={{ title: 'approve' }}
        finalValues={{ title: '法务最终标题' }}
        onDecisionChange={vi.fn()}
        onFinalValueChange={vi.fn()}
      />,
    );

    expect(screen.getAllByText('当前值').length).toBeGreaterThan(0);
    expect(screen.getAllByText('消息提取值').length).toBeGreaterThan(0);
    expect(screen.getAllByText('AI 建议值').length).toBeGreaterThan(0);
    expect(screen.getAllByText('法务最终值').length).toBeGreaterThan(0);
    expect(screen.getByText('当前标题')).toBeInTheDocument();
    expect(screen.getByText('AI 建议标题')).toBeInTheDocument();
    expect(screen.getByLabelText('标题 法务最终值')).toHaveValue('法务最终标题');
  });

  it('reports edits only as the human final value', () => {
    const onFinalValueChange = vi.fn();
    render(
      <MatterUpdateComparison
        proposal={proposal}
        decisions={{ title: 'approve' }}
        finalValues={{ title: '法务最终标题' }}
        onDecisionChange={vi.fn()}
        onFinalValueChange={onFinalValueChange}
      />,
    );

    fireEvent.change(screen.getByLabelText('标题 法务最终值'), {
      target: { value: '法务修改后的标题' },
    });

    expect(onFinalValueChange).toHaveBeenCalledWith('title', '法务修改后的标题');
    expect(screen.getByText('AI 建议标题')).toBeInTheDocument();
  });

  it('builds partial approval without treating rejected AI values as final values', () => {
    const values = buildProposalFieldDecisions(
      {
        ...proposal,
        proposedChanges: {
          ...proposal.proposedChanges,
          nextAction: {
            currentValue: '旧行动',
            messageExtractedValue: '消息行动',
            aiSuggestedValue: 'AI 行动',
          },
        },
      },
      { title: 'approve', nextAction: 'reject' },
      { title: '法务最终标题', nextAction: '不应提交' },
    );

    expect(values).toEqual([
      { fieldName: 'title', decision: 'approve', finalValue: '法务最终标题' },
      { fieldName: 'nextAction', decision: 'reject', finalValue: null },
    ]);
  });
});
