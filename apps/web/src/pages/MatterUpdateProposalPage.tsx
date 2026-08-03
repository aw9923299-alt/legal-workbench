import { ArrowLeftOutlined, CheckOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Input,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { QueryState } from '../components/QueryState';
import {
  ApiError,
  clearMutationContext,
  getOrCreateMutationContext,
  isDefinitiveMutationFailure,
  legalApi,
} from '../services/api';
import type {
  MatterUpdateProposalField,
  ProposedFieldValues,
} from '../types/api';

const { Title, Text } = Typography;

const fieldLabels: Record<MatterUpdateProposalField, string> = {
  title: '标题',
  category: '分类',
  priority: '优先级',
  deadline: '截止时间',
  owner: '负责人',
  currentStatus: '当前状态',
  nextAction: '下一步行动',
  newWorkItems: '新增 WorkItem',
};

type ReviewDecision = 'approve' | 'reject';

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value);
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

export default function MatterUpdateProposalPage() {
  const { proposalId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [decisions, setDecisions] = useState<Partial<Record<MatterUpdateProposalField, ReviewDecision>>>({});
  const [finalValues, setFinalValues] = useState<Partial<Record<MatterUpdateProposalField, string>>>({});
  const [rejectionReason, setRejectionReason] = useState('');

  const proposal = useQuery({
    queryKey: ['matter-update-proposal', proposalId],
    queryFn: () => legalApi.getMatterUpdateProposal(proposalId),
    enabled: Boolean(proposalId),
  });
  const matter = useQuery({
    queryKey: ['matter', proposal.data?.matterId],
    queryFn: () => legalApi.getMatter(proposal.data!.matterId),
    enabled: Boolean(proposal.data?.matterId),
  });

  const rows = useMemo(() => Object.entries(proposal.data?.proposedChanges ?? {}).map(
    ([field, values]) => ({
      field: field as MatterUpdateProposalField,
      values: values as ProposedFieldValues,
    }),
  ), [proposal.data?.proposedChanges]);

  useEffect(() => {
    if (proposal.data?.status !== 'pending') return;
    setFinalValues(Object.fromEntries(rows.map(({ field, values }) => [
      field,
      displayValue(values.aiSuggestedValue ?? values.messageExtractedValue ?? values.currentValue),
    ])));
  }, [proposal.data?.id, proposal.data?.status, rows]);

  const review = useMutation({
    mutationFn: async () => {
      if (!proposal.data) throw new Error('更新建议尚未加载');
      const missing = rows.filter(({ field }) => !decisions[field]);
      if (missing.length) throw new Error(`请逐项决定：${missing.map(({ field }) => fieldLabels[field]).join('、')}`);
      const approvedCount = rows.filter(({ field }) => decisions[field] === 'approve').length;
      if (!approvedCount && !rejectionReason.trim()) throw new Error('全部拒绝时必须填写拒绝原因');
      const payload = {
        proposalVersion: proposal.data.version,
        matterVersion: proposal.data.baseMatterVersion,
        decisions: rows.map(({ field }) => ({
          fieldName: field,
          decision: decisions[field]!,
          finalValue: decisions[field] === 'approve'
            ? parseFinalValue(field, finalValues[field] ?? '')
            : null,
        })),
        rejectionReason: rejectionReason.trim() || undefined,
      };
      const key = `review-matter-update-proposal:${proposal.data.id}`;
      const context = getOrCreateMutationContext(key, payload);
      try {
        const result = await legalApi.reviewMatterUpdateProposal(proposal.data.id, payload, context);
        clearMutationContext(key);
        return result;
      } catch (error) {
        if (isDefinitiveMutationFailure(error)) clearMutationContext(key);
        throw error;
      }
    },
    onSuccess: (result) => {
      message.success(result.status === 'rejected' ? '更新建议已拒绝，Matter 未修改' : '法务最终值已写入 Matter');
      void queryClient.invalidateQueries({ queryKey: ['matter-update-proposal', proposalId] });
      void queryClient.invalidateQueries({ queryKey: ['matter', result.matterId] });
      void queryClient.invalidateQueries({ queryKey: ['matters'] });
    },
  });

  const error = proposal.error ?? matter.error;
  const mutationError = review.error;
  const apiError = mutationError instanceof ApiError ? mutationError : undefined;
  const pending = proposal.data?.status === 'pending';

  return <div className="page">
    <Space className="page-title-row" align="start">
      <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>返回</Button>
      <div><span className="eyebrow">HUMAN REVIEW GATE</span><Title level={2}>Matter 更新建议审核</Title></div>
    </Space>
    <QueryState loading={proposal.isLoading || matter.isLoading} error={error} onRetry={() => { void proposal.refetch(); void matter.refetch(); }}>
      {proposal.data && matter.data && <>
        <Card variant="borderless">
          <Descriptions column={{ xs: 1, md: 2 }}>
            <Descriptions.Item label="Matter"><Button type="link" onClick={() => navigate(`/matters/${matter.data!.id}`)}>{matter.data.matterNumber} · {matter.data.title}</Button></Descriptions.Item>
            <Descriptions.Item label="状态"><Tag color={pending ? 'gold' : proposal.data.status.includes('approved') ? 'green' : 'default'}>{proposal.data.status}</Tag></Descriptions.Item>
            <Descriptions.Item label="基准 Matter 版本">v{proposal.data.baseMatterVersion}</Descriptions.Item>
            <Descriptions.Item label="当前 Matter 版本">v{matter.data.version}</Descriptions.Item>
            <Descriptions.Item label="建议理由" span={2}>{proposal.data.reason}</Descriptions.Item>
          </Descriptions>
          {matter.data.version !== proposal.data.baseMatterVersion && pending && <Alert type="error" showIcon message="Matter 已发生变化" description="当前建议不能直接批准。后端也会返回版本冲突，绝不会静默覆盖新版本。" />}
        </Card>
        <Card title="当前值 / 消息提取值 / AI 建议值 / 法务最终值" variant="borderless" style={{ marginTop: 16 }}>
          <Table
            rowKey="field"
            pagination={false}
            scroll={{ x: 1100 }}
            dataSource={rows}
            columns={[
              { title: '字段', dataIndex: 'field', width: 130, render: (field: MatterUpdateProposalField) => <Text strong>{fieldLabels[field]}</Text> },
              { title: '当前值', width: 190, render: (_value, row) => <pre className="agent-json">{displayValue(row.values.currentValue)}</pre> },
              { title: '消息提取值', width: 190, render: (_value, row) => <pre className="agent-json">{displayValue(row.values.messageExtractedValue)}</pre> },
              { title: 'AI 建议值', width: 190, render: (_value, row) => <pre className="agent-json">{displayValue(row.values.aiSuggestedValue)}</pre> },
              { title: '法务最终值', width: 240, render: (_value, row) => pending ? <Input.TextArea rows={row.field === 'newWorkItems' ? 8 : 3} value={finalValues[row.field] ?? ''} disabled={decisions[row.field] !== 'approve'} onChange={(event) => setFinalValues((current) => ({ ...current, [row.field]: event.target.value }))} /> : <pre className="agent-json">{displayValue(proposal.data!.finalChanges[row.field])}</pre> },
              { title: '逐项决定', width: 140, fixed: 'right' as const, render: (_value, row) => pending ? <Select style={{ width: 120 }} placeholder="请选择" value={decisions[row.field]} onChange={(value) => setDecisions((current) => ({ ...current, [row.field]: value }))} options={[{ value: 'approve', label: '批准' }, { value: 'reject', label: '拒绝' }]} /> : <Tag>{proposal.data!.fieldDecisions.find((value) => value.fieldName === row.field)?.decision ?? '—'}</Tag> },
            ]}
          />
          {pending && <>
            <Input.TextArea style={{ marginTop: 16 }} rows={3} value={rejectionReason} onChange={(event) => setRejectionReason(event.target.value)} placeholder="拒绝或部分拒绝原因（全部拒绝时必填）" />
            {mutationError && <Alert style={{ marginTop: 16 }} type="error" showIcon message={mutationError instanceof Error ? mutationError.message : '审核失败'} description={apiError && <span>错误码：{apiError.code ?? 'UNKNOWN'} · Correlation ID：{apiError.correlationId ?? 'unknown'}</span>} />}
            <Space style={{ marginTop: 16 }}>
              <Button type="primary" icon={<CheckOutlined />} loading={review.isPending} onClick={() => review.mutate()}>提交逐项审核</Button>
              <Text type="secondary">只有批准字段会在一个数据库事务中落地。</Text>
            </Space>
          </>}
        </Card>
      </>}
    </QueryState>
  </div>;
}
