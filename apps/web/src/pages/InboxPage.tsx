import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Card, DatePicker, Input, Modal, Progress, Select, Space, Table, Tabs, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { QueryState } from '../components/QueryState';
import {
  clearMutationContext,
  getOrCreateMutationContext,
  isDefinitiveMutationFailure,
  legalApi,
} from '../services/api';
import { categoryLabels } from '../services/apiLabels';
import { useRealtimeStatus } from '../services/RealtimeProvider';
import type { FeishuMessageStatus, FeishuMessageSummary } from '../types/api';
import { matchesInboxView, statusesForInboxView, type InboxView } from './inboxFilters';

const { Title, Text } = Typography;

const views: Array<{ key: InboxView; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'pending_analysis', label: '待分析' },
  { key: 'queued', label: '排队中' },
  { key: 'analysing', label: '分析中' },
  { key: 'pending_confirmation', label: '待确认' },
  { key: 'processed', label: '已处理' },
  { key: 'ignored', label: '已忽略' },
  { key: 'failed', label: '失败' },
  { key: 'dead_letter', label: '死信' },
];

const stateColors: Record<string, string> = {
  received: 'default', queued_for_analysis: 'gold', context_prepared: 'gold', agent_queued: 'gold',
  analysing: 'blue', candidate_created: 'green', ignored: 'default', analysis_failed: 'red', dead_letter: 'volcano',
};

