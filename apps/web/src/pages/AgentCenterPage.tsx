import { Alert, Button, Card, Descriptions, Drawer, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ReloadOutlined, RobotOutlined } from '@ant-design/icons';
import { useCallback, useEffect, useState } from 'react';
import DataBoundaryBanner from '../components/DataBoundaryBanner';
import PageHeader from '../components/PageHeader';
import ResponsiveCollection from '../components/ResponsiveCollection';
import StatePanel from '../components/StatePanel';
import { legalApi } from '../services/api';
import { classifyApiFailure, type ApiFailureState } from '../services/apiFailure';
import { agentRunStatusLabels, technicalStatusLabel } from '../services/apiLabels';
import type { AgentRunRecord } from '../types/api';

const { Title, Text } = Typography;

const statusColor: Record<string, string> = {
  completed: 'green',
  failed: 'red',
  timed_out: 'red',
  dead_letter: 'volcano',
  running: 'blue',
  preparing: 'blue',
  validating: 'cyan',
  queued: 'gold',
  needs_more_information: 'gold',
  cancelled: 'default',
};

type AgentCenterProps = {
  runId?: string;
  onRunSelected: (runId: string) => void;
  onRunClosed: () => void;
};

function runStatus(value: string) {
  return <Tag color={statusColor[value]}>{technicalStatusLabel(agentRunStatusLabels, value)}</Tag>;
}

function timestamp(value: string | null) {
  return value ? new Date(value).toLocaleString() : '—';
}

