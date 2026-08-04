import {
  App as AntApp,
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
  type FormInstance,
} from 'antd';
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ApiError,
  clearMutationContext,
  getOrCreateMutationContext,
  isDefinitiveMutationFailure,
  legalApi,
  type ConfirmCandidateInput,
} from '../services/api';
import {
  candidateStatusLabels,
  categoryLabels,
  legalRelevanceLabels,
  messageRoleLabels,
  priorityLabels,
  recommendedActionLabels,
  riskLabels,
} from '../services/apiLabels';
import type {
  BusinessImpact,
  MatterCategory,
  MessageAnalysis,
  MessageCandidate,
  MessageJudgementResult,
  Priority,
} from '../types/api';
import StatePanel from '../components/StatePanel';
import { SemanticStatusTag } from '../components/StatusTags';
import DataBoundaryBanner from '../components/DataBoundaryBanner';
import PageHeader from '../components/PageHeader';

const { Title, Text, Paragraph } = Typography;
const analysisBlockingStatuses = new Set(['queued', 'preparing', 'running', 'validating']);
const plannedCompleteAtPattern = /^\d{4}-(0[1-9]|1[0-2])-([0-2]\d|3[01]) ([01]\d|2[0-3]):[0-5]\d$/;

interface RetryFreshnessBarrier {
  previousAgentRunId: string | null;
}

interface CandidateBoundDetail {
  candidateId: string;
  analysis: MessageAnalysis;
}

interface ConfirmFormValues {
  title: string;
  primaryCategory: MatterCategory;
  ownerId: string;
  legalRisk: 'critical' | 'high' | 'medium' | 'low' | 'pending';
  businessImpact: BusinessImpact;
  summary?: string;
  objective?: string;
  workItemTitle: string;
  workItemOwnerId: string;
  priority: Priority;
  nextAction: string;
  estimatedMinutes?: number;
  plannedCompleteAt?: string;
}

