import { ArrowLeftOutlined, HistoryOutlined, LinkOutlined, ReloadOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Col, Collapse, DatePicker, Descriptions, Divider, Form, Input, List, Modal, Progress, Row, Select, Space, Tabs, Tag, Timeline, Typography, message } from 'antd';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { EvidencePanels } from '../components/EvidencePanels';
import { QueryState } from '../components/QueryState';
import {
  clearMutationContext,
  getOrCreateMutationContext,
  isDefinitiveMutationFailure,
  legalApi,
  type ConfirmCandidateInput,
} from '../services/api';
import { categoryLabels, priorityLabels } from '../services/apiLabels';
import { useRealtimeStatus } from '../services/RealtimeProvider';
import type { MatterCategory, MessageJudgementResult, Priority } from '../types/api';

const { Title, Text, Paragraph } = Typography;

interface HumanForm {
  title: string;
  category: MatterCategory;
  priority: Priority;
  deadline?: { toISOString(): string };
  ownerId: string;
  nextAction: string;
}

interface RelatedMatterProposal {
  matterId: string;
  matterNumber: string;
  title: string;
  confidence: number;
  signals: string[];
  evidenceRefs: string[];
}

const continuitySignalLabels: Record<string, string> = {
  reply_to_communication: '回复自已发送沟通',
  same_thread_confirmed_link: '同一会话已有人工关联',
};

function relatedMatterProposals(values: Array<Record<string, unknown>> | undefined): RelatedMatterProposal[] {
  if (!values) return [];
  return values.flatMap((value) => {
    const matterId = typeof value.matterId === 'string' ? value.matterId : '';
    const matterNumber = typeof value.matterNumber === 'string' ? value.matterNumber : '';
    const title = typeof value.title === 'string' ? value.title : '';
    const confidence = typeof value.confidence === 'number' ? value.confidence : 0;
    if (!matterId || !matterNumber || !title) return [];
    return [{
      matterId,
      matterNumber,
      title,
      confidence,
      signals: Array.isArray(value.signals) ? value.signals.filter((item): item is string => typeof item === 'string') : [],
      evidenceRefs: Array.isArray(value.evidenceRefs) ? value.evidenceRefs.filter((item): item is string => typeof item === 'string') : [],
    }];
  });
}

