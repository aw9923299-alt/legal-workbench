import { Alert, Button, Card, Descriptions, Empty, Modal, Space, Spin, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ReloadOutlined, RobotOutlined } from '@ant-design/icons';
import { useCallback, useEffect, useState } from 'react';
import { legalApi } from '../services/api';
import type { AgentRunRecord } from '../types/api';

const { Title, Text, Paragraph } = Typography;

const statusColor: Record<string, string> = {
  completed: 'green', failed: 'red', timed_out: 'red', dead_letter: 'volcano',
  running: 'blue', preparing: 'blue', validating: 'cyan', queued: 'gold',
};

export default function AgentCenterPage({ initialRunId }: { initialRunId?: string }) {
  const [runs, setRuns] = useState<AgentRunRecord[]>([]);
  const [selected, setSelected] = useState<AgentRunRecord>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const values = await legalApi.listAgentRuns();
      setRuns(values);
      if (initialRunId) {
        setSelected(values.find((run) => run.id === initialRunId) ?? await legalApi.getAgentRun(initialRunId));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '加载 AgentRun 失败');
    } finally {
      setLoading(false);
    }
  }, [initialRunId]);

  useEffect(() => { void load(); }, [load]);

  const columns: ColumnsType<AgentRunRecord> = [
    { title: 'Agent', render: (_, run) => <div className="agent-name"><RobotOutlined /><div><strong>{run.agentKey}</strong><span>v{run.agentVersion}</span></div></div> },
    { title: '状态', dataIndex: 'status', render: (value: string) => <Tag color={statusColor[value]}>{value}</Tag> },
    { title: '尝试', render: (_, run) => `${run.attemptNumber}/${run.maxAttempts}` },
    { title: '飞书消息', dataIndex: 'feishuMessageId', render: (value: string | null) => value ?? '—' },
    { title: '开始时间', dataIndex: 'startedAt', render: (value: string | null) => value ? new Date(value).toLocaleString() : '—' },
    { title: '失败代码', dataIndex: 'failureCode', render: (value: string | null) => value ?? '—' },
    { title: '操作', render: (_, run) => <Button type="link" onClick={() => setSelected(run)}>查看详情</Button> },
  ];

  return <div className="page">
    <div className="page-title-row">
      <div><span className="eyebrow">CONTROLLED CODEX RUNTIME</span><Title level={2}>Agent 中心</Title><Text type="secondary">查看消息研判 Agent 的版本、授权来源、运行状态与失败记录。</Text></div>
      <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
    </div>
    <Alert type="info" showIcon message="当前正式 Agent：message_judgement v1.0.0" description="仅使用本次 ContextSnapshot；结果必须经过 Schema 和业务约束校验，始终由法务人工确认。" />
    {error && <Alert style={{ marginTop: 12 }} type="error" showIcon message={error} action={<Button onClick={() => void load()}>重试</Button>} />}
    <Card title="AgentRun 执行记录" bordered={false} style={{ marginTop: 14 }}>
      <Spin spinning={loading}>
        {!loading && runs.length === 0 ? <Empty description="暂无 AgentRun" /> : <Table rowKey="id" columns={columns} dataSource={runs} pagination={{ pageSize: 20 }} />}
      </Spin>
    </Card>
    <Modal open={Boolean(selected)} title="AgentRun 详情" width={900} footer={null} onCancel={() => setSelected(undefined)}>
      {selected && <>
        <Descriptions bordered size="small" column={2}>
          <Descriptions.Item label="Run ID" span={2}>{selected.id}</Descriptions.Item>
          <Descriptions.Item label="Agent">{selected.agentKey} v{selected.agentVersion}</Descriptions.Item>
          <Descriptions.Item label="状态"><Tag color={statusColor[selected.status]}>{selected.status}</Tag></Descriptions.Item>
          <Descriptions.Item label="尝试次数">{selected.attemptNumber}/{selected.maxAttempts}</Descriptions.Item>
          <Descriptions.Item label="心跳">{selected.heartbeatAt ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="ContextSnapshot" span={2}>{selected.contextSnapshotId}</Descriptions.Item>
          <Descriptions.Item label="Correlation ID" span={2}>{selected.correlationId}</Descriptions.Item>
          <Descriptions.Item label="失败代码">{selected.failureCode ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="失败原因">{selected.failureMessage ?? '—'}</Descriptions.Item>
        </Descriptions>
        <Title level={5}>实际授权来源</Title>
        <Space direction="vertical" style={{ width: '100%' }}>{selected.sources.map((source) => <Text code key={`${source.sourceType}-${source.sourceId}`}>{source.sourceType}: {source.displayName} · {source.sourceHash.slice(0, 12)}</Text>)}</Space>
        <Title level={5}>结构化输出</Title>
        <Paragraph><pre className="agent-json">{JSON.stringify(selected.outputPayload, null, 2)}</pre></Paragraph>
      </>}
    </Modal>
  </div>;
}