export default function InboxPage({ candidateId, onCandidateSelected, onMatterCreated, onOpenAgentRun }: {
  candidateId?: string;
  onCandidateSelected?: (candidateId?: string) => void;
  onMatterCreated?: (matterId: string) => void;
  onOpenAgentRun?: (runId: string) => void;
}) {
  const { message: messageApi, modal: modalApi } = AntApp.useApp();
  const [items, setItems] = useState<MessageCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string>();
  const [forbidden, setForbidden] = useState(false);
  const [selectedId, setSelectedId] = useState<string | undefined>(candidateId);
  const [detailState, setDetailState] = useState<CandidateBoundDetail>();
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string>();
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const [confirmingCandidate, setConfirmingCandidate] = useState<MessageCandidate>();
  const [formDirty, setFormDirty] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [retryingId, setRetryingId] = useState<string>();
  const [retryFreshnessBarriers, setRetryFreshnessBarriers] = useState<Record<string, RetryFreshnessBarrier>>({});
  const detailRequest = useRef(0);
  const requestedCandidateId = useRef(candidateId);
  const confirmTrigger = useRef<HTMLElement | null>(null);
  const restoreConfirmFocus = useRef(false);
  const submitInFlight = useRef(false);
  const [form] = Form.useForm<ConfirmFormValues>();

  const selected = useMemo(
    () => items.find((candidate) => candidate.id === selectedId),
    [items, selectedId],
  );
  const detail = detailState && detailState.candidateId === selectedId ? detailState.analysis : undefined;

  const loadCandidates = useCallback(async () => {
    setLoading(true);
    setListError(undefined);
    setForbidden(false);
    try {
      const candidates = await legalApi.listCandidates();
      setItems(candidates);
      setSelectedId((current) => {
        const requested = requestedCandidateId.current;
        if (requested) return candidates.some((candidate) => candidate.id === requested) ? requested : undefined;
        return candidates.some((candidate) => candidate.id === current) ? current : candidates[0]?.id;
      });
      if (candidates.length === 0) {
        setDetailState(undefined);
        setDetailError(undefined);
      }
    } catch (reason) {
      setItems([]);
      setSelectedId(undefined);
      setDetailState(undefined);
      setForbidden(reason instanceof ApiError && [401, 403].includes(reason.status));
      setListError(reason instanceof Error ? reason.message : '加载候选消息失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    requestedCandidateId.current = candidateId;
    if (candidateId) {
      setSelectedId(items.some((candidate) => candidate.id === candidateId) ? candidateId : undefined);
      setMobileDetailOpen(true);
      return;
    }
    setMobileDetailOpen(false);
    setSelectedId(items[0]?.id);
  }, [candidateId, items]);

  const loadDetail = useCallback(async (candidate: MessageCandidate) => {
    const requestId = detailRequest.current + 1;
    detailRequest.current = requestId;
    setDetailState(undefined);
    setDetailError(undefined);
    if (!candidate.feishuMessageId) {
      setDetailError('当前 Candidate 未关联原始消息，无法核对证据');
      return;
    }
    setDetailLoading(true);
    try {
      const analysis = await legalApi.getMessageAnalysis(candidate.feishuMessageId);
      if (detailRequest.current === requestId) {
        setDetailState({ candidateId: candidate.id, analysis });
      }
    } catch (reason) {
      if (detailRequest.current === requestId) {
        setDetailError(reason instanceof Error ? reason.message : '加载证据详情失败');
      }
    } finally {
      if (detailRequest.current === requestId) setDetailLoading(false);
    }
  }, []);

  useEffect(() => { void loadCandidates(); }, [loadCandidates]);
  useEffect(() => {
    if (selected) void loadDetail(selected);
  }, [selected, loadDetail]);
  useEffect(() => {
    if (!selected || !detail) return;
    const barrier = retryFreshnessBarriers[selected.id];
    const exposedRunId = selected.agentRunId;
    const detailRunStatus = detail.agentRun?.status ?? detail.messageStatus;
    const newFinishedRunIsProven = Boolean(
      barrier
      && exposedRunId
      && exposedRunId !== barrier.previousAgentRunId
      && detailState?.candidateId === selected.id
      && detail.agentRun?.id === exposedRunId
      && !analysisBlockingStatuses.has(detailRunStatus),
    );
    if (!newFinishedRunIsProven) return;
    setRetryFreshnessBarriers((current) => {
      if (current[selected.id] !== barrier) return current;
      const next = { ...current };
      delete next[selected.id];
      return next;
    });
  }, [detail, detailState?.candidateId, retryFreshnessBarriers, selected]);

  const selectCandidate = (candidate: MessageCandidate) => {
    setSelectedId(candidate.id);
    setMobileDetailOpen(true);
    onCandidateSelected?.(candidate.id);
  };

  const returnToQueue = () => {
    setMobileDetailOpen(false);
    onCandidateSelected?.(undefined);
  };

  const retryAnalysis = async (candidate: MessageCandidate) => {
    if (!candidate.feishuMessageId) return;
    const previousAgentRunId = candidate.agentRunId
      ?? detail?.agentRun?.id
      ?? null;
    setRetryingId(candidate.id);
    setDetailState((current) => current?.candidateId === candidate.id
      ? { ...current, analysis: { ...current.analysis, messageStatus: 'queued' } }
      : current);
    const actionKey = `retry-analysis:${candidate.feishuMessageId}`;
    const mutation = getOrCreateMutationContext(actionKey, { forceNewRun: true });
    try {
      await legalApi.retryMessageAnalysis(candidate.feishuMessageId, mutation);
      clearMutationContext(actionKey);
      setRetryFreshnessBarriers((current) => ({
        ...current,
        [candidate.id]: { previousAgentRunId },
      }));
      messageApi.success('已提交重新分析；正式确认保持冻结，等待新结果');
      await loadCandidates();
    } catch (reason) {
      if (isDefinitiveMutationFailure(reason)) {
        clearMutationContext(actionKey);
        setRetryFreshnessBarriers((current) => {
          const next = { ...current };
          delete next[candidate.id];
          return next;
        });
        await loadDetail(candidate);
      } else {
        setRetryFreshnessBarriers((current) => ({
          ...current,
          [candidate.id]: { previousAgentRunId },
        }));
        await loadCandidates();
      }
      messageApi.error(reason instanceof Error ? reason.message : '重新分析失败；结果状态不明，请刷新核对');
    } finally {
      setRetryingId(undefined);
    }
  };

  const openConfirm = (candidate: MessageCandidate) => {
    const proposedCategory = candidate.categoryProposals.find(
      (value) => typeof value.category === 'string',
    )?.category as MatterCategory | undefined;
    const sourceText = detail ? extractMessageText(detail.message.content) : undefined;
    const missingInformation = candidate.analysisPayload.missingInformation ?? [];
    form.resetFields();
    setFormDirty(false);
    form.setFieldsValue({
      title: candidate.titleProposal ?? undefined,
      primaryCategory: proposedCategory ?? 'general_consultation',
      summary: sourceText,
      workItemTitle: candidate.titleProposal ? `处理：${candidate.titleProposal}` : undefined,
      nextAction: missingInformation.length
        ? `补充并核对：${missingInformation.join('、')}`
        : undefined,
    });
    confirmTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setConfirmingCandidate(candidate);
  };

  const closeConfirmImmediately = (shouldRestoreFocus: boolean) => {
    if (confirmingCandidate) clearMutationContext(`confirm-candidate:${confirmingCandidate.id}`);
    restoreConfirmFocus.current = shouldRestoreFocus;
    setConfirmingCandidate(undefined);
    setFormDirty(false);
    form.resetFields();
  };

  const requestCloseConfirm = () => {
    if (submitting) return;
    if (!formDirty) {
      closeConfirmImmediately(true);
      return;
    }
    modalApi.confirm({
      title: '放弃未保存的修改？',
      content: '人工修改尚未提交。放弃后将恢复为 AI 建议值。',
      okText: '放弃修改',
      cancelText: '继续编辑',
      okButtonProps: { danger: true },
      onOk: () => closeConfirmImmediately(true),
    });
  };

  const handleConfirmDrawerOpenChange = (open: boolean) => {
    if (open || !restoreConfirmFocus.current) return;
    restoreConfirmFocus.current = false;
    window.requestAnimationFrame(() => confirmTrigger.current?.focus());
  };

  const confirm = async () => {
    if (!confirmingCandidate || submitInFlight.current) return;
    submitInFlight.current = true;
    setSubmitting(true);
    try {
      let values: ConfirmFormValues;
      try {
        values = await form.validateFields();
      } catch {
        return;
      }
      const plannedCompleteAt = values.plannedCompleteAt
        ? toPlannedCompleteAtIso(values.plannedCompleteAt)
        : undefined;
      if (values.plannedCompleteAt && !plannedCompleteAt) {
        form.setFields([{ name: 'plannedCompleteAt', errors: ['请按 YYYY-MM-DD HH:mm 填写有效时间'] }]);
        return;
      }
      const payload: ConfirmCandidateInput = {
        candidateVersion: confirmingCandidate.version,
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
          plannedCompleteAt,
        }],
      };
      const actionKey = `confirm-candidate:${confirmingCandidate.id}`;
      const mutation = getOrCreateMutationContext(actionKey, payload);
      const result = await legalApi.confirmCandidate(confirmingCandidate.id, payload, mutation);
      clearMutationContext(actionKey);
      messageApi.success(`已创建事项 ${result.matterNumber}`);
      closeConfirmImmediately(false);
      onMatterCreated?.(result.matterId);
    } catch (reason) {
      if (isDefinitiveMutationFailure(reason) && confirmingCandidate) {
        clearMutationContext(`confirm-candidate:${confirmingCandidate.id}`);
      }
      messageApi.error(reason instanceof Error ? reason.message : '创建事项失败');
    } finally {
      submitInFlight.current = false;
      setSubmitting(false);
    }
  };

  return (
    <div className="page inbox-page">
      <PageHeader
        className="inbox-page-title"
        eyebrow="人工证据核对"
        title="待确认消息"
        description="先核对原始消息和证据范围，再决定是否创建正式事项。"
        secondaryActions={[<Button key="refresh" icon={<ReloadOutlined />} onClick={() => void loadCandidates()}>刷新</Button>]}
      />
      <DataBoundaryBanner
        variant="api"
        title="候选与证据由服务接口提供"
        description="界面不声称实时同步；附件正文、缺失上下文和人工确认状态仍需逐项核对。"
      />

      {loading ? (
        <StatePanel
          className="inbox-loading"
          variant="loading"
          title="待确认消息加载中"
          description="正在从服务接口请求候选消息；加载完成前不显示业务摘要。"
        />
      ) : listError ? (
        <Alert
          className="inbox-list-alert"
          type={forbidden ? 'warning' : 'error'}
          showIcon
          message={forbidden ? '无权查看待确认消息' : '候选列表加载失败'}
          description={listError}
          action={<Button onClick={() => void loadCandidates()}>重试</Button>}
        />
      ) : items.length === 0 ? (
        <Empty className="inbox-empty" description="暂无待确认消息" />
      ) : (
        <div className={`inbox-workspace${mobileDetailOpen ? ' inbox-mobile-detail-open' : ''}`}>
          <aside className="inbox-queue" aria-label="待确认消息队列">
            <div className="inbox-queue-heading">
              <strong>待人工确认</strong>
              <Text type="secondary">{items.length} 条 Candidate</Text>
            </div>
            <div className="inbox-queue-list">
              {items.map((candidate) => (
                <CandidateQueueItem
                  key={candidate.id}
                  candidate={candidate}
                  analysis={candidate.id === selectedId ? detail : undefined}
                  selected={candidate.id === selectedId}
                  onSelect={() => selectCandidate(candidate)}
                />
              ))}
            </div>
            <Paragraph className="inbox-coverage-note" type="secondary">
              当前队列仅覆盖已生成 Candidate 的消息；未证明覆盖无 Candidate 的失败或死信消息。
            </Paragraph>
          </aside>

          <main className="inbox-detail">
            <Button className="inbox-mobile-back" icon={<ArrowLeftOutlined />} onClick={returnToQueue}>返回消息队列</Button>
            {selected && (
              <CandidateDetail
                candidate={selected}
                analysis={detail}
                loading={detailLoading}
                error={detailError}
                retrying={retryingId === selected.id}
                retryAwaitingFreshness={Boolean(retryFreshnessBarriers[selected.id])}
                onRetryDetail={() => void loadDetail(selected)}
                onRetryAnalysis={() => void retryAnalysis(selected)}
                onConfirm={() => openConfirm(selected)}
                onOpenAgentRun={onOpenAgentRun}
              />
            )}
          </main>
        </div>
      )}

      <ConfirmDrawer
        candidate={confirmingCandidate}
        analysis={detail}
        form={form}
        submitting={submitting}
        onCancel={requestCloseConfirm}
        onConfirm={() => void confirm()}
        onValuesChange={() => setFormDirty(true)}
        onOpenChange={handleConfirmDrawerOpenChange}
      />
    </div>
  );
}

