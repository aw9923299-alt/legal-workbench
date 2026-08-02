import { ReloadOutlined, RobotOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Button, Card, Select, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { QueryState } from '../components/QueryState';
import { legalApi } from '../services/api';
import { useRealtimeStatus } from '../services/RealtimeProvider';
import type { AgentRunRecord, AgentRunStatus } from '../types/api';

const { Title, Text } = Typography;
const statusColor: Record<string, string> = { completed: 'green', failed: 'red', timed_out: 'red', dead_letter: 'volcano', cancelled: 'default', running: 'blue', preparing: 'blue', validating: 'cyan', queued: 'gold' };

function duration(run: AgentRunRecord): string {
  const start = run.startedAt ? new Date(run.startedAt).getTime() : new Date(run.createdAt).getTime();
  const end = run.finishedAt ? new Date(run.finishedAt).getTime() : Date.now();
  return `${Math.max(Math.round((end - start) / 1000), 0)} 秒`;
}

export default function AgentCenterPage() {
  const navigate = useNavigate();
  const realtime = useRealtimeStatus();
  const [status, setStatus] = useState<AgentRunStatus>();
  const query = useQuery({
    queryKey: ['agent-runs', status],
    queryFn: () => legalApi.listAgentRuns(status),
    refetchInterval: realtime.pollingInterval,
  });
  const columns: ColumnsType<AgentRunRecord> = [
    { title: 'Run ID', dataIndex: 'id', width: 170, render: (value: string) => <Button type="link" onClick={() => navigate(`/agent-runs/${value}`)}>{value.slice(0, 12)}…</Button> },
    { title: 'Agent', width: 190, render: (_, run) => <div className="agent-name"><RobotOutlined /><div><strong>{run.agentKey}</strong><span>v{run.agentVersion}</span></div></div> },
    { title: '来源消息', dataIndex: 'feishuMessageId', width: 180, render: (value: string | null) => value ? <Button type="link" onClick={() => navigate(`/inbox/${value}`)}>{value.slice(0, 12)}…</Button> : '—' },
    { title: '状态', dataIndex: 'status', width: 120, render: (value: string) => <Tag color={statusColor[value]}>{value}</Tag> },
    { title: '开始时间', dataIndex: 'startedAt', width: 170, render: (value: string | null) => value ? new Date(value).toLocaleString() : '—' },
    { title: '运行时长', width: 100, render: (_, run) => duration(run) },
    { title: '尝试', width: 80, render: (_, run) => `${run.attemptNumber}/${run.maxAttempts}` },
    { title: '失败码', dataIndex: 'failureCode', width: 190, render: (value: string | null) => value ? <Tag color="red">{value}</Tag> : '—' },
    { title: 'Worker', dataIndex: 'workerId', width: 140, render: (value: string | null) => value ?? '—' },
    { title: 'Correlation ID', dataIndex: 'correlationId', width: 200 },
  ];
  return <div className="page">
    <div className="page-title-row">
      <div><span className="eyebrow">CONTROLLED CODEX RUNTIME</span><Title level={2}>Agent 运行中心</Title><Text type="secondary">查看真实状态迁移、租约、版本、授权来源、校验和失败恢复。</Text></div>
      <Space><Tag color={realtime.connected ? 'green' : 'orange'}>{realtime.connected ? '实时' : '轮询'}</Tag><Button icon={<ReloadOutlined />} onClick={() => void query.refetch()}>刷新</Button></Space>
    </div>
    <Card variant="borderless">
      <Space style={{ marginBottom: 16 }}><Select allowClear value={status} onChange={setStatus} placeholder="运行状态" style={{ width: 200 }} options={['queued', 'preparing', 'running', 'validating', 'completed', 'needs_more_information', 'failed', 'timed_out', 'cancelled', 'dead_letter'].map((value) => ({ value, label: value }))} /><Text type="secondary">最近更新：{query.dataUpdatedAt ? new Date(query.dataUpdatedAt).toLocaleString() : '—'}</Text></Space>
      <QueryState loading={query.isLoading} error={query.error} empty={!query.data?.length} onRetry={() => void query.refetch()}>
        <Table rowKey="id" columns={columns} dataSource={query.data} scroll={{ x: 1600 }} pagination={{ pageSize: 20 }} />
      </QueryState>
    </Card>
  </div>;
}
