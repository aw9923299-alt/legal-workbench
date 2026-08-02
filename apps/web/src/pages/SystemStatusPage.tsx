import { ExclamationCircleOutlined, ReloadOutlined, SyncOutlined, WarningOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Col, Descriptions, List, Modal, Row, Space, Statistic, Tag, Typography, message } from 'antd';
import { QueryState } from '../components/QueryState';
import {
  clearMutationContext,
  getOrCreateMutationContext,
  isDefinitiveMutationFailure,
  legalApi,
} from '../services/api';
import { useRealtimeStatus } from '../services/RealtimeProvider';

const { Title, Text, Paragraph } = Typography;
const labels: Record<string, string> = {
  fastapi: 'FastAPI', postgresql: 'PostgreSQL', redis: 'Redis', celery_worker: 'Celery Worker',
  celery_scheduler: 'Celery Scheduler', feishu: '飞书连接', codex_cli: 'Codex CLI', codex_auth: 'Codex 认证',
};
const colors: Record<string, string> = { normal: 'green', degraded: 'orange', unavailable: 'red', not_configured: 'default' };
const statuses: Record<string, string> = { normal: '正常', degraded: '降级', unavailable: '不可用', not_configured: '未配置' };

function useAuditedOperation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ key, payload, call }: { key: string; payload: unknown; call: Parameters<typeof execute>[2] }) => execute(key, payload, call),
    onSuccess: () => {
      message.success('操作已完成并写入审计');
      void queryClient.invalidateQueries({ queryKey: ['system'] });
      void queryClient.invalidateQueries({ queryKey: ['feishu-status'] });
      void queryClient.invalidateQueries({ queryKey: ['agent-runs'] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : '操作失败'),
  });
}

async function execute<T>(key: string, payload: unknown, call: (context: ReturnType<typeof getOrCreateMutationContext>) => Promise<T>): Promise<T> {
  const context = getOrCreateMutationContext(key, payload);
  try {
    const result = await call(context);
    clearMutationContext(key);
    return result;
  } catch (error) {
    if (isDefinitiveMutationFailure(error)) clearMutationContext(key);
    throw error;
  }
}

