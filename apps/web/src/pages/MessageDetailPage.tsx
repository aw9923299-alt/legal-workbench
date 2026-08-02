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

export default function MessageDetailPage() {
  const { messageId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const realtime = useRealtimeStatus();
  const [createOpen, setCreateOpen] = useState(false);
  const [linkAction, setLinkAction] = useState<'link_existing' | 'update_existing'>();
  const [matterId, setMatterId] = useState<string>();
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
            <List dataSource={detail.data.attachments} locale={{ emptyText: '无附件' }} renderItem={(file) => <List.Item><List.Item.Meta title={file.fileName} description={`${file.mimeType ?? '未知类型'} · ${file.size ?? '未知大小'} · ${file.downloadStatus}`} /><Tag color={file.authorizedForAnalysis ? 'green' : 'default'}>{file.authorizedForAnalysis ? '已授权分析' : '未授权正文'}</Tag></List.Item>} />
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
            <Divider>法务人工动作</Divider>
            <Space wrap>
              {candidate.data?.status === 'pending_confirmation' && <>
                <Button type="primary" onClick={openCreate}>创建新 Matter</Button>
                <Button icon={<LinkOutlined />} onClick={() => setLinkAction('link_existing')}>关联已有 Matter</Button>
                <Button onClick={() => setLinkAction('update_existing')}>更新已有 Matter</Button>
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
    <Modal open={Boolean(linkAction)} title={linkAction === 'update_existing' ? '更新已有 Matter' : '关联已有 Matter'} okText="确认" confirmLoading={resolve.isPending} onCancel={() => setLinkAction(undefined)} onOk={() => linkAction && matterId && resolve.mutate({ action: linkAction, selectedMatter: matterId })} okButtonProps={{ disabled: !matterId }}>
      <Alert type="info" showIcon message={linkAction === 'update_existing' ? '本操作登记 Candidate 为已有事项更新，不会静默改写事项字段。' : '本操作建立可审计关联。'} />
      <Select showSearch style={{ width: '100%', marginTop: 16 }} placeholder="选择 Matter" value={matterId} onChange={setMatterId} loading={matters.isLoading} options={matters.data?.map((matter) => ({ value: matter.id, label: `${matter.matterNumber} · ${matter.title}` }))} />
    </Modal>
  </div>;
}
