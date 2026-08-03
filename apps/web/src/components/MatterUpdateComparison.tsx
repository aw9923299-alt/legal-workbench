import { Input, Radio, Table, Tag, Typography } from 'antd';
import type {
  MatterUpdateProposal,
  MatterUpdateProposalField,
  ProposedFieldValues,
} from '../types/api';

const { Text } = Typography;

export type MatterFieldDecision = 'approve' | 'reject';

export const matterFieldLabels: Record<MatterUpdateProposalField, string> = {
  title: '标题',
  category: '分类',
  priority: '优先级',
  deadline: '截止时间',
  owner: '负责人',
  currentStatus: '当前状态',
  nextAction: '下一步行动',
  newWorkItems: '新增 WorkItem',
};

export function displayMatterValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value);
}

interface ComparisonRow {
  field: MatterUpdateProposalField;
  values: ProposedFieldValues;
}

export function proposalRows(proposal: MatterUpdateProposal): ComparisonRow[] {
  return Object.entries(proposal.proposedChanges).map(([field, values]) => ({
    field: field as MatterUpdateProposalField,
    values: values as ProposedFieldValues,
  }));
}

function parseFinalValue(field: MatterUpdateProposalField, value: string): unknown {
  if (field !== 'newWorkItems') return value.trim();
  try {
    const parsed: unknown = JSON.parse(value);
    if (!Array.isArray(parsed)) throw new Error('新增 WorkItem 必须是 JSON 数组');
    return parsed;
  } catch (error) {
    throw new Error(error instanceof Error ? error.message : '新增 WorkItem JSON 无效');
  }
}

export function buildProposalFieldDecisions(
  proposal: MatterUpdateProposal,
  decisions: Partial<Record<MatterUpdateProposalField, MatterFieldDecision>>,
  finalValues: Partial<Record<MatterUpdateProposalField, string>>,
): Array<{
  fieldName: MatterUpdateProposalField;
  decision: MatterFieldDecision;
  finalValue: unknown;
}> {
  const rows = proposalRows(proposal);
  const missing = rows.filter(({ field }) => !decisions[field]);
  if (missing.length) {
    throw new Error(
      `请逐项决定：${missing.map(({ field }) => matterFieldLabels[field]).join('、')}`,
    );
  }
  return rows.map(({ field }) => ({
    fieldName: field,
    decision: decisions[field]!,
    finalValue: decisions[field] === 'approve'
      ? parseFinalValue(field, finalValues[field] ?? '')
      : null,
  }));
}

export default function MatterUpdateComparison({
  proposal,
  decisions,
  finalValues,
  onDecisionChange,
  onFinalValueChange,
}: {
  proposal: MatterUpdateProposal;
  decisions: Partial<Record<MatterUpdateProposalField, MatterFieldDecision>>;
  finalValues: Partial<Record<MatterUpdateProposalField, string>>;
  onDecisionChange: (field: MatterUpdateProposalField, decision: MatterFieldDecision) => void;
  onFinalValueChange: (field: MatterUpdateProposalField, value: string) => void;
}) {
  const pending = proposal.status === 'pending';
  const rows = proposalRows(proposal);

  return (
    <Table
      rowKey="field"
      pagination={false}
      scroll={{ x: 1100 }}
      dataSource={rows}
      columns={[
        {
          title: '字段', dataIndex: 'field', width: 130,
          render: (field: MatterUpdateProposalField) => <Text strong>{matterFieldLabels[field]}</Text>,
        },
        {
          title: '当前值', width: 190,
          render: (_value, row) => <pre className="agent-json">{displayMatterValue(row.values.currentValue)}</pre>,
        },
        {
          title: '消息提取值', width: 190,
          render: (_value, row) => <pre className="agent-json">{displayMatterValue(row.values.messageExtractedValue)}</pre>,
        },
        {
          title: 'AI 建议值', width: 190,
          render: (_value, row) => <pre className="agent-json">{displayMatterValue(row.values.aiSuggestedValue)}</pre>,
        },
        {
          title: '法务最终值', width: 240,
          render: (_value, row) => pending ? (
            <Input.TextArea
              aria-label={`${matterFieldLabels[row.field]} 法务最终值`}
              rows={row.field === 'newWorkItems' ? 8 : 3}
              value={finalValues[row.field] ?? ''}
              disabled={decisions[row.field] !== 'approve'}
              onChange={(event) => onFinalValueChange(row.field, event.target.value)}
            />
          ) : (
            <pre className="agent-json">{displayMatterValue(proposal.finalChanges[row.field])}</pre>
          ),
        },
        {
          title: '逐项决定', width: 140, fixed: 'right' as const,
          render: (_value, row) => pending ? (
            <Radio.Group
              aria-label={`${matterFieldLabels[row.field]} 逐项决定`}
              value={decisions[row.field]}
              onChange={(event) => onDecisionChange(row.field, event.target.value as MatterFieldDecision)}
              optionType="button"
              buttonStyle="solid"
              size="small"
            >
              <Radio.Button value="approve">批准</Radio.Button>
              <Radio.Button value="reject">拒绝</Radio.Button>
            </Radio.Group>
          ) : (
            <Tag>{proposal.fieldDecisions.find((value) => value.fieldName === row.field)?.decision ?? '—'}</Tag>
          ),
        },
      ]}
    />
  );
}
