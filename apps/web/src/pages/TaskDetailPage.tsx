import { Alert, Avatar, Button, Card, Descriptions, Divider, List, Progress, Space, Steps, Tabs, Tag, Timeline, Typography } from 'antd';
import { ArrowLeftOutlined, CheckCircleOutlined, FileTextOutlined, RobotOutlined, SendOutlined } from '@ant-design/icons';
import type { Task } from '../types/domain';
import { ImpactTag, PriorityTag, RiskTag, StatusTag } from '../components/StatusTags';

const { Title, Text, Paragraph } = Typography;

export default function TaskDetailPage({ task, onBack }: { task: Task; onBack: () => void }) {
  return (
    <div className="page task-detail-page">
      <Button type="text" icon={<ArrowLeftOutlined />} onClick={onBack}>返回任务中心</Button>
      <div className="detail-header">
        <div>
          <div className="detail-id-row"><Text type="secondary">{task.id}</Text><Tag color="blue">AI 已关联 18 条消息</Tag></div>
          <Title level={2}>{task.title}</Title>
          <Space wrap><StatusTag value={task.status} /><PriorityTag value={task.priority} /><RiskTag value={task.legalRisk} /><ImpactTag value={task.businessImpact} /></Space>
        </div>
        <Space><Button>设置提醒</Button><Button icon={<RobotOutlined />}>调用 Agent</Button><Button type="primary" icon={<SendOutlined />}>发送进度</Button></Space>
      </div>

      <Alert type="warning" showIcon message={`下一步行动：${task.nextAction}`} description={`当前负责人：${task.owner.name}；${task.waitingFor ? `正在等待 ${task.waitingFor}` : '当前由你继续处理'}。截止时间：${task.deadline || '未设置'}。`} />

      <div className="detail-grid">
        <main className="detail-main">
          <Card className="ai-summary-card" bordered={false}>
            <div className="ai-label"><RobotOutlined /> AI 任务摘要 · 未经人工确认</div>
            <Paragraph>该事项由飞书消息自动识别并与历史沟通合并。当前核心目标是控制解约、停播和竞业限制争议风险，在业务决定前确认合同主体、违约事实、补偿支付及对外沟通口径。</Paragraph>
            <div className="evidence-links"><button>消息 07-31 18:42</button><button>主播合作协议.pdf 第 12 条</button><button>结算表 2026H1.xlsx</button></div>
          </Card>

          <Card bordered={false}>
            <Tabs items={[
              { key: 'work', label: '处理工作区', children: <WorkArea task={task} /> },
              { key: 'chat', label: '飞书上下文', children: <ChatContext /> },
              { key: 'files', label: '文件与材料', children: <FileArea task={task} /> },
              { key: 'ai', label: 'AI 分析记录', children: <AiRecords /> },
              { key: 'decision', label: '决策与变更', children: <Timeline items={[{ children: '今天 11:18 人工确认法律风险为“严重”' }, { children: '今天 10:52 AI 将 3 个群聊线程合并至本任务' }, { children: '昨天 18:42 从 @消息创建待确认事项' }]} /> },
            ]} />
          </Card>
        </main>

        <aside className="detail-sidebar">
          <Card title="任务字段" bordered={false}>
            <Descriptions column={1} size="small" items={[
              { key: 'type', label: '事项类型', children: task.category },
              { key: 'line', label: '业务线', children: task.businessLine },
              { key: 'requester', label: '发起人', children: `${task.requester.name} / ${task.requester.department}` },
              { key: 'owner', label: '负责人', children: task.owner.name },
              { key: 'deadline', label: '截止时间', children: task.deadline },
              { key: 'source', label: '来源', children: `${task.source} · ${task.sourceName}` },
              { key: 'amount', label: '涉及金额', children: task.amount ? `¥${task.amount.toLocaleString()}` : '未填写' },
              { key: 'secret', label: '保密等级', children: '机密' },
            ]} />
          </Card>
          <Card title="AI 判断透明度" bordered={false}>
            <Progress percent={Math.round(task.confidence * 100)} />
            <Text type="secondary">基于消息明确交办、上下文主体、历史任务相似度与截止节点综合判断。</Text>
            <Divider />
            {task.riskReasons.map((reason) => <Tag key={reason} color="volcano">{reason}</Tag>)}
          </Card>
          <Card title="可调用 Agent" bordered={false}>
            {['法律风险识别 Agent','合同条款提取 Agent','证据材料整理 Agent','文书起草 Agent'].map((name) => <button className="agent-call-row" key={name}><RobotOutlined /><span>{name}</span><em>调用</em></button>)}
          </Card>
        </aside>
      </div>
    </div>
  );
}

