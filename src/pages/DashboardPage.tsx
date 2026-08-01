import { Alert, Badge, Button, Card, Segmented, Space, Tabs, Typography } from 'antd';
import { AlertOutlined, ClockCircleOutlined, ExclamationCircleOutlined, InboxOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useMemo, useState } from 'react';
import { inboxItems, tasks } from '../data/mock';
import type { Task } from '../types/domain';
import MetricStrip from '../components/MetricStrip';
import TaskTable from '../components/TaskTable';
import AiAssistant from '../components/AiAssistant';

const { Title, Text } = Typography;

export default function DashboardPage({ onOpenTask }: { onOpenTask: (task: Task) => void }) {
  const [scope, setScope] = useState('今天');
  const urgentTasks = useMemo(() => tasks.filter((task) => task.priority !== '低'), []);

  return (
    <div className="page dashboard-page">
      <div className="page-title-row">
        <div>
          <span className="eyebrow">SATURDAY · 2026.08.01</span>
          <Title level={2}>今日工作台</Title>
          <Text type="secondary">先处理高风险、临近截止和正在等待你行动的事项。</Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />}>同步飞书</Button>
          <Button type="primary" icon={<PlusOutlined />}>新建任务</Button>
        </Space>
      </div>

      <Alert
        className="sync-alert"
        type="info"
        showIcon
        message="飞书同步正常"
        description="已同步 42 个授权会话；最近同步 12:58。2 个敏感群聊已排除，私聊仅读取包含 @法务 或明确授权的线程。"
        action={<Button size="small">查看授权范围</Button>}
      />

      <MetricStrip items={[
        { label: '今日必须处理', value: 4, hint: '2 项将在 4 小时内到期', tone: 'critical', icon: <ClockCircleOutlined /> },
        { label: '已逾期', value: 1, hint: '最长逾期 22 小时', tone: 'warning', icon: <ExclamationCircleOutlined /> },
        { label: '高风险事项', value: 3, hint: '含 1 项严重风险', tone: 'critical', icon: <AlertOutlined /> },
        { label: '等待我确认', value: 6, hint: '新增 3 条 AI 判断', tone: 'info', icon: <InboxOutlined /> },
      ]} />

      <div className="dashboard-grid">
        <main className="dashboard-main">
          <Card className="work-queue-card" bordered={false}>
            <div className="section-toolbar">
              <div>
                <Title level={4}>下一步工作队列</Title>
                <Text type="secondary">按紧迫度、法律风险、业务影响与等待时长综合排序</Text>
              </div>
              <Segmented value={scope} onChange={(value) => setScope(String(value))} options={['今天', '本周', '全部']} />
            </div>
            <Tabs
              defaultActiveKey="focus"
              items={[
                { key: 'focus', label: <span>应立即处理 <Badge count={4} size="small" /></span>, children: <TaskTable data={urgentTasks} onOpen={onOpenTask} /> },
                { key: 'waiting', label: '等待回复', children: <TaskTable data={tasks.filter((task) => task.waitingFor)} onOpen={onOpenTask} /> },
                { key: 'risk', label: '风险升级', children: <TaskTable data={tasks.filter((task) => ['严重', '高'].includes(task.legalRisk))} onOpen={onOpenTask} /> },
              ]}
            />
          </Card>

          <Card className="week-card" bordered={false}>
            <div className="section-toolbar compact">
              <div><Title level={4}>本周处理概览</Title><Text type="secondary">不以数量替代质量，仅用于识别积压与阻塞</Text></div>
              <Button type="link">查看周报草稿</Button>
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

        <div className="dashboard-side">
          <AiAssistant />
          <Card className="side-card" title={<span>AI 待确认消息 <Badge count={inboxItems.length} /></span>} extra={<Button type="link">进入收件箱</Button>}>
            {inboxItems.slice(0, 3).map((item) => (
              <button className="inbox-mini-item" key={item.id}>
                <span className="inbox-mini-top"><strong>{item.aiDecision}</strong><em>{Math.round(item.confidence * 100)}%</em></span>
                <span>{item.summary}</span>
                <small>{item.chatName} · {item.sentAt}</small>
              </button>
            ))}
          </Card>
          <Card className="side-card" title="即将发生的节点">
            <div className="deadline-list">
              <div><time>14:00</time><span>主播解约事实核查会</span></div>
              <div><time>16:00</time><span>解约风险意见内部截止</span></div>
              <div><time>18:00</time><span>直播广告脚本定稿</span></div>
              <div><time>明日</time><span>音乐版权申诉材料截止</span></div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