export default function MessageDetailPage() {
  const { messageId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const realtime = useRealtimeStatus();
  const [createOpen, setCreateOpen] = useState(false);
  const [linkAction, setLinkAction] = useState<'link_existing' | 'update_existing'>();
  const [matterId, setMatterId] = useState<string>();
  const [updateReason, setUpdateReason] = useState('消息包含已有事项的新进展，提交法务审核。');
  const [form] = Form.useForm<HumanForm>();
  const detail = useQuery({ queryKey: ['inbox', 'detail', messageId], queryFn: () => legalApi.getMessage(messageId), enabled: Boolean(messageId), refetchInterval: realtime.pollingInterval });
  const analysis = useQuery({ queryKey: ['inbox', 'analysis', messageId], queryFn: () => legalApi.getMessageAnalysis(messageId), enabled: Boolean(messageId), refetchInterval: realtime.pollingInterval });
  const candidate = useQuery({ queryKey: ['candidate', detail.data?.candidateId], queryFn: () => legalApi.getCandidate(detail.data!.candidateId!), enabled: Boolean(detail.data?.candidateId) });
  const matters = useQuery({ queryKey: ['matters'], queryFn: () => legalApi.listMatters(), enabled: Boolean(linkAction) });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['inbox'] });
    void queryClient.invalidateQueries({ queryKey: ['candidate'] });
  };
  const retry = useMutation({
    mutationFn: async () => {
      const key = `retry-analysis:${messageId}`;
      const context = getOrCreateMutationContext(key, { forceNewRun: true });
      try {
        const result = await legalApi.retryMessageAnalysis(messageId, context);
        clearMutationContext(key);
        return result;
      } catch (error) {
        if (isDefinitiveMutationFailure(error)) clearMutationContext(key);
        throw error;
      }
    },
    onSuccess: () => { message.success('已要求重新分析，历史版本保留'); invalidate(); },
    onError: (error) => message.error(error instanceof Error ? error.message : '重新分析失败'),
  });
  const authorizeAttachment = useMutation({
    mutationFn: async ({ attachmentId, authorized }: { attachmentId: string; authorized: boolean }) => {
      const key = `attachment-authorization:${attachmentId}:${authorized}`;
      const payload = { authorized };
      const context = getOrCreateMutationContext(key, payload);
      try {
        const result = await legalApi.setAttachmentAnalysisAuthorization(
          messageId,
          attachmentId,
          authorized,
          context,
        );
        clearMutationContext(key);
        return result;
      } catch (error) {
        if (isDefinitiveMutationFailure(error)) clearMutationContext(key);
        throw error;
      }
    },
    onSuccess: (_result, variables) => {
      message.success(variables.authorized ? '已授权附件正文；请点击重新分析生成新版本' : '已撤销附件正文授权');
      void detail.refetch();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : '附件授权失败'),
  });
  const resolve = useMutation({
    mutationFn: async ({ action, selectedMatter }: { action: 'link_existing' | 'update_existing' | 'information_only' | 'ignore'; selectedMatter?: string }) => {
      if (!candidate.data) throw new Error('Candidate 尚未加载');
      const key = `resolve:${candidate.data.id}:${action}:${selectedMatter ?? ''}`;
      const payload = { candidateVersion: candidate.data.version, action, matterId: selectedMatter };
      const context = getOrCreateMutationContext(key, payload);
      try {
        const result = await legalApi.resolveCandidate(candidate.data.id, payload, context);
        clearMutationContext(key);
        return result;
      } catch (error) {
        if (isDefinitiveMutationFailure(error)) clearMutationContext(key);
        throw error;
      }
    },
    onSuccess: () => { message.success('人工决定已保存'); setLinkAction(undefined); invalidate(); },
    onError: (error) => message.error(error instanceof Error ? error.message : '处理失败'),
  });
  const createMatter = useMutation({
    mutationFn: async (values: HumanForm) => {
      if (!candidate.data) throw new Error('Candidate 尚未加载');
      const payload: ConfirmCandidateInput = {
        candidateVersion: candidate.data.version,
        title: values.title,
        primaryCategory: values.category,
        secondaryCategories: [],
        ownerId: values.ownerId,
        requesterIds: [],
        legalRisk: 'pending',
        businessImpact: 'general',
        confidentiality: 'internal',
        summary: `由消息 ${detail.data?.messageId} 人工确认创建`,
        initialWorkItems: [{
          title: values.title,
          ownerId: values.ownerId,
          priority: values.priority,
          prioritySource: 'legal_confirmed',
          nextAction: values.nextAction,
          priorityReasons: ['法务人工确认'],
          plannedCompleteAt: values.deadline?.toISOString(),
        }],
      };
      const key = `confirm-candidate:${candidate.data.id}`;
      const context = getOrCreateMutationContext(key, payload);
      try {
        const result = await legalApi.confirmCandidate(candidate.data.id, payload, context);
        clearMutationContext(key);
        return result;
      } catch (error) {
        if (isDefinitiveMutationFailure(error)) clearMutationContext(key);
        throw error;
      }
    },
    onSuccess: (result) => { message.success(`已创建事项 ${result.matterNumber}`); setCreateOpen(false); navigate(`/matters/${result.matterId}`); },
    onError: (error) => message.error(error instanceof Error ? error.message : '创建事项失败'),
  });
  const createProposal = useMutation({
    mutationFn: async () => {
      if (!candidate.data || !matterId) throw new Error('请选择要更新的 Matter');
      const requestedFields = [
        'title', 'category', 'priority', 'deadline', 'owner',
        'currentStatus', 'nextAction', 'newWorkItems',
      ];
      const proposedChanges = Object.fromEntries(requestedFields.map((field) => [field, {
        currentValue: null,
        messageExtractedValue: null,
        aiSuggestedValue: null,
      }]));
      const payload = {
        candidateVersion: candidate.data.version,
        matterId,
        proposedChanges,
        reason: updateReason,
      };
      const key = `matter-update-proposal:${candidate.data.id}:${matterId}`;
      const context = getOrCreateMutationContext(key, payload);
      try {
        const response = await legalApi.createMatterUpdateProposal(
          candidate.data.id,
          payload,
          context,
        );
        clearMutationContext(key);
        return response;
      } catch (error) {
        if (isDefinitiveMutationFailure(error)) clearMutationContext(key);
        throw error;
      }
    },
    onSuccess: (response) => {
      message.success('更新建议已提交，Matter 尚未修改');
      setLinkAction(undefined);
      navigate(`/matter-update-proposals/${response.proposalId}`);
    },
    onError: (error) => message.error(error instanceof Error ? error.message : '提交更新建议失败'),
  });

  const openCreate = () => {
    const result = analysis.data?.analysisResult;
    const proposedCategory = result?.categoryCandidates[0]?.category;
    form.setFieldsValue({
      title: candidate.data?.titleProposal ?? result?.suggestedTitle ?? '待确认法务事项',
      category: (proposedCategory === 'general' ? 'general_consultation' : proposedCategory) ?? 'general_consultation',
      priority: 'medium', ownerId: 'local-legal-user', nextAction: '核实事实、材料和完成时间',
    });
    setCreateOpen(true);
  };

  const continuityProposals = relatedMatterProposals(candidate.data?.relatedMatterProposals);
  const openLinkAction = (action: 'link_existing' | 'update_existing') => {
    setMatterId(continuityProposals[0]?.matterId);
    setLinkAction(action);
  };
  const recommendedMatterIds = new Set(continuityProposals.map((value) => value.matterId));
  const matterOptions = [
    ...continuityProposals.map((value) => ({
      value: value.matterId,
      label: `${value.matterNumber} · ${value.title}`,
    })),
    ...(matters.data ?? [])
      .filter((value) => !recommendedMatterIds.has(value.id))
      .map((value) => ({ value: value.id, label: `${value.matterNumber} · ${value.title}` })),
  ];

  const result = analysis.data?.analysisResult as MessageJudgementResult | null | undefined;
  return <div className="page">
    <div className="page-title-row">
      <Space><Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/inbox')}>返回收件箱</Button><div><span className="eyebrow">MESSAGE EVIDENCE & HUMAN DECISION</span><Title level={2}>消息详情</Title></div></Space>
      <Space><Tag color={realtime.connected ? 'green' : 'orange'}>{realtime.connected ? '实时' : '轮询'}</Tag><Button icon={<ReloadOutlined />} onClick={() => { void detail.refetch(); void analysis.refetch(); }}>刷新</Button></Space>
    </div>
    <QueryState loading={detail.isLoading || analysis.isLoading} error={detail.error || analysis.error} onRetry={() => { void detail.refetch(); void analysis.refetch(); }}>
      {detail.data && <Row gutter={16} align="stretch">
        <Col xs={24} xl={12}>
          <Card title="原始飞书消息" className="source-message-card" variant="borderless">
            <Paragraph className="source-text">{detail.data.plainText || '无可读正文'}</Paragraph>
            <Descriptions size="small" column={2}>
              <Descriptions.Item label="消息 ID" span={2}>{detail.data.messageId}</Descriptions.Item>
              <Descriptions.Item label="发送人">{detail.data.senderId ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="群聊">{detail.data.chatId ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="父消息">{detail.data.parentMessageId ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="根消息">{detail.data.rootMessageId ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="编辑">{detail.data.editedAt ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="撤回">{detail.data.recalledAt ?? '未撤回'}</Descriptions.Item>
              <Descriptions.Item label="类型">{detail.data.messageType}</Descriptions.Item>
              <Descriptions.Item label="状态"><Tag>{detail.data.status}</Tag></Descriptions.Item>
            </Descriptions>
            {detail.data.unsupportedReason && <Alert type="warning" showIcon message="不支持分析" description={detail.data.unsupportedReason} />}
            <Divider>线程上下文</Divider>
            <Timeline items={detail.data.contextMessages.map((value) => ({ children: <><Text strong>{value.senderId ?? '未知发送人'}</Text><Paragraph>{value.plainText || value.unsupportedReason || '无正文'}</Paragraph></> }))} />
            <Divider>附件元数据</Divider>
            <List
              dataSource={detail.data.attachments}
              locale={{ emptyText: '无附件' }}
              renderItem={(file) => (
                <List.Item
                  id={`attachment-${file.id}`}
                  actions={file.downloadStatus === 'downloaded' ? [
                    <Button
                      key="authorization"
                      size="small"
                      loading={authorizeAttachment.isPending}
                      onClick={() => authorizeAttachment.mutate({
                        attachmentId: file.id,
                        authorized: !file.authorizedForAnalysis,
                      })}
                    >
                      {file.authorizedForAnalysis ? '撤销正文授权' : '授权正文给 Codex'}
                    </Button>,
                  ] : undefined}
                >
                  <List.Item.Meta
                    title={file.fileName}
                    description={[
                      file.mimeType ?? '未知类型',
                      file.size == null ? '未知大小' : `${file.size} B`,
                      `下载 ${file.downloadStatus}`,
                      `解析 ${file.extractionStatus}`,
                      file.downloadStatus === 'metadata_only' ? '附件已检测，正文暂不可读取' : null,
                      file.extractionStatus === 'body_unavailable' && file.downloadStatus !== 'metadata_only' ? '正文暂不可解析' : null,
                      file.extractionErrorCode,
                    ].filter(Boolean).join(' · ')}
                  />
                  <Space size={4}>
                    {file.downloadStatus === 'metadata_only' && <Tag color="orange">仅元数据</Tag>}
                    <Tag color={file.authorizedForAnalysis ? 'green' : 'default'}>
                      {file.authorizedForAnalysis ? '已授权分析' : '未授权正文'}
                    </Tag>
                  </Space>
                </List.Item>
              )}
            />
            <Collapse items={[
              { key: 'versions', label: `编辑/撤回历史（${detail.data.versions.length}）`, children: <Timeline items={detail.data.versions.map((version) => ({ children: `v${version.revision} · ${version.isRecalled ? '已撤回' : version.plainText || '无正文'} · ${new Date(version.createdAt).toLocaleString()}` }))} /> },
              { key: 'raw', label: '查看受控原始 Payload', children: <pre className="agent-json">{JSON.stringify(detail.data.rawPayload, null, 2)}</pre> },
            ]} />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="Agent 分析与人工确认" variant="borderless">
            {analysis.data?.agentRun ? <>
              <Space wrap><Tag color="blue">{analysis.data.agentRun.status}</Tag><Tag>{analysis.data.agentRun.agentKey} v{analysis.data.agentRun.agentVersion}</Tag><Button type="link" onClick={() => navigate(`/agent-runs/${analysis.data!.agentRun!.id}`)}>查看 AgentRun</Button></Space>
              <Descriptions size="small" column={2}>
                <Descriptions.Item label="置信度"><Progress percent={Math.round((result?.confidence ?? 0) * 100)} size="small" /></Descriptions.Item>
                <Descriptions.Item label="建议分类">{result?.categoryCandidates.map((value) => categoryLabels[value.category] ?? value.category).join('、') || '—'}</Descriptions.Item>
                <Descriptions.Item label="建议标题" span={2}>{result?.suggestedTitle ?? '—'}</Descriptions.Item>
                <Descriptions.Item label="建议截止" span={2}>{result?.deadlineCandidates.map((value) => `${value.rawText} → ${value.resolvedAt ?? '待确认'}`).join('；') || '—'}</Descriptions.Item>
              </Descriptions>
              {result && <><EvidencePanels result={result} /><Divider>判断理由</Divider><List size="small" dataSource={result.reasons} renderItem={(value) => <List.Item>{value}</List.Item>} /></>}
            </> : <Alert type={analysis.data?.failureCode ? 'error' : 'info'} message={analysis.data?.failureCode ?? '尚未生成 AgentRun'} description={analysis.data?.failureMessage} />}
            {continuityProposals.length > 0 && <>
              <Divider>可能关联事项</Divider>
              <Alert
                type="info"
                showIcon
                message="以下建议只来自已发送沟通或同一会话的人工确认关系，系统不会自动关联 Matter。"
                style={{ marginBottom: 12 }}
              />
              <List
                size="small"
                dataSource={continuityProposals}
                renderItem={(proposal) => <List.Item>
                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    <Text strong>{proposal.matterNumber} · {proposal.title}</Text>
                    <Space wrap>
                      <Tag color="blue">确定性置信度 {Math.round(proposal.confidence * 100)}%</Tag>
                      {proposal.signals.map((signal) => <Tag key={signal}>{continuitySignalLabels[signal] ?? signal}</Tag>)}
                    </Space>
                  </Space>
                </List.Item>}
              />
            </>}
            <Divider>法务人工动作</Divider>
            <Space wrap>
              {candidate.data?.status === 'pending_confirmation' && <>
                <Button type="primary" onClick={openCreate}>创建新 Matter</Button>
                <Button icon={<LinkOutlined />} onClick={() => openLinkAction('link_existing')}>关联已有 Matter</Button>
                <Button onClick={() => openLinkAction('update_existing')}>更新已有 Matter</Button>
                <Button onClick={() => resolve.mutate({ action: 'information_only' })}>仅供知悉</Button>
                <Button danger onClick={() => Modal.confirm({ title: '确认忽略？', content: '该决定会作为法务人工修改写入审计。', okButtonProps: { danger: true }, onOk: () => resolve.mutateAsync({ action: 'ignore' }) })}>忽略</Button>
              </>}
              <Button icon={<HistoryOutlined />} loading={retry.isPending} onClick={() => retry.mutate()}>要求重新分析</Button>
            </Space>
            <div className="human-decision-note">人工修改区：提交前可调整标题、分类、优先级、截止时间、负责人和下一步行动；AI 建议不会覆盖这里的确认值。</div>
            <Divider>分析版本</Divider>
            <Collapse items={detail.data.candidateRevisions.map((revision) => ({ key: revision.id, label: `Revision ${revision.revision} · Run ${revision.agentRunId.slice(0, 8)} · ${revision.supersededAt ? '已被替代' : '当前'}`, children: <pre className="agent-json">{JSON.stringify(revision.analysisPayload, null, 2)}</pre> }))} />
          </Card>
        </Col>
      </Row>}
    </QueryState>

    <Modal open={createOpen} title="人工确认并创建 Matter" okText="确认创建" confirmLoading={createMatter.isPending} onCancel={() => setCreateOpen(false)} onOk={() => void form.validateFields().then((values) => createMatter.mutate(values))}>
      <Form form={form} layout="vertical">
        <Form.Item name="title" label="标题" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="category" label="分类" rules={[{ required: true }]}><Select options={Object.entries(categoryLabels).map(([value, label]) => ({ value, label }))} /></Form.Item>
        <Form.Item name="priority" label="优先级" rules={[{ required: true }]}><Select options={Object.entries(priorityLabels).map(([value, label]) => ({ value, label }))} /></Form.Item>
        <Form.Item name="deadline" label="截止时间"><DatePicker showTime style={{ width: '100%' }} /></Form.Item>
        <Form.Item name="ownerId" label="负责人" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="nextAction" label="下一步行动" rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item>
      </Form>
    </Modal>
    <Modal open={Boolean(linkAction)} title={linkAction === 'update_existing' ? '提交已有 Matter 更新建议' : '关联已有 Matter'} okText={linkAction === 'update_existing' ? '生成待审建议' : '确认关联'} confirmLoading={resolve.isPending || createProposal.isPending} onCancel={() => setLinkAction(undefined)} onOk={() => {
      if (!linkAction || !matterId) return;
      if (linkAction === 'update_existing') createProposal.mutate();
      else resolve.mutate({ action: linkAction, selectedMatter: matterId });
    }} okButtonProps={{ disabled: !matterId || (linkAction === 'update_existing' && !updateReason.trim()) }}>
      <Alert type="info" showIcon message={linkAction === 'update_existing' ? '只生成待法务审核的更新建议；不会在此步骤修改 Matter。' : '本操作建立可审计关联。'} />
      <Select showSearch style={{ width: '100%', marginTop: 16 }} placeholder="选择 Matter" value={matterId} onChange={setMatterId} loading={matters.isLoading} options={matterOptions} />
      {linkAction === 'update_existing' && <Input.TextArea style={{ marginTop: 16 }} rows={3} value={updateReason} onChange={(event) => setUpdateReason(event.target.value)} placeholder="说明为什么需要更新事项" />}
    </Modal>
  </div>;
}
