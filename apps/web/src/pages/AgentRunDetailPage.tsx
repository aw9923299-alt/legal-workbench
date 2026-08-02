import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Col, Collapse, Descriptions, Divider, Modal, Row, Space, Tag, Timeline, Typography, message } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import { QueryState } from '../components/QueryState';
import { clearMutationContext, getOrCreateMutationContext, isDefinitiveMutationFailure, legalApi } from '../services/api';
import { useRealtimeStatus } from '../services/RealtimeProvider';

const { Title, Text, Paragraph } = Typography;
const active = new Set(['queued', 'preparing', 'running', 'validating']);
const retryable = new Set(['failed', 'timed_out', 'cancelled', 'dead_letter']);

export default function AgentRunDetailPage() {
  const { runId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const realtime = useRealtimeStatus();
  const query = useQuery({ queryKey: ['agent-runs', 'detail', runId], queryFn: () => legalApi.getAgentRun(runId), enabled: Boolean(runId), refetchInterval: realtime.pollingInterval });
  const mutate = useMutation({
    mutationFn: async (action: 'retry' | 'cancel') => {
      const key = `${action}-run:${runId}`;
      const context = getOrCreateMutationContext(key, { runId, action });
      try {
        const result = action === 'retry' ? await legalApi.retryAgentRun(runId, context) : await legalApi.cancelAgentRun(runId, context);
        clearMutationContext(key);
        return result;
      } catch (error) {
        if (isDefinitiveMutationFailure(error)) clearMutationContext(key);
        throw error;
      }
    },
    onSuccess: () => { message.success('操作已提交并写入审计'); void queryClient.invalidateQueries({ queryKey: ['agent-runs'] }); },
    onError: (error) => message.error(error instanceof Error ? error.message : '操作失败'),
  });
  const run = query.data;
  return <div className="page">
    <div className="page-title-row">
      <Space><Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/agent-runs')}>返回</Button><div><span className="eyebrow">AUDITABLE AGENT EXECUTION</span><Title level={2}>AgentRun 详情</Title></div></Space>
      <Space>{run && active.has(run.status) && <Button danger onClick={() => Modal.confirm({ title: '取消运行？', content: '取消为协作式门禁；已启动的外部进程结果将被拒绝落库。', okButtonProps: { danger: true }, onOk: () => mutate.mutateAsync('cancel') })}>取消</Button>}{run && retryable.has(run.status) && <Button type="primary" onClick={() => mutate.mutate('retry')}>重新入队</Button>}<Button icon={<ReloadOutlined />} onClick={() => void query.refetch()}>刷新</Button></Space>
    </div>
    <QueryState loading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
      {run && <>
        {run.failureCode && <Alert type="error" showIcon message={run.failureCode} description={run.failureMessage} />}
        <Card variant="borderless">
          <Descriptions bordered size="small" column={3}>
            <Descriptions.Item label="Run ID" span={3}>{run.id}</Descriptions.Item>
            <Descriptions.Item label="Agent">{run.agentKey} v{run.agentVersion}</Descriptions.Item>
            <Descriptions.Item label="状态"><Tag>{run.status}</Tag></Descriptions.Item>
            <Descriptions.Item label="尝试">{run.attemptNumber}/{run.maxAttempts}</Descriptions.Item>
            <Descriptions.Item label="Runtime">{run.runtimeVersion ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="定义版本">{run.agentDefinitionVersion}</Descriptions.Item>
            <Descriptions.Item label="Prompt 版本">{run.promptVersion}</Descriptions.Item>
            <Descriptions.Item label="Worker">{run.workerId ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="心跳">{run.heartbeatAt ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="租约截止">{run.leaseExpiresAt ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="Correlation ID" span={3}>{run.correlationId}</Descriptions.Item>
          </Descriptions>
        </Card>
        <Row gutter={16} style={{ marginTop: 16 }}>
          <Col xs={24} xl={12}>
            <Card title="状态历史" variant="borderless"><Timeline items={run.statusEvents.map((event) => ({ color: ['failed', 'timed_out', 'dead_letter'].includes(event.toStatus) ? 'red' : 'blue', children: <div><Text strong>{event.fromStatus ?? 'created'} → {event.toStatus}</Text><br /><Text type="secondary">{new Date(event.changedAt).toLocaleString()} · Attempt {event.attemptNumber}</Text>{event.failureCode && <Paragraph type="danger">{event.failureCode} · {event.failureMessage}</Paragraph>}</div> }))} /></Card>
            <Card title="实际使用来源" variant="borderless" style={{ marginTop: 16 }}><Timeline items={run.sources.map((source) => ({ children: <><Text strong>{source.sourceType} · {source.displayName}</Text><br /><Text code>{source.sourceHash}</Text></> }))} /></Card>
          </Col>
          <Col xs={24} xl={12}>
            <Card title="输入与 ContextSnapshot" variant="borderless"><pre className="agent-json">{JSON.stringify(run.inputPayload, null, 2)}</pre></Card>
            <Card title="输出与 Schema 校验" variant="borderless" style={{ marginTop: 16 }}>
              <Space wrap><Tag color={run.repairAttempted ? 'orange' : 'default'}>修复重试：{run.repairAttempted ? '是' : '否'}</Tag><Tag>Token：{run.tokenUsage ? JSON.stringify(run.tokenUsage) : 'CLI 未提供'}</Tag></Space>
              {run.validationErrors.length > 0 && <Alert type="warning" message="校验错误" description={run.validationErrors.join('；')} />}
              <pre className="agent-json">{JSON.stringify(run.outputPayload, null, 2)}</pre>
            </Card>
          </Col>
        </Row>
        <Collapse style={{ marginTop: 16 }} items={[
          { key: 'prompt', label: 'Prompt 快照', children: <pre className="agent-json">{run.promptSnapshot}</pre> },
          { key: 'stdout', label: 'stdout 摘要（受限）', children: <pre className="agent-json">{run.rawStdout || '—'}</pre> },
          { key: 'stderr', label: 'stderr 摘要（受限）', children: <pre className="agent-json">{run.rawStderr || '—'}</pre> },
        ]} />
        <Divider />
        <Space><Text type="secondary">ContextSnapshot：{run.contextSnapshotId}</Text>{run.feishuMessageId && <Button type="link" onClick={() => navigate(`/inbox/${run.feishuMessageId}`)}>来源消息</Button>}{run.candidateId && <Tag color="green">Candidate {run.candidateId}</Tag>}</Space>
      </>}
    </QueryState>
  </div>;
}