export default function InboxPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const realtime = useRealtimeStatus();
  const [view, setView] = useState<InboxView>('all');
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<string>();
  const [chatId, setChatId] = useState('');
  const [dates, setDates] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null);
  const query = useQuery({
    queryKey: ['inbox', view, search, category, chatId, dates?.[0]?.toISOString(), dates?.[1]?.toISOString()],
    queryFn: () => legalApi.listMessages({
      statuses: statusesForInboxView(view) as FeishuMessageStatus[] | undefined,
      search: search || undefined,
      category,
      chatId: chatId || undefined,
      from: dates?.[0]?.startOf('day').toISOString(),
      to: dates?.[1]?.endOf('day').toISOString(),
    }),
    refetchInterval: realtime.pollingInterval,
  });
  const items = useMemo(
    () => (query.data ?? []).filter((item) => matchesInboxView(item, view)),
    [query.data, view],
  );

  const analyse = useMutation({
    mutationFn: async ({ item, retry }: { item: FeishuMessageSummary; retry: boolean }) => {
      const actionKey = `${retry ? 'retry' : 'analyse'}:${item.id}`;
      const context = getOrCreateMutationContext(actionKey, { messageId: item.id, retry });
      try {
        const result = retry
          ? await legalApi.retryMessageAnalysis(item.id, context)
          : await legalApi.analyseMessage(item.id, context);
        clearMutationContext(actionKey);
        return result;
      } catch (error) {
        if (isDefinitiveMutationFailure(error)) clearMutationContext(actionKey);
        throw error;
      }
    },
    onSuccess: () => {
      message.success('分析任务已进入持久化队列');
      void queryClient.invalidateQueries({ queryKey: ['inbox'] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : '操作失败'),
  });

  const resolve = useMutation({
    mutationFn: async ({ item, action }: { item: FeishuMessageSummary; action: 'information_only' | 'ignore' }) => {
      if (!item.candidateId) throw new Error('该消息没有可处理的 Candidate');
      const candidate = await legalApi.getCandidate(item.candidateId);
      const actionKey = `resolve:${candidate.id}:${action}`;
      const context = getOrCreateMutationContext(actionKey, { action, version: candidate.version });
      try {
        const result = await legalApi.resolveCandidate(candidate.id, {
          candidateVersion: candidate.version, action,
        }, context);
        clearMutationContext(actionKey);
        return result;
      } catch (error) {
        if (isDefinitiveMutationFailure(error)) clearMutationContext(actionKey);
        throw error;
      }
    },
    onSuccess: () => {
      message.success('人工处理结果已保存');
      void queryClient.invalidateQueries({ queryKey: ['inbox'] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : '处理失败'),
  });

  const columns: ColumnsType<FeishuMessageSummary> = [
    {
      title: '消息摘要', dataIndex: 'plainText', width: 330,
      render: (value: string | null, item) => <button className="text-link message-summary" onClick={() => navigate(`/inbox/${item.id}`)}>{value || item.unsupportedReason || '无可读正文'}</button>,
    },
    { title: '来源群聊', dataIndex: 'chatId', width: 150, render: (value: string | null) => value ?? '—' },
    { title: '发起人', dataIndex: 'senderId', width: 130, render: (value: string | null) => value ?? '—' },
    { title: '消息时间', dataIndex: 'sentAt', width: 165, render: (value: string | null) => value ? new Date(value).toLocaleString() : '—' },
    { title: '类型', dataIndex: 'messageType', width: 90 },
    { title: '处理状态', dataIndex: 'status', width: 130, render: (value: string) => <Tag color={stateColors[value]}>{value}</Tag> },
    { title: 'Agent', dataIndex: 'agentStatus', width: 110, render: (value: string | null) => value ? <Tag>{value}</Tag> : '—' },
    { title: 'Candidate', dataIndex: 'candidateStatus', width: 130, render: (value: string | null) => value ?? '—' },
    { title: '置信度', dataIndex: 'confidence', width: 110, render: (value: number | null) => value == null ? '—' : <Progress percent={Math.round(value * 100)} size="small" /> },
    { title: '建议分类', dataIndex: 'suggestedCategory', width: 120, render: (value: string | null) => value ? categoryLabels[value] ?? value : '—' },
    { title: '建议截止', dataIndex: 'suggestedDeadline', width: 150, render: (value: string | null) => value ?? '—' },
    { title: '错误/重试', width: 180, render: (_, item) => item.failureCode ? <div><Tag color="red">{item.failureCode}</Tag><Text type="secondary">{item.analysisAttempts} 次</Text></div> : `${item.analysisAttempts} 次` },
    {
      title: '操作', fixed: 'right', width: 250,
      render: (_, item) => <Space size={4} wrap>
        <Button size="small" onClick={() => navigate(`/inbox/${item.id}`)}>详情</Button>
        {item.status === 'received' && <Button size="small" type="primary" loading={analyse.isPending} onClick={() => analyse.mutate({ item, retry: false })}>分析</Button>}
        {['analysis_failed', 'dead_letter'].includes(item.status) && <Button size="small" danger loading={analyse.isPending} onClick={() => analyse.mutate({ item, retry: true })}>重试</Button>}
        {item.candidateStatus === 'pending_confirmation' && <>
          <Button size="small" onClick={() => resolve.mutate({ item, action: 'information_only' })}>仅供知悉</Button>
          <Button size="small" onClick={() => Modal.confirm({ title: '确认忽略这条消息？', content: '该人工决定会写入审计记录。', okText: '确认忽略', okButtonProps: { danger: true }, onOk: () => resolve.mutateAsync({ item, action: 'ignore' }) })}>忽略</Button>
        </>}
      </Space>,
    },
  ];

  return <div className="page">
    <div className="page-title-row">
      <div><span className="eyebrow">REAL FEISHU MESSAGE QUEUE</span><Title level={2}>AI 收件箱</Title><Text type="secondary">原始消息落库后立即可见，分析与人工确认状态来自 PostgreSQL。</Text></div>
      <Space><Tag color={realtime.connected ? 'green' : 'orange'}>{realtime.connected ? '实时连接正常' : '实时断开，轮询中'}</Tag><Button icon={<ReloadOutlined />} onClick={() => void query.refetch()}>刷新</Button></Space>
    </div>
    <Card variant="borderless" className="filter-card">
      <Tabs activeKey={view} items={views} onChange={(key) => setView(key as InboxView)} />
      <Space wrap>
        <Input allowClear prefix={<SearchOutlined />} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索消息正文" style={{ width: 240 }} />
        <Select allowClear value={category} onChange={setCategory} placeholder="建议分类" style={{ width: 160 }} options={Object.entries(categoryLabels).map(([value, label]) => ({ value, label }))} />
        <Input allowClear value={chatId} onChange={(event) => setChatId(event.target.value)} placeholder="群聊 ID" style={{ width: 180 }} />
        <DatePicker.RangePicker value={dates} onChange={(value) => setDates(value)} />
      </Space>
    </Card>
    <Card variant="borderless" style={{ marginTop: 14 }}>
      <QueryState loading={query.isLoading} error={query.error} empty={!items.length} onRetry={() => void query.refetch()}>
        <Table rowKey="id" columns={columns} dataSource={items} scroll={{ x: 2050 }} pagination={{ pageSize: 20 }} />
      </QueryState>
      <div className="updated-at">最近更新：{query.dataUpdatedAt ? new Date(query.dataUpdatedAt).toLocaleString() : '—'}</div>
    </Card>
  </div>;
}