function CandidateQueueItem({ candidate, analysis, selected, onSelect }: {
  candidate: MessageCandidate;
  analysis?: MessageAnalysis;
  selected: boolean;
  onSelect: () => void;
}) {
  const judgement = candidate.analysisPayload as Partial<MessageJudgementResult>;
  const missingCount = judgement.missingInformation?.length ?? 0;
  const sourceLine = analysis
    ? `${analysis.message.createTime ?? '时间未提供'} · ${analysis.message.senderId ?? '发送人未提供'}`
    : '选择后加载发送人和时间';

  return (
    <button
      className={`inbox-queue-item${selected ? ' selected' : ''}`}
      aria-pressed={selected}
      aria-label={`建议：${candidate.titleProposal ?? '未命名候选'}，${candidateStatusLabels[candidate.status] ?? candidate.status}`}
      onClick={onSelect}
    >
      <span className="inbox-queue-kicker">建议 · {recommendedActionLabels[candidate.recommendedAction] ?? candidate.recommendedAction}</span>
      <strong>{candidate.titleProposal ?? '未命名候选'}</strong>
      <small>{sourceLine}</small>
      <span className="inbox-queue-meta">
        <Tag color="processing">{candidateStatusLabels[candidate.status] ?? candidate.status}</Tag>
        <span>缺失信息 {missingCount} 项</span>
      </span>
    </button>
  );
}