export default function SystemStatusPage() {
  const realtime = useRealtimeStatus();
  const operation = useAuditedOperation();
  const health = useQuery({ queryKey: ['system', 'health'], queryFn: () => legalApi.getSystemHealth(), refetchInterval: realtime.pollingInterval || 10_000 });
  const feishu = useQuery({ queryKey: ['feishu-status'], queryFn: () => legalApi.getFeishuStatus(), refetchInterval: realtime.pollingInterval || 10_000 });
  const deadLetters = useQuery({ queryKey: ['system', 'outbox-dead-letters'], queryFn: () => legalApi.listOutboxDeadLetters(), refetchInterval: realtime.pollingInterval || 15_000 });
  const deadRuns = useQuery({ queryKey: ['agent-runs', 'dead_letter'], queryFn: () => legalApi.listAgentRuns('dead_letter'), refetchInterval: realtime.pollingInterval || 15_000 });
  const confirm = (title: string, content: string, onOk: () => Promise<unknown>) => Modal.confirm({ title, content, icon: <ExclamationCircleOutlined />, okText: '确认执行', okButtonProps: { danger: true }, onOk });
  const metrics = health.data?.metrics;

  return <div className="page">
    <div className="page-title-row">
      <div><span className="eyebrow">LIVE OPERATIONAL HEALTH</span><Title level={2}>系统状态</Title><Text type="secondary">所有状态来自实时健康接口；业务事实和恢复游标仍以 PostgreSQL 为准。</Text></div>
      <Space><Tag color={realtime.connected ? 'green' : 'orange'}>{realtime.connected ? 'SSE 正常' : 'SSE 断开 · 轮询回退'}</Tag><Button icon={<ReloadOutlined />} onClick={() => { void health.refetch(); void feishu.refetch(); }}>刷新</Button></Space>
    </div>
    {!realtime.connected && <Alert type="warning" showIcon message="实时连接已断开" description="页面已自动切换为 15 秒轮询；SSE 会按指数退避自动重连。" />}
    <QueryState loading={health.isLoading} error={health.error} onRetry={() => void health.refetch()}>
      {health.data && <>
        <Row gutter={[14, 14]} style={{ marginTop: 14 }}>
          {Object.entries(health.data.components).map(([key, component]) => <Col xs={12} md={8} xl={6} key={key}><Card className="health-card" variant="borderless"><Space direction="vertical"><Text type="secondary">{labels[key] ?? key}</Text><Tag color={colors[component.status]}>{statuses[component.status] ?? component.status}</Tag><Paragraph ellipsis={{ rows: 2, expandable: true }}>{component.detail}</Paragraph><Text type="secondary">{new Date(component.updatedAt).toLocaleString()}</Text></Space></Card></Col>)}
          <Col xs={12} md={8} xl={6}><Card className="health-card" variant="borderless"><Space direction="vertical"><Text type="secondary">SSE 连接</Text><Tag color={realtime.connected ? 'green' : 'orange'}>{realtime.connected ? '正常' : '降级'}</Tag><Paragraph>{realtime.connected ? '实时事件流已连接。' : '有限频率轮询已启用。'}</Paragraph><Text type="secondary">最近事件：{realtime.lastEventAt ? new Date(realtime.lastEventAt).toLocaleString() : '—'}</Text></Space></Card></Col>
        </Row>
        <Row gutter={[14, 14]} style={{ marginTop: 14 }}>
          {[['Outbox 积压', metrics?.outboxPending], ['Agent 队列', metrics?.agentQueued], ['失败任务', metrics?.failedRuns], ['Agent 死信', metrics?.agentDeadLetters], ['Outbox 死信', metrics?.outboxDeadLetters]].map(([label, value]) => <Col xs={12} md={8} xl={4} key={String(label)}><Card variant="borderless"><Statistic title={String(label)} value={Number(value ?? 0)} /></Card></Col>)}
        </Row>
        <Row gutter={14} style={{ marginTop: 14 }}>
          <Col xs={24} xl={12}><Card title="运行与集成详情" variant="borderless"><Descriptions bordered size="small" column={1}>
            <Descriptions.Item label="Codex 状态">{health.data.codex.status}</Descriptions.Item><Descriptions.Item label="检测版本">{health.data.codex.detectedVersion ?? '—'}</Descriptions.Item><Descriptions.Item label="期望版本">{health.data.codex.expectedVersion ?? '—'}</Descriptions.Item><Descriptions.Item label="认证">{health.data.codex.authentication}</Descriptions.Item><Descriptions.Item label="Runtime 目录">{health.data.codex.runtimeDirectoryWritable ? '可写' : '不可写'}</Descriptions.Item>
            <Descriptions.Item label="飞书模式">{feishu.data?.connectionMode ?? '—'}</Descriptions.Item><Descriptions.Item label="飞书状态">{feishu.data?.status ?? '—'}</Descriptions.Item><Descriptions.Item label="重连次数">{feishu.data?.reconnectCount ?? 0}</Descriptions.Item><Descriptions.Item label="最近成功消息">{metrics?.lastMessageAt ? new Date(metrics.lastMessageAt).toLocaleString() : '—'}</Descriptions.Item><Descriptions.Item label="最近成功 AgentRun">{metrics?.lastCompletedRunAt ? new Date(metrics.lastCompletedRunAt).toLocaleString() : '—'}</Descriptions.Item><Descriptions.Item label="最近补偿同步">{metrics?.lastReconcileAt ? new Date(metrics.lastReconcileAt).toLocaleString() : '—'}</Descriptions.Item>
          </Descriptions></Card></Col>
          <Col xs={24} xl={12}><Card title="恢复操作" variant="borderless"><Space direction="vertical" style={{ width: '100%' }}>
            <Button block icon={<SyncOutlined />} loading={operation.isPending} onClick={() => void confirm('重新连接飞书？', '连接器将停止并重新启动；数据库中的消息不会删除。', () => operation.mutateAsync({ key: 'system:feishu-reconnect', payload: {}, call: (context) => legalApi.reconnectFeishu(context) }))}>重新连接飞书</Button>
            <Button block icon={<SyncOutlined />} loading={operation.isPending} onClick={() => void confirm('触发 60 分钟补偿同步？', '重复事件由 PostgreSQL 唯一约束吸收；飞书接口能力受限时会返回明确限制。', () => operation.mutateAsync({ key: 'system:feishu-reconcile:60', payload: { windowMinutes: 60 }, call: (context) => legalApi.reconcileFeishu(60, context) }))}>触发补偿同步</Button>
            <Button block danger icon={<WarningOutlined />} loading={operation.isPending} onClick={() => void confirm('恢复遗留分析任务？', '系统将扫描无活动 Run 的待分析消息和租约过期 Run。', () => operation.mutateAsync({ key: 'system:recover-pending', payload: {}, call: (context) => legalApi.recoverPendingJobs(context) }))}>重新派发遗留任务</Button>
          </Space></Card></Col>
        </Row>
        <Row gutter={14} style={{ marginTop: 14 }}>
          <Col xs={24} xl={12}><Card title={`Agent 死信（${deadRuns.data?.length ?? 0}）`} variant="borderless"><QueryState loading={deadRuns.isLoading} error={deadRuns.error} empty={!deadRuns.data?.length} onRetry={() => void deadRuns.refetch()}><List dataSource={deadRuns.data} renderItem={(run) => <List.Item actions={[<Button key="retry" danger onClick={() => void confirm('重新派发 Agent 死信？', `Run ${run.id} 将基于原消息创建新的可审计尝试。`, () => operation.mutateAsync({ key: `system:retry-run:${run.id}`, payload: { runId: run.id }, call: (context) => legalApi.retryAgentRun(run.id, context) }))}>重新入队</Button>]}><List.Item.Meta title={`${run.agentKey} · ${run.id}`} description={`${run.failureCode ?? 'UNKNOWN'} · ${run.failureMessage ?? '无失败摘要'}`} /></List.Item>} /></QueryState></Card></Col>
          <Col xs={24} xl={12}><Card title={`Outbox 死信（${deadLetters.data?.filter((item) => !item.requeuedAt).length ?? 0}）`} variant="borderless"><QueryState loading={deadLetters.isLoading} error={deadLetters.error} empty={!deadLetters.data?.some((item) => !item.requeuedAt)} onRetry={() => void deadLetters.refetch()}><List dataSource={deadLetters.data?.filter((item) => !item.requeuedAt)} renderItem={(item) => <List.Item actions={[<Button key="requeue" danger onClick={() => void confirm('重新派发 Outbox 死信？', `${item.eventType} 将生成新的 Outbox 事件，并保留原死信。`, () => operation.mutateAsync({ key: `system:requeue-outbox:${item.id}`, payload: { deadLetterId: item.id }, call: (context) => legalApi.requeueOutboxDeadLetter(item.id, context) }))}>重新入队</Button>]}><List.Item.Meta title={`${item.eventType} · ${item.id}`} description={`${item.lastError} · Correlation ID ${item.correlationId}`} /></List.Item>} /></QueryState></Card></Col>
        </Row>
        <div className="updated-at">健康快照：{new Date(health.data.generatedAt).toLocaleString()}</div>
      </>}
    </QueryState>
  </div>;
}
