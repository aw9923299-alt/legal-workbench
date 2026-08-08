import { ArrowLeftOutlined, CheckOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Input,
  Space,
  Tag,
  Typography,
  message,
} from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import MatterUpdateComparison, {
  buildProposalFieldDecisions,
  displayMatterValue,
  proposalRows,
  type MatterFieldDecision,
} from '../components/MatterUpdateComparison';
import { QueryState } from '../components/QueryState';
import {
  ApiError,
  clearMutationContext,
  getOrCreateMutationContext,
  isDefinitiveMutationFailure,
  legalApi,
} from '../services/api';
import type { MatterUpdateProposalField } from '../types/api';

const { Title, Text } = Typography;

export default function MatterUpdateProposalPage() {
  const { proposalId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [decisions, setDecisions] = useState<Partial<Record<MatterUpdateProposalField, MatterFieldDecision>>>({});
  const [finalValues, setFinalValues] = useState<Partial<Record<MatterUpdateProposalField, string>>>({});
  const [rejectionReason, setRejectionReason] = useState('');
  const [conflict, setConflict] = useState<string>();

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

  const rows = useMemo(() => proposal.data ? proposalRows(proposal.data) : [], [proposal.data]);

  useEffect(() => {
    if (proposal.data?.status !== 'pending') return;
    setDecisions({});
    setFinalValues(Object.fromEntries(rows.map(({ field, values }) => [
      field,
      displayMatterValue(
        values.aiSuggestedValue ?? values.messageExtractedValue ?? values.currentValue,
      ),
    ])));
    setRejectionReason('');
    setConflict(undefined);
    // A refetch of the same Proposal must not reset legal's draft after a 409.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proposal.data?.id]);

  const review = useMutation({
    mutationFn: async () => {
      if (!proposal.data) throw new Error('更新建议尚未加载');
      const approvedCount = rows.filter(({ field }) => decisions[field] === 'approve').length;
      if (!approvedCount && !rejectionReason.trim()) throw new Error('全部拒绝时必须填写拒绝原因');
      const payload = {
        proposalVersion: proposal.data.version,
        matterVersion: proposal.data.baseMatterVersion,
        decisions: buildProposalFieldDecisions(proposal.data, decisions, finalValues),
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
      setConflict(undefined);
      message.success(result.status === 'rejected' ? '更新建议已拒绝，Matter 未修改' : '法务最终值已写入 Matter');
      void queryClient.invalidateQueries({ queryKey: ['matter-update-proposal', proposalId] });
      void queryClient.invalidateQueries({ queryKey: ['matter', result.matterId] });
      void queryClient.invalidateQueries({ queryKey: ['matters'] });
      void queryClient.invalidateQueries({ queryKey: ['dashboard', 'today'] });
    },
    onError: async (error) => {
      if (!(error instanceof ApiError) || error.status !== 409) return;
      setConflict('Matter 已在建议创建后发生变化。系统已刷新当前版本，并保留你的逐字段决定和法务最终值草稿。');
      await Promise.all([proposal.refetch(), matter.refetch()]);
    },
  });

  const error = proposal.error ?? matter.error;
  const mutationError = review.error;
  const apiError = mutationError instanceof ApiError ? mutationError : undefined;
  const pending = proposal.data?.status === 'pending';
  const versionConflict = Boolean(
    pending && proposal.data && matter.data
    && matter.data.version !== proposal.data.baseMatterVersion,
  );

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
          {versionConflict && <Alert type="error" showIcon message="Matter 已发生变化" description="当前建议不能直接批准。后端也会返回版本冲突，绝不会静默覆盖新版本。" />}
        </Card>
        <Card title="当前值 / 消息提取值 / AI 建议值 / 法务最终值" variant="borderless" style={{ marginTop: 16 }}>
          <MatterUpdateComparison
            proposal={proposal.data}
            decisions={decisions}
            finalValues={finalValues}
            onDecisionChange={(field, decision) => setDecisions((current) => ({
              ...current, [field]: decision,
            }))}
            onFinalValueChange={(field, value) => setFinalValues((current) => ({
              ...current, [field]: value,
            }))}
          />
          {pending && <>
            <Input.TextArea style={{ marginTop: 16 }} rows={3} value={rejectionReason} onChange={(event) => setRejectionReason(event.target.value)} placeholder="拒绝或部分拒绝原因（全部拒绝时必填）" />
            {conflict && <Alert
              style={{ marginTop: 16 }}
              type="error"
              showIcon
              message="版本冲突，未修改 Matter"
              description={conflict}
              action={<Button onClick={() => navigate(`/candidates/${proposal.data!.candidateId}`)}>返回 Candidate</Button>}
            />}
            {mutationError && <Alert style={{ marginTop: 16 }} type="error" showIcon message={mutationError instanceof Error ? mutationError.message : '审核失败'} description={apiError && <span>错误码：{apiError.code ?? 'UNKNOWN'} · Correlation ID：{apiError.correlationId ?? 'unknown'}</span>} />}
            <Space style={{ marginTop: 16 }}>
              <Button type="primary" icon={<CheckOutlined />} loading={review.isPending} disabled={versionConflict} onClick={() => review.mutate()}>提交逐项审核</Button>
              <Text type="secondary">只有批准字段会在一个数据库事务中落地。</Text>
            </Space>
          </>}
        </Card>
      </>}
    </QueryState>
  </div>;
}