function CandidateDetail({ candidate, analysis, loading, error, retrying, retryAwaitingFreshness, onRetryDetail, onRetryAnalysis, onConfirm, onOpenAgentRun }: {
  candidate: MessageCandidate;
  analysis?: MessageAnalysis;
  loading: boolean;
  error?: string;
  retrying: boolean;
  retryAwaitingFreshness: boolean;
  onRetryDetail: () => void;
  onRetryAnalysis: () => void;
  onConfirm: () => void;
  onOpenAgentRun?: (runId: string) => void;
}) {
  if (loading) return <div className="inbox-detail-loading" aria-label="消息证据加载中"><Skeleton active paragraph={{ rows: 10 }} /></div>;

  const judgement = (analysis?.analysisResult ?? candidate.analysisPayload) as Partial<MessageJudgementResult>;
  const runStatus = analysis?.agentRun?.status ?? analysis?.messageStatus;
  const busy = retrying || retryAwaitingFreshness || Boolean(runStatus && analysisBlockingStatuses.has(runStatus));
  const detailAvailable = Boolean(analysis && analysis.analysisResult && !error);
  const canConfirmCreate = candidate.recommendedAction === 'create_matter'
    && candidate.status === 'pending_confirmation'
    && detailAvailable
    && !busy;
  const category = candidate.categoryProposals.find((proposal) => typeof proposal.category === 'string')?.category;

  return (
    <Card className="inbox-detail-surface" variant="borderless">
      <div className="inbox-detail-header">
        <div>
          <span className="eyebrow">当前 Candidate</span>
          <Title level={3}>{candidate.titleProposal ?? '未命名候选事项'}</Title>
        </div>
        <Space wrap>
          <SemanticStatusTag kind="api">由服务接口提供 · 不代表实时同步</SemanticStatusTag>
          <Tag>{candidateStatusLabels[candidate.status] ?? candidate.status}</Tag>
          <Tag color="processing">建议：{recommendedActionLabels[candidate.recommendedAction] ?? candidate.recommendedAction}</Tag>
        </Space>
      </div>

      {error && (
        <Alert
          className="inbox-detail-alert"
          type="error"
          showIcon
          message="证据详情加载失败"
          description={error}
          action={<Button onClick={onRetryDetail}>重试详情</Button>}
        />
      )}
      {retryAwaitingFreshness ? (
        <Alert
          className="inbox-detail-alert"
          type="warning"
          showIcon
          message="重新分析已提交，等待 Candidate 暴露新的 AgentRun"
          description="当前接口仍不能证明结果来自本次重试；正式确认保持冻结，请刷新核对。"
        />
      ) : busy && <Alert className="inbox-detail-alert" type="warning" showIcon message="正在分析，正式确认已冻结" description="旧结果仅供查看，需等待最新 AgentRun 完成并重新加载证据。" />}

      {analysis && (
        <>
          <section className="inbox-evidence-section" aria-labelledby="source-message-title">
            <SectionHeading id="source-message-title" eyebrow="来源证据" title="原始消息" />
            <Descriptions
              size="small"
              column={{ xs: 1, sm: 2 }}
              items={[
                { key: 'sender', label: '发送人 ID', children: analysis.message.senderId ?? '当前接口未提供' },
                { key: 'time', label: '发送时间', children: analysis.message.createTime ?? '当前接口未提供' },
                { key: 'type', label: '消息类型', children: analysis.message.messageType },
                { key: 'chat', label: '群聊名称', children: '当前接口未提供' },
              ]}
            />
            <div className="inbox-source-copy">
              <Text type="secondary">消息正文</Text>
              <Paragraph>{extractMessageText(analysis.message.content) ?? '当前接口未返回可读正文'}</Paragraph>
            </div>
            {!extractMessageText(analysis.message.content) && (
              <Collapse ghost size="small" items={[{ key: 'content', label: '查看受控结构化内容', children: <pre className="inbox-structured-content">{JSON.stringify(analysis.message.content, null, 2)}</pre> }]} />
            )}
          </section>

          <section className="inbox-evidence-section" aria-labelledby="coverage-title">
            <SectionHeading id="coverage-title" eyebrow="证据边界" title="上下文与附件覆盖范围" />
            {analysis.contextSnapshot ? (
              <>
                <Descriptions
                  size="small"
                  column={{ xs: 1, sm: 2, lg: 3 }}
                  items={[
                    { key: 'version', label: '快照版本', children: `快照版本 ${analysis.contextSnapshot.snapshotVersion}` },
                    { key: 'messages', label: '纳入消息', children: `${analysis.contextSnapshot.messageIds.length} 条` },
                    { key: 'participants', label: '参与人 ID', children: `${analysis.contextSnapshot.participantIds.length} 个` },
                    { key: 'attachments', label: '附件 ID', children: `${analysis.contextSnapshot.attachmentIds.length} 个` },
                    { key: 'truncated', label: '是否截断', children: analysis.contextSnapshot.truncated ? '是，需关注缺失上下文' : '否' },
                    { key: 'created', label: '快照时间', children: analysis.contextSnapshot.createdAt },
                  ]}
                />
                <EvidenceIds label="消息 ID" values={analysis.contextSnapshot.messageIds} />
                <EvidenceIds label="参与人 ID" values={analysis.contextSnapshot.participantIds} />
                {analysis.contextSnapshot.attachmentIds.length > 0 ? (
                  <Alert
                    className="inbox-boundary-alert"
                    type="info"
                    showIcon
                    message="当前仅验证元数据，未证明附件正文已解析"
                    description={analysis.contextSnapshot.attachmentIds.join(' · ')}
                  />
                ) : judgement.missingInformation?.length ? (
                  <Alert className="inbox-boundary-alert" type="warning" showIcon message="当前快照未纳入附件" description="AI 指出仍有材料缺口；请勿把无附件误认为材料齐全。" />
                ) : null}
              </>
            ) : <Alert type="warning" showIcon message="当前分析没有 ContextSnapshot" />}
          </section>

          <section className="inbox-ai-section" aria-labelledby="ai-result-title">
            <SectionHeading id="ai-result-title" eyebrow="AI 建议 · 待人工确认" title="AI 提取结果" />
            <div className="inbox-ai-summary">
              <span><Text type="secondary">建议分类</Text><strong>{typeof category === 'string' ? categoryLabels[category] ?? category : '待分类'}</strong></span>
              <span><Text type="secondary">建议动作</Text><strong>{recommendedActionLabels[candidate.recommendedAction] ?? candidate.recommendedAction}</strong></span>
              <span><Text type="secondary">置信度</Text><strong>{Math.round(candidate.confidence * 100)}%（不能替代证据）</strong></span>
              <span><Text type="secondary">消息角色</Text><strong>{messageRoleLabels[candidate.messageRole] ?? candidate.messageRole}</strong></span>
              <span><Text type="secondary">法律相关性</Text><strong>{legalRelevanceLabels[candidate.legalRelevance] ?? candidate.legalRelevance}</strong></span>
            </div>
            <InformationList title="研判理由" values={judgement.reasons} />
            <InformationList title="消息中明确陈述（待法务确认）" values={judgement.confirmedFacts?.map((fact) => `${fact.statement}（来源 ${fact.sourceMessageId}）`)} />
            <InformationList title="AI 推断" tone="inference" values={judgement.inferredFacts?.map((fact) => `${fact.statement}（${fact.basis}，${Math.round(fact.confidence * 100)}%）`)} />
            <InformationList title="期限候选" values={judgement.deadlineCandidates?.map((deadline) => `${deadline.rawText} → ${deadline.resolvedAt ?? '待确认'}（${deadline.deadlineType}）`)} />
            <InformationList title="缺失信息与材料" tone="missing" values={judgement.missingInformation} />
          </section>

          <Collapse
            className="inbox-audit-collapse"
            ghost
            items={[{
              key: 'audit',
              label: '审计信息',
              children: (
                <Descriptions
                  size="small"
                  column={1}
                  items={[
                    { key: 'candidate', label: 'Candidate', children: `${candidate.id} · 版本 ${candidate.version}` },
                    { key: 'run', label: 'AgentRun', children: analysis.agentRun ? `${analysis.agentRun.id} · ${analysis.agentRun.agentKey} v${analysis.agentRun.agentVersion}` : '当前接口未提供' },
                    { key: 'snapshot', label: 'ContextSnapshot', children: analysis.contextSnapshot ? `${analysis.contextSnapshot.id} · ${analysis.contextSnapshot.contentHash}` : '当前接口未提供' },
                  ]}
                />
              ),
            }]}
          />
        </>
      )}

      <Divider />
      <section className="inbox-decision-section" aria-labelledby="decision-title">
        <SemanticStatusTag kind="human">待人工决定 · 尚未确认</SemanticStatusTag>
        <SectionHeading id="decision-title" eyebrow="人工处置" title="正式动作门禁" />
        {candidate.recommendedAction !== 'create_matter' && (
          <Alert type="warning" showIcon message="当前建议处置尚未接入，已阻止错误新建事项" description={`AI 建议为“${recommendedActionLabels[candidate.recommendedAction] ?? candidate.recommendedAction}”；本轮不会将其转换为新建事项。`} />
        )}
        <div className="inbox-decision-actions">
          {candidate.recommendedAction === 'create_matter' && (
            <Button type="primary" disabled={!canConfirmCreate} onClick={onConfirm}>审阅并创建事项</Button>
          )}
          {candidate.feishuMessageId && <Button loading={retrying} disabled={busy} onClick={onRetryAnalysis}>重新分析</Button>}
          {candidate.agentRunId && <Button type="link" onClick={() => onOpenAgentRun?.(candidate.agentRunId!)}>AgentRun 详情</Button>}
        </div>
        <div className="inbox-unavailable-actions">
          {['关联或更新事项', '补充材料', '仅作信息', '忽略', '暂缓', '合并'].map((label) => <Button key={label} aria-label={label} disabled>{label}</Button>)}
        </div>
        <Text className="inbox-unavailable-note" type="secondary">后端流程未接入，不会执行</Text>
      </section>
    </Card>
  );
}