function WorkArea({ task }: { task: Task }) {
  const checklist = ['核实签约及收款主体', '整理违约事实和证据', '核对竞业补偿支付记录', '确认停播及结算业务影响', '形成内部风险意见'];
  return (
    <div className="work-area-grid">
      <section>
        <Title level={4}>当前处理目标</Title>
        <Paragraph>在不影响核心直播业务连续性的前提下，明确公司可采取的解约或暂停合作路径，并形成可执行的沟通方案。</Paragraph>
        <Title level={4}>子任务与检查清单</Title>
        <List dataSource={checklist} renderItem={(item, index) => <List.Item><Space><CheckCircleOutlined className={index < 2 ? 'done-icon' : ''} /><span>{item}</span></Space><Text type="secondary">{index < 2 ? '已完成' : '待处理'}</Text></List.Item>} />
      </section>
      <section>
        <Title level={4}>进度时间线</Title>
        <Steps direction="vertical" size="small" current={2} items={[
          { title: '识别并确认任务', description: '已合并 3 个群聊线程' },
          { title: '材料与事实核查', description: '仍缺 2 项材料' },
          { title: '法律分析与方案', description: '进行中' },
          { title: '业务决策与沟通', description: '待开始' },
          { title: '结案与复盘', description: '待开始' },
        ]} />
      </section>
    </div>
  );
}

function ChatContext() {
  return <Timeline items={[
    { color: 'blue', children: <><Text strong>今天 10:26 · 主播经纪管理群</Text><Paragraph>HR 提出暂停结算并评估终止合作，AI 判断为同一事项的新进展。</Paragraph></> },
    { color: 'gray', children: <><Text strong>昨天 18:42 · 主播管理专项群</Text><Paragraph>@法务确认竞业条款、停播影响和解约通知安排。</Paragraph></> },
    { color: 'gray', children: <><Text strong>07-29 15:10 · 私聊</Text><Paragraph>运营提供主播近三场缺播情况及业务影响。</Paragraph></> },
  ]} />;
}

function FileArea({ task }: { task: Task }) {
  return <div><List dataSource={['主播合作协议_最终版.pdf','2026H1主播结算明细.xlsx','直播排期与缺播记录.xlsx']} renderItem={(item) => <List.Item actions={[<Button key="open" type="link">打开</Button>]}><List.Item.Meta avatar={<Avatar icon={<FileTextOutlined />} />} title={item} description="AI 已提取关键信息，原文件权限继承自飞书" /></List.Item>} /><Divider /><Title level={5}>缺失材料</Title>{task.missingMaterials?.map((item) => <Tag key={item} color="gold">{item}</Tag>)}</div>;
}

function AiRecords() {
  return <List dataSource={[
    ['法律风险识别 Agent','识别 6 项高风险事实，置信度 92%，等待人工确认。'],
    ['消息识别 Agent','将 18 条消息聚合为 1 个事项，排除 4 条重复通知。'],
    ['合同条款提取 Agent','提取解约、违约、竞业和争议解决条款共 11 项。'],
  ]} renderItem={([name, content]) => <List.Item><List.Item.Meta avatar={<Avatar icon={<RobotOutlined />} />} title={name} description={content} /></List.Item>} />;
}