export default function AgentCenterPage({ runId, onRunSelected, onRunClosed }: AgentCenterProps) {
  const [runs, setRuns] = useState<AgentRunRecord[]>([]);
  const [selected, setSelected] = useState<AgentRunRecord>();
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [failure, setFailure] = useState<ApiFailureState>();
  const [detailFailure, setDetailFailure] = useState<ApiFailureState>();

  const load = useCallback(async () => {
    setLoading(true);
    setFailure(undefined);
    try {
      setRuns(await legalApi.listAgentRuns());
    } catch (reason) {
      setRuns([]);
      setFailure(classifyApiFailure(reason, 'Agent 执行数据', 'Agent 执行记录加载失败', '加载 Agent 执行记录失败'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!runId) {
      setSelected(undefined);
      setDetailFailure(undefined);
      return;
    }
    let current = true;
    const loadDetail = async () => {
      setDetailLoading(true);
      setDetailFailure(undefined);
      try {
        const fromList = runs.find((run) => run.id === runId);
        const value = fromList ?? await legalApi.getAgentRun(runId);
        if (current) setSelected(value);
      } catch (reason) {
        if (current) {
          setSelected(undefined);
          setDetailFailure(classifyApiFailure(reason, 'Agent 执行详情', 'Agent 执行详情加载失败', '加载 Agent 执行详情失败'));
        }
      } finally {
        if (current) setDetailLoading(false);
      }
    };
    void loadDetail();
    return () => { current = false; };
  }, [runId, runs]);

  const columns: ColumnsType<AgentRunRecord> = [
    { title: 'Agent', render: (_, run) => <div className="agent-name"><RobotOutlined /><div><strong>{run.agentKey}</strong><span>v{run.agentVersion}</span></div></div> },
    { title: '状态', dataIndex: 'status', width: 194, render: (value: string) => runStatus(value) },
    { title: '尝试', width: 76, render: (_, run) => `${run.attemptNumber}/${run.maxAttempts}` },
    { title: '来源消息', dataIndex: 'feishuMessageId', render: (value: string | null) => value ?? '—' },
    { title: '开始时间', dataIndex: 'startedAt', width: 190, render: timestamp },
    { title: '失败代码', dataIndex: 'failureCode', render: (value: string | null) => value ?? '—' },
    { title: '操作', width: 120, render: (_, run) => <Button type="link" aria-label={`查看执行记录：${run.id}`} onClick={() => onRunSelected(run.id)}>查看详情</Button> },
  ];

  const renderCard = (run: AgentRunRecord, className: string) => (
    <article className={className}>
      <span className="run-card-id">{run.id}</span>
      <h3>{run.agentKey} · v{run.agentVersion}</h3>
      <div>{runStatus(run.status)}</div>
      <dl>
        <div><dt>尝试</dt><dd>尝试 {run.attemptNumber}/{run.maxAttempts}</dd></div>
        <div><dt>开始时间</dt><dd>{timestamp(run.startedAt)}</dd></div>
        <div><dt>来源消息</dt><dd>{run.feishuMessageId ?? '—'}</dd></div>
        <div><dt>失败代码</dt><dd>{run.failureCode ?? '—'}</dd></div>
      </dl>
      <Button type="link" aria-label={`查看执行记录：${run.id}`} onClick={() => onRunSelected(run.id)}>查看执行详情</Button>
    </article>
  );

  return (
    <div className="page agent-center-page">
      <PageHeader
        eyebrow="系统与审计"
        title="Agent 执行记录"
        description="查看受控 Codex Runtime 的版本、授权来源、运行状态和失败记录。"
        primaryAction={<Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新执行记录</Button>}
      />
      <DataBoundaryBanner
        className="data-boundary-banner--mobile-detail"
        variant="api"
        title="由服务接口提供"
        description={<span>状态仅说明受控运行进度。<strong>运行完成不等于法律结论已确认</strong>，所有业务结论仍需法务人工确认。</span>}
      />
      {loading ? (
        <StatePanel variant="loading" title="正在加载 Agent 执行记录" description="等待服务接口返回运行审计数据。" />
      ) : failure ? (
        <StatePanel {...failure} action={<Button onClick={() => void load()}>重试</Button>} />
      ) : runs.length === 0 ? (
        <StatePanel variant="empty" title="暂无 Agent 执行记录" description="当前没有可展示的受控运行记录。" />
      ) : (
        <Card className="agent-runs-surface" variant="borderless">
          <ResponsiveCollection
            className="agent-runs-collection"
            items={runs}
            getKey={(run) => run.id}
            renderDesktop={(items) => <Table className="agent-runs-table" rowKey="id" columns={columns} dataSource={[...items]} pagination={false} tableLayout="fixed" />}
            renderCompact={(run) => renderCard(run, 'run-compact-card')}
            renderMobile={(run) => renderCard(run, 'run-mobile-card')}
          />
        </Card>
      )}

      <Drawer
        className="agent-detail-drawer"
        width={900}
        open={Boolean(runId)}
        onClose={onRunClosed}
        title="Agent 执行详情"
        extra={<Button onClick={onRunClosed}>返回执行记录</Button>}
      >
        {detailLoading ? (
          <StatePanel variant="loading" title="正在加载 Agent 执行详情" />
        ) : detailFailure ? (
          <StatePanel {...detailFailure} action={<Button onClick={onRunClosed}>返回执行记录</Button>} />
        ) : selected ? (
          <div className="agent-run-detail">
            <Alert type="info" showIcon message={runStatus(selected.status)} description="运行状态是确定性执行记录，不构成法律结论确认。" />
            <Descriptions bordered size="small" column={1}>
              <Descriptions.Item label="Run ID">{selected.id}</Descriptions.Item>
              <Descriptions.Item label="Agent">{selected.agentKey} v{selected.agentVersion}</Descriptions.Item>
              <Descriptions.Item label="尝试次数">{selected.attemptNumber}/{selected.maxAttempts}</Descriptions.Item>
              <Descriptions.Item label="开始时间">{timestamp(selected.startedAt)}</Descriptions.Item>
              <Descriptions.Item label="结束时间">{timestamp(selected.finishedAt)}</Descriptions.Item>
              <Descriptions.Item label="ContextSnapshot">{selected.contextSnapshotId}</Descriptions.Item>
              <Descriptions.Item label="Correlation ID">{selected.correlationId}</Descriptions.Item>
              <Descriptions.Item label="失败代码">{selected.failureCode ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="失败原因">{selected.failureMessage ?? '—'}</Descriptions.Item>
            </Descriptions>
            <section className="agent-run-sources">
              <Title level={4}>实际授权来源</Title>
              <Space direction="vertical">{selected.sources.map((source) => <Text code key={`${source.sourceType}-${source.sourceId}`}>{source.sourceType}: {source.displayName} · {source.sourceHash.slice(0, 12)}</Text>)}</Space>
            </section>
            <section className="agent-run-output">
              <Title level={4}>结构化输出</Title>
              <pre className="agent-json" role="region" aria-label="结构化输出 JSON" tabIndex={0}>{JSON.stringify(selected.outputPayload, null, 2)}</pre>
            </section>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}