function ConfirmDrawer({ candidate, analysis, form, submitting, onCancel, onConfirm, onValuesChange, onOpenChange }: {
  candidate?: MessageCandidate;
  analysis?: MessageAnalysis;
  form: FormInstance<ConfirmFormValues>;
  submitting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  onValuesChange: () => void;
  onOpenChange: (open: boolean) => void;
}) {
  const missingInformation = candidate?.analysisPayload.missingInformation ?? [];
  return (
    <Drawer
      rootClassName="inbox-confirm-drawer"
      title="审阅并创建事项"
      width={560}
      open={Boolean(candidate)}
      onClose={onCancel}
      afterOpenChange={onOpenChange}
      destroyOnHidden
      closable={!submitting}
      keyboard={!submitting}
      maskClosable={!submitting}
      footer={(
        <div className="inbox-confirm-footer">
          <Button aria-label="取消" disabled={submitting} onClick={onCancel}>取消</Button>
          <Button type="primary" loading={submitting} disabled={submitting} onClick={onConfirm}>确认创建 1 个事项与 1 个任务</Button>
        </div>
      )}
    >
      {candidate && (
        <>
          <div className="inbox-confirm-context">
            <Tag color="processing">AI 建议，可人工修改</Tag>
            <Text strong>{extractMessageText(analysis?.message.content ?? {}) ?? candidate.titleProposal ?? '原始消息未提供可读摘要'}</Text>
            <Text type="secondary">Candidate 版本 {candidate.version} · 来源 AgentRun {candidate.agentRunId ?? '当前接口未提供'}</Text>
          </div>
          <Form form={form} layout="vertical" requiredMark="optional" onValuesChange={onValuesChange}>
            <Form.Item name="title" label="事项标题" rules={[{ required: true, message: '请确认事项标题' }]}><Input /></Form.Item>
            <Form.Item name="primaryCategory" label="主分类" rules={[{ required: true }]}>
              <Select options={Object.entries(categoryLabels).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
            <Form.Item name="summary" label="事项背景（AI 建议，可人工修改）"><Input.TextArea rows={3} /></Form.Item>
            <Form.Item name="objective" label="处理目标"><Input.TextArea rows={2} /></Form.Item>
            <div className="inbox-confirm-grid">
              <Form.Item name="ownerId" label="事项负责人" rules={[{ required: true, message: '请明确事项负责人' }]}><Input /></Form.Item>
              <Form.Item name="legalRisk" label="法律风险" rules={[{ required: true, message: '请人工确认法律风险' }]}>
                <Select options={Object.entries(riskLabels).map(([value, label]) => ({ value, label }))} />
              </Form.Item>
              <Form.Item name="businessImpact" label="业务影响" rules={[{ required: true, message: '请人工确认业务影响' }]}>
                <Select options={[
                  { value: 'company', label: '公司级' }, { value: 'department', label: '部门级' },
                  { value: 'project', label: '项目级' }, { value: 'general', label: '一般' },
                ]} />
              </Form.Item>
            </div>
            <Divider orientation="left">首个 WorkItem</Divider>
            <Form.Item name="workItemTitle" label="任务名称" rules={[{ required: true }]}><Input /></Form.Item>
            <div className="inbox-confirm-grid">
              <Form.Item name="workItemOwnerId" label="首个任务负责人" rules={[{ required: true, message: '请明确任务负责人' }]}><Input /></Form.Item>
              <Form.Item name="priority" label="优先级" rules={[{ required: true, message: '请人工确认优先级' }]}>
                <Select options={Object.entries(priorityLabels).map(([value, label]) => ({ value, label }))} />
              </Form.Item>
              <Form.Item name="estimatedMinutes" label="预计分钟"><InputNumber min={1} style={{ width: '100%' }} /></Form.Item>
              <Form.Item
                name="plannedCompleteAt"
                label="计划完成时间"
                rules={[
                  { required: true, message: '请填写首个任务计划完成时间' },
                  {
                    validator: (_, value?: string) => !value || toPlannedCompleteAtIso(value)
                      ? Promise.resolve()
                      : Promise.reject(new Error('请按 YYYY-MM-DD HH:mm 填写有效时间')),
                  },
                ]}
              >
                <Input placeholder="YYYY-MM-DD HH:mm" />
              </Form.Item>
            </div>
            <Form.Item name="nextAction" label="下一步行动" rules={[{ required: true, message: '请明确下一步行动' }]}><Input.TextArea rows={2} /></Form.Item>
          </Form>
          {missingInformation.length > 0 && (
            <section className="inbox-missing-material-handoff" role="region" aria-label="缺失材料承接">
              <InformationList title="缺失信息与材料" tone="missing" values={missingInformation} />
              <Alert
                type="warning"
                showIcon
                message="创建事项后添加依赖"
                description="缺失材料已预填到首个任务的下一步行动。当前接口不会自动创建依赖；事项创建后请在任务中核对并添加依赖。"
              />
            </section>
          )}
          <Alert
            className="inbox-impact-preview"
            type="info"
            showIcon
            message="将原子创建 1 个 Matter 和 1 个 WorkItem"
            description="记录本次人工确认；不会发送消息，不会绕过后续审核。计划完成时间仅写入首个 WorkItem，不声称创建独立 Deadline。"
          />
        </>
      )}
    </Drawer>
  );
}

function SectionHeading({ id, eyebrow, title }: { id: string; eyebrow: string; title: string }) {
  return <div className="inbox-section-heading"><span className="eyebrow">{eyebrow}</span><Title id={id} level={4}>{title}</Title></div>;
}

function InformationList({ title, values, tone = 'neutral' }: { title: string; values?: string[]; tone?: 'neutral' | 'inference' | 'missing' }) {
  if (!values?.length) return null;
  return <div className={`inbox-information-list inbox-information-${tone}`}><strong>{title}</strong>{values.map((value, index) => <span key={`${title}-${index}`}>· {value}</span>)}</div>;
}

function EvidenceIds({ label, values }: { label: string; values: string[] }) {
  return <div className="inbox-evidence-ids"><Text type="secondary">{label}</Text><div>{values.map((value) => <code key={value}>{value}</code>)}</div></div>;
}

function extractMessageText(content: Record<string, unknown>): string | undefined {
  for (const key of ['text', 'content', 'body', 'title']) {
    const value = content[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return undefined;
}

function toPlannedCompleteAtIso(value: string): string | undefined {
  if (!plannedCompleteAtPattern.test(value)) return undefined;
  const parsed = dayjs(value);
  if (!parsed.isValid() || parsed.format('YYYY-MM-DD HH:mm') !== value) return undefined;
  return parsed.toISOString();
}
