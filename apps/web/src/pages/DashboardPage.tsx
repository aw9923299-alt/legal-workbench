import { Badge, Button, Card, Tabs, Typography } from 'antd';
import { AlertOutlined, ClockCircleOutlined, ExclamationCircleOutlined, InboxOutlined } from '@ant-design/icons';
import { useMemo } from 'react';
import { inboxItems, tasks } from '../data/mock';
import type { Task } from '../types/domain';
import MetricStrip from '../components/MetricStrip';
import TaskTable from '../components/TaskTable';
import AiAssistant from '../components/AiAssistant';
import DataBoundaryBanner from '../components/DataBoundaryBanner';
import PageHeader from '../components/PageHeader';

const { Title, Text } = Typography;

export default function DashboardPage({ onOpenTask, onOpenInbox }: { onOpenTask: (task: Task) => void; onOpenInbox: () => void }) {
  const focusTasks = useMemo(() => tasks.filter((task) => ['紧急', '高'].includes(task.priority)), []);
  const summary = useMemo(() => ({
    overdue: tasks.filter((task) => task.deadline?.startsWith('2026-07')).length,
    urgent: focusTasks.length,
    highRisk: tasks.filter((task) => ['严重', '高'].includes(task.legalRisk)).length,
    pendingConfirmation: inboxItems.length,
  }), []);

  return (
    <div className="page dashboard-page">
      <PageHeader
        eyebrow="演示快照 · 2026.08.01"
        title="今日工作台"
        description="先处理硬期限、重大风险和等待人工决定的事项。"
        primaryAction={<Button type="primary" onClick={onOpenInbox}>处理待确认消息</Button>}
      />

      <DataBoundaryBanner
        variant="demo"
        title="演示数据 / 非实时业务事实"
        description="当前首页仅用于演示信息层级；真实同步、授权范围和服务健康应以系统状态接口为准。专业 Agent、知识检索和真实外发均未在此页面表示为已上线。"
      />

      <main className="dashboard-main">
        <Card className="work-queue-card" variant="borderless">
          <div className="section-toolbar">
            <div>
              <Title level={4}>下一步工作队列</Title>
              <Text type="secondary">按紧迫度、法律风险、业务影响与等待时长综合排序</Text>
            </div>
          </div>
          <Tabs
            defaultActiveKey="focus"
            items={[
              { key: 'focus', label: <span>应立即处理 <Badge count={summary.urgent} size="small" /></span>, children: <TaskTable data={focusTasks} onOpen={onOpenTask} /> },
              { key: 'waiting', label: '等待回复', children: <TaskTable data={tasks.filter((task) => task.waitingFor)} onOpen={onOpenTask} /> },
              { key: 'risk', label: '风险升级', children: <TaskTable data={tasks.filter((task) => ['严重', '高'].includes(task.legalRisk))} onOpen={onOpenTask} /> },
            ]}
          />
        </Card>

        <div className="dashboard-support-grid">
          <Card className="side-card" variant="borderless" title="即将发生的节点">
            <div className="deadline-list">
              <div><time>14:00</time><span>主播解约事实核查会</span></div>
              <div><time>16:00</time><span>解约风险意见内部截止</span></div>
              <div><time>18:00</time><span>直播广告脚本定稿</span></div>
              <div><time>明日</time><span>音乐版权申诉材料截止</span></div>
            </div>
          </Card>
          <Card className="side-card" variant="borderless" title={<span>待确认消息（演示） <Badge count={inboxItems.length} /></span>} extra={<Button type="link" onClick={onOpenInbox}>进入收件箱</Button>}>
            {inboxItems.slice(0, 3).map((item) => (
              <button
                className="inbox-mini-item"
                key={item.id}
                aria-label={`查看待确认消息：${item.chatName}`}
                onClick={onOpenInbox}
              >
                <span className="inbox-mini-top"><strong>{item.aiDecision}</strong><em>{Math.round(item.confidence * 100)}%</em></span>
                <span>{item.summary}</span>
                <small>{item.chatName} · {item.sentAt}</small>
              </button>
            ))}
          </Card>
        </div>

        <MetricStrip
          caption="演示快照口径：统计仅来自本页安全演示任务与待确认消息，不代表实时业务数据。"
          items={[
            { label: '已逾期', value: summary.overdue, hint: '需优先复核期限', tone: 'warning', icon: <ExclamationCircleOutlined /> },
            { label: '紧急/高优先级', value: summary.urgent, hint: '按演示队列计算', tone: 'critical', icon: <ClockCircleOutlined /> },
            { label: '高/严重风险', value: summary.highRisk, hint: '含重大风险样例', tone: 'critical', icon: <AlertOutlined /> },
            { label: '待人工确认', value: summary.pendingConfirmation, hint: '来自演示收件箱', tone: 'info', icon: <InboxOutlined /> },
          ]}
        />

        <AiAssistant />

        <Card className="week-card" variant="borderless">
          <div className="section-toolbar compact">
            <div><Title level={4}>本周处理概览（演示）</Title><Text type="secondary">不以数量替代质量，仅用于识别积压与阻塞</Text></div>
          </div>
          <div className="week-grid">
            <div><strong>26</strong><span>新识别事项</span></div>
            <div><strong>18</strong><span>确认创建任务</span></div>
            <div><strong>13</strong><span>本周已完成</span></div>
            <div><strong>4.6h</strong><span>平均首次响应</span></div>
            <div><strong>3</strong><span>当前阻塞事项</span></div>
          </div>
        </Card>
      </main>
    </div>
  );
}
