import { Button, Card, Input, Select, Space, Tabs, Typography } from 'antd';
import { AppstoreOutlined, CalendarOutlined, FilterOutlined, PlusOutlined, SearchOutlined, UnorderedListOutlined } from '@ant-design/icons';
import { tasks } from '../data/mock';
import type { Task } from '../types/domain';
import TaskTable from '../components/TaskTable';

const { Title, Text } = Typography;

export default function TaskCenterPage({ onOpenTask }: { onOpenTask: (task: Task) => void }) {
  return (
    <div className="page">
      <div className="page-title-row"><div><span className="eyebrow">LEGAL WORKFLOW</span><Title level={2}>任务中心</Title><Text type="secondary">统一查看任务、案件、项目及跨会话进度。</Text></div><Button type="primary" icon={<PlusOutlined />}>新建任务</Button></div>
      <Card className="filter-card" bordered={false}>
        <Space wrap>
          <Input prefix={<SearchOutlined />} placeholder="搜索标题、主体、主播、合同或消息" style={{ width: 320 }} />
          <Select placeholder="状态" style={{ width: 130 }} options={['待确认','待开始','处理中','等待业务反馈','等待外部反馈','等待材料','待审批','存在阻塞','已完成'].map((value) => ({ value }))} />
          <Select placeholder="法律风险" style={{ width: 130 }} options={['严重','高','中','低','待评估'].map((value) => ({ value }))} />
          <Select placeholder="业务部门" style={{ width: 150 }} options={['直播商务部','直播运营部','品牌市场部','人力资源部','财务部'].map((value) => ({ value }))} />
          <Select placeholder="等待状态" style={{ width: 150 }} options={['等待我回复','等待他人回复','缺少材料','存在阻塞'].map((value) => ({ value }))} />
          <Button icon={<FilterOutlined />}>更多筛选</Button><Button type="link">保存当前筛选</Button>
        </Space>
      </Card>
      <Card className="task-center-card" bordered={false}>
        <Tabs
          defaultActiveKey="list"
          tabBarExtraContent={<Text type="secondary">共 {tasks.length} 项 · 其中 AI 创建 {tasks.filter((task) => task.aiCreated).length} 项</Text>}
          items={[
            { key: 'list', label: <span><UnorderedListOutlined /> 列表</span>, children: <TaskTable data={tasks} onOpen={onOpenTask} /> },
            { key: 'board', label: <span><AppstoreOutlined /> 看板</span>, children: <div className="placeholder-state">看板视图：按状态展示拖拽列，并在状态变化时要求填写下一步行动。</div> },
            { key: 'calendar', label: <span><CalendarOutlined /> 日历</span>, children: <div className="placeholder-state">日历视图：展示截止时间、提醒节点、诉讼期限与合同履约节点。</div> },
            { key: 'timeline', label: '时间线', children: <div className="placeholder-state">时间线视图：聚合同一事项在不同群聊和日期中的关键变化。</div> },
          ]}
        />
      </Card>
    </div>
  );
}
