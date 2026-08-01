import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Progress,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  clearMutationContext,
  getOrCreateMutationContext,
  isDefinitiveMutationFailure,
  legalApi,
  type ConfirmCandidateInput,
} from '../services/api';
import {
  candidateStatusLabels,
  categoryLabels,
  displayValue,
  priorityLabels,
  riskLabels,
} from '../services/apiLabels';
import type { MatterCategory, MessageAnalysis, MessageCandidate, MessageJudgementResult, Priority } from '../types/api';

const { Title, Text, Paragraph } = Typography;

interface ConfirmFormValues {
  title: string;
  primaryCategory: MatterCategory;
  ownerId: string;
  legalRisk: 'critical' | 'high' | 'medium' | 'low' | 'pending';
  businessImpact: 'company' | 'department' | 'project' | 'general';
  summary?: string;
  objective?: string;
  workItemTitle: string;
  workItemOwnerId: string;
  priority: Priority;
  nextAction: string;
  estimatedMinutes?: number;
}

export default function InboxPage({ onMatterCreated, onOpenAgentRun }: { onMatterCreated?: (matterId: string) => void; onOpenAgentRun?: (runId: string) => void }) {
  const [items, setItems] = useState<MessageCandidate[]>([]);
  const [analyses, setAnalyses] = useState<Record<string, MessageAnalysis>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [active, setActive] = useState<MessageCandidate>();
  const [submitting, setSubmitting] = useState(false);
  const [retryingId, setRetryingId] = useState<string>();
  const [form] = Form.useForm<ConfirmFormValues>();

  const load = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const candidates = await legalApi.listCandidates();
      setItems(candidates);
      const loaded = await Promise.all(candidates.map(async (candidate) => {
        if (!candidate.feishuMessageId) return null;
        try {
          return [candidate.id, await legalApi.getMessageAnalysis(candidate.feishuMessageId)] as const;
        } catch {
          return null;
        }
      }));
      setAnalyses(Object.fromEntries(loaded.filter((value): value is readonly [string, MessageAnalysis] => value !== null)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '加载候选消息失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const retryAnalysis = async (candidate: MessageCandidate) => {
    if (!candidate.feishuMessageId) return;
    setRetryingId(candidate.id);
    const actionKey = `retry-analysis:${candidate.feishuMessageId}`;
    const mutation = getOrCreateMutationContext(actionKey, { forceNewRun: true });
    try {
      await legalApi.retryMessageAnalysis(candidate.feishuMessageId, mutation);
      clearMutationContext(actionKey);
      message.success('已提交重新分析，原 AgentRun 将保留');
      await load();
    } catch (reason) {
      if (isDefinitiveMutationFailure(reason)) clearMutationContext(actionKey);
      message.error(reason instanceof Error ? reason.message : '重新分析失败');
    } finally {
      setRetryingId(undefined);
    }
  };

  const openConfirm = (candidate: MessageCandidate) => {
    const proposedCategory = candidate.categoryProposals.find(
      (value) => typeof value.category === 'string',
    )?.category as MatterCategory | undefined;
    form.setFieldsValue({
      title: candidate.titleProposal ?? '待确认法务事项',
      primaryCategory: proposedCategory ?? 'general_consultation',
      ownerId: 'local-legal-user',
      legalRisk: 'pending',
      businessImpact: 'general',
      summary: candidate.evidenceRefs.join('\n'),
      workItemTitle: candidate.titleProposal ?? '核实需求并形成处理意见',
      workItemOwnerId: 'local-legal-user',
      priority: 'medium',
      nextAction: '核实事实、材料和完成时间',
    });
    setActive(candidate);
  };

  const confirm = async () => {
    if (!active) return;
    const values = await form.validateFields();
    const payload: ConfirmCandidateInput = {
      candidateVersion: active.version,
      title: values.title,
      primaryCategory: values.primaryCategory,
      secondaryCategories: [],
      ownerId: values.ownerId,
      requesterIds: [],
      legalRisk: values.legalRisk,
      businessImpact: values.businessImpact,
      confidentiality: 'internal',
      summary: values.summary,
      objective: values.objective,
      initialWorkItems: [{
        title: values.workItemTitle,
        ownerId: values.workItemOwnerId,
        priority: values.priority,
        prioritySource: 'legal_confirmed',
        nextAction: values.nextAction,
        priorityReasons: ['法务在工作台确认'],
        estimatedMinutes: values.estimatedMinutes,
      }],
    };
    setSubmitting(true);
    const actionKey = `confirm-candidate:${active.id}`;
    const mutation = getOrCreateMutationContext(actionKey, payload);
    try {
      const result = await legalApi.confirmCandidate(active.id, payload, mutation);
      clearMutationContext(actionKey);
      message.success(`已创建事项 ${result.matterNumber}`);
      setActive(undefined);
      form.resetFields();
      await load();
      onMatterCreated?.(result.matterId);
    } catch (reason) {
      if (isDefinitiveMutationFailure(reason)) clearMutationContext(actionKey);
      message.error(reason instanceof Error ? reason.message : '创建事项失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="page">
      <div className="page-title-row">
        <div>
          <span className="eyebrow">HUMAN-IN-THE-LOOP</span>
          <Title level={2}>AI 收件箱</Title>
          <Text type="secondary">候选消息先由法务确认，再创建正式事项和行动任务。</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
      </div>

      {error && <Alert type="error" showIcon message={error} action={<Button onClick={() => void load()}>重试</Button>} />}
      <Spin spinning={loading}>
        <div className="inbox-stream">
          {!loading && items.length === 0 && <Empty description="暂无待确认候选消息" />}
          {items.map((item) => (
            <CandidateCard
              key={item.id}
              item={item}
              analysis={analyses[item.id]}
              onConfirm={() => openConfirm(item)}
              onRetry={() => void retryAnalysis(item)}
              retrying={retryingId === item.id}
              onOpenAgentRun={onOpenAgentRun}
            />
          ))}
        </div>
      </Spin>

      <Modal
        open={Boolean(active)}
        title="确认并创建法务事项"
        width={760}
        okText="创建事项"
        cancelText="取消"
        confirmLoading={submitting}
        onCancel={() => {
          if (active) clearMutationContext(`confirm-candidate:${active.id}`);
          setActive(undefined);
        }}
        onOk={() => void confirm()}
      >
        <Alert
          type="info"
          showIcon
          message="该操作将在同一事务中创建 LegalMatter 和首个 WorkItem，并记录人工确认。"
          style={{ marginBottom: 16 }}
        />
        <Form form={form} layout="vertical">
          <Form.Item name="title" label="事项标题" rules={[{ required: true }]}><Input /></Form.Item>
          <Space align="start" wrap>
            <Form.Item name="primaryCategory" label="主分类" rules={[{ required: true }]}>
              <Select style={{ width: 180 }} options={Object.entries(categoryLabels).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
            <Form.Item name="legalRisk" label="法律风险" rules={[{ required: true }]}>
              <Select style={{ width: 140 }} options={Object.entries(riskLabels).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
            <Form.Item name="businessImpact" label="业务影响" rules={[{ required: true }]}>
              <Select style={{ width: 140 }} options={[
                { value: 'company', label: '公司级' }, { value: 'department', label: '部门级' },
                { value: 'project', label: '项目级' }, { value: 'general', label: '一般' },
              ]} />
            </Form.Item>
            <Form.Item name="ownerId" label="事项负责人" rules={[{ required: true }]}><Input style={{ width: 180 }} /></Form.Item>
          </Space>
          <Form.Item name="summary" label="事项背景"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="objective" label="处理目标"><Input.TextArea rows={2} /></Form.Item>
          <Title level={5}>首个行动任务</Title>
          <Form.Item name="workItemTitle" label="任务名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Space align="start" wrap>
            <Form.Item name="workItemOwnerId" label="负责人" rules={[{ required: true }]}><Input style={{ width: 180 }} /></Form.Item>
            <Form.Item name="priority" label="优先级" rules={[{ required: true }]}>
              <Select style={{ width: 140 }} options={Object.entries(priorityLabels).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
            <Form.Item name="estimatedMinutes" label="预计分钟"><InputNumber min={1} /></Form.Item>
          </Space>
          <Form.Item name="nextAction" label="下一步行动" rules={[{ required: true }]}><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

function CandidateCard({ item, analysis, onConfirm, onRetry, retrying, onOpenAgentRun }: {
  item: MessageCandidate;
  analysis?: MessageAnalysis;
  onConfirm: () => void;
  onRetry: () => void;
  retrying: boolean;
  onOpenAgentRun?: (runId: string) => void;
}) {
  const category = useMemo(() => {
    const value = item.categoryProposals.find((proposal) => typeof proposal.category === 'string')?.category;
    return typeof value === 'string' ? categoryLabels[value] ?? value : '待分类';
  }, [item.categoryProposals]);
  const judgement = (analysis?.analysisResult ?? item.analysisPayload) as Partial<MessageJudgementResult>;
  const run = analysis?.agentRun;

  return (
    <Card className="inbox-card" bordered={false}>
      <div className="inbox-card-grid">
        <div className="inbox-card-main">
          <Space wrap>
            <Tag color="blue">{candidateStatusLabels[item.status] ?? item.status}</Tag>
            <Tag>{category}</Tag>
            <Tag>{item.messageRole}</Tag>
            <Tag color={item.legalRelevance === 'relevant' ? 'green' : 'gold'}>{item.legalRelevance}</Tag>
            {item.requiresManualReview && <Tag color="orange">必须人工确认</Tag>}
          </Space>
          <Title level={4}>{item.titleProposal ?? '未命名候选事项'}</Title>
          <Paragraph type="secondary">建议动作：{item.recommendedAction}</Paragraph>
          <div className="analysis-meta">
            <span>飞书来源：{analysis?.message.messageId ?? item.feishuMessageId ?? '未关联'}</span>
            <span>分析状态：{analysis?.messageStatus ?? run?.status ?? 'completed'}</span>
            <span>Agent：{run ? `${run.agentKey} v${run.agentVersion}` : 'message_judgement'}</span>
          </div>
          <AnalysisSection title="研判理由" values={judgement.reasons} />
          <AnalysisSection title="已确认事实" values={judgement.confirmedFacts?.map((fact) => `${fact.statement}（来源 ${fact.sourceMessageId}）`)} />
          <AnalysisSection title="推断事实" values={judgement.inferredFacts?.map((fact) => `${fact.statement}（${fact.basis}，${Math.round(fact.confidence * 100)}%）`)} />
          <AnalysisSection title="截止时间候选" values={judgement.deadlineCandidates?.map((deadline) => `${deadline.rawText} → ${deadline.resolvedAt ?? '待确认'}（${deadline.deadlineType}）`)} />
          <AnalysisSection title="缺失信息" values={judgement.missingInformation} />
          {item.evidenceRefs.length > 0 && <AnalysisSection title="证据消息" values={item.evidenceRefs.map(displayValue)} />}
        </div>
        <div className="confidence-panel">
          <Text type="secondary">置信度</Text>
          <Progress type="circle" percent={Math.round(item.confidence * 100)} size={68} />
        </div>
      </div>
      <div className="inbox-card-actions">
        <Button type="primary" onClick={onConfirm}>确认并创建事项</Button>
        {item.feishuMessageId && <Button loading={retrying} onClick={onRetry}>重新分析</Button>}
        {item.agentRunId && <Button type="link" onClick={() => onOpenAgentRun?.(item.agentRunId!)}>AgentRun 详情</Button>}
        <Text type="secondary">版本 {item.version} · {item.id}</Text>
      </div>
    </Card>
  );
}

function AnalysisSection({ title, values }: { title: string; values?: string[] }) {
  if (!values?.length) return null;
  return <div className="rationale-box"><strong>{title}</strong>{values.map((value, index) => <span key={`${title}-${index}`}>· {value}</span>)}</div>;
}
