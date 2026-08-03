import {
  Alert,
  Badge,
  Button,
  Card,
  Empty,
  List,
  Space,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import {
  AlertOutlined,
  AuditOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  InboxOutlined,
  ReloadOutlined,
  TeamOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import MetricStrip from '../components/MetricStrip';
import { QueryState } from '../components/QueryState';
import { legalApi } from '../services/api';
import type { DashboardItem, DashboardToday } from '../types/api';

const { Title, Text } = Typography;

type QueueKey = Exclude<keyof DashboardToday, 'generatedAt'>;

const queueDefinitions: Array<{ key: QueueKey; label: string }> = [
  { key: 'todayMustHandle', label: '今日必须处理' },
  { key: 'overdue', label: '已逾期' },
  { key: 'pendingCandidates', label: '待确认 Candidate' },
  { key: 'analysisFailed', label: '分析失败' },
  { key: 'waitingOthers', label: '等待他人' },
  { key: 'upcomingDeadlines', label: '即将到期' },
  { key: 'pendingOutboundReview', label: '待审核外发' },
  { key: 'systemAbnormal', label: '系统异常' },
];

function formatDateTime(value: string | null): string | null {
  if (!value) return null;
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value));
}

function DashboardQueue({ items }: { items: DashboardItem[] }) {
  const navigate = useNavigate();
  if (items.length === 0) {
    return <Empty className="dashboard-empty" description="当前队列为空" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <List
      className="dashboard-queue-list"
      dataSource={items}
      renderItem={(item) => (
        <List.Item className="dashboard-queue-item">
          <button type="button" className="dashboard-item-button" onClick={() => navigate(item.href)}>
            <span className="dashboard-item-heading">
              <strong>{item.title}</strong>
              <Tag bordered={false}>{item.status}</Tag>
            </span>
            {item.description && <span className="dashboard-item-description">{item.description}</span>}
            <span className="dashboard-item-meta">
              {item.dueAt && <span>截止：{formatDateTime(item.dueAt)}</span>}
              {item.waitingSince && <span>等待自：{formatDateTime(item.waitingSince)}</span>}
              <span>类型：{item.objectType}</span>
            </span>
            <span className="dashboard-ranking-reasons">
              {item.rankingReasons.map((reason) => <Tag key={reason} color={item.isOverdue ? 'error' : 'blue'}>{reason}</Tag>)}
              {item.aiSuggestedPriority && (
                <Tag color="default">AI 建议优先级：{item.aiSuggestedPriority}（仅供参考）</Tag>
              )}
            </span>
          </button>
        </List.Item>
      )}
    />
  );
}

export default function DashboardPage() {
  const [activeQueue, setActiveQueue] = useState<QueueKey>('todayMustHandle');
  const dashboard = useQuery({
    queryKey: ['dashboard', 'today'],
    queryFn: () => legalApi.getDashboardToday(),
    refetchInterval: 30_000,
  });

  const tabs = useMemo(() => queueDefinitions.map(({ key, label }) => ({
    key,
    label: <span>{label} <Badge count={dashboard.data?.[key].length ?? 0} showZero size="small" /></span>,
    children: <DashboardQueue items={dashboard.data?.[key] ?? []} />,
  })), [dashboard.data]);

  const generatedAt = dashboard.data ? formatDateTime(dashboard.data.generatedAt) : null;
  const systemProblems = dashboard.data?.systemAbnormal.length ?? 0;

  return (
    <div className="page dashboard-page">
      <div className="page-title-row">
        <div>
          <span className="eyebrow">POSTGRESQL · DETERMINISTIC QUEUE</span>
          <Title level={2}>今日工作台</Title>
          <Text type="secondary">硬期限、逾期、法律风险、人工确认优先级、等待时长和创建时间共同决定顺序。</Text>
        </div>
        <Button icon={<ReloadOutlined />} loading={dashboard.isFetching} onClick={() => void dashboard.refetch()}>
          刷新队列
        </Button>
      </div>

      <QueryState loading={dashboard.isLoading} error={dashboard.error} onRetry={() => void dashboard.refetch()}>
        {dashboard.data && (
          <>
            <Alert
              className="sync-alert"
              type={systemProblems > 0 ? 'warning' : 'info'}
              showIcon
              message={systemProblems > 0 ? `检测到 ${systemProblems} 项系统异常` : '工作队列已从业务事实库生成'}
              description={`生成时间：${generatedAt ?? '未知'}。AI 优先级只作为建议展示，不参与覆盖人工确认值。`}
              action={systemProblems > 0 ? <Button size="small" onClick={() => setActiveQueue('systemAbnormal')}>查看异常</Button> : undefined}
            />

            <MetricStrip items={[
              {
                label: '今日必须处理', value: dashboard.data.todayMustHandle.length,
                hint: '按确定性规则排序', tone: 'critical', icon: <ClockCircleOutlined />,
                onClick: () => setActiveQueue('todayMustHandle'),
              },
              {
                label: '已逾期', value: dashboard.data.overdue.length,
                hint: '包含未满足的有效期限', tone: 'warning', icon: <ExclamationCircleOutlined />,
                onClick: () => setActiveQueue('overdue'),
              },
              {
                label: '待确认 Candidate', value: dashboard.data.pendingCandidates.length,
                hint: '必须由法务人工处置', tone: 'info', icon: <InboxOutlined />,
                onClick: () => setActiveQueue('pendingCandidates'),
              },
              {
                label: '系统异常', value: dashboard.data.systemAbnormal.length,
                hint: '连接、任务与死信状态', tone: systemProblems > 0 ? 'critical' : 'neutral', icon: <WarningOutlined />,
                onClick: () => setActiveQueue('systemAbnormal'),
              },
            ]} />

            <Card className="work-queue-card" variant="borderless">
              <div className="section-toolbar">
                <div>
                  <Title level={4}>持续跟踪队列</Title>
                  <Space size="middle" wrap>
                    <Text type="secondary"><AlertOutlined /> 法律风险优先</Text>
                    <Text type="secondary"><TeamOutlined /> 等待时长可见</Text>
                    <Text type="secondary"><AuditOutlined /> 外发仍需审核</Text>
                  </Space>
                </div>
              </div>
              <Tabs
                activeKey={activeQueue}
                onChange={(key) => setActiveQueue(key as QueueKey)}
                items={tabs}
              />
            </Card>
          </>
        )}
      </QueryState>
    </div>
  );
}
