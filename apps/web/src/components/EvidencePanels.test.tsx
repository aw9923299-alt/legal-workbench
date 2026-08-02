import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EvidencePanels } from './EvidencePanels';

describe('evidence boundaries', () => {
  it('labels confirmed facts and AI inference as different evidence classes', () => {
    render(<EvidencePanels result={{
      legalRelevance: 'relevant', messageRole: 'new_request', actionability: 'create_candidate',
      suggestedTitle: '审核合同', categoryCandidates: [], deadlineCandidates: [],
      confirmedFacts: [{ statement: '原文明确要求审核', sourceMessageId: 'om_1' }],
      inferredFacts: [{ statement: '可能较紧急', basis: '使用尽快一词', confidence: 0.6 }],
      missingInformation: [], reasons: ['有明确请求'], confidence: 0.8,
    }} />);
    expect(screen.getByRole('region', { name: '已确认事实' })).toHaveClass('confirmed-facts');
    expect(screen.getByRole('region', { name: 'AI推断' })).toHaveClass('inferred-facts');
    expect(screen.getByText(/未经人工确认/)).toBeInTheDocument();
  });
});
