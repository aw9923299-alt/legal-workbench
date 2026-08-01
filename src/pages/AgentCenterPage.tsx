import { Alert, Button, Card, Progress, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PauseCircleOutlined, PlayCircleOutlined, RobotOutlined, SettingOutlined } from '@ant-design/icons';
import { agentRuns } from '../data/mock';
import type { AgentRun } from '../types/domain';

const { Title, Text } = Typography;

const installedAgents = [
  { id: 'message', name: '飞书消息识别 Agent', version: '3.6.0', scope: '授权群聊、@消息、指定私聊', trigger: '消息同步后', success: 96.4, approval: '低置信度需审批', status: '启用' },
  { id: 'risk', name: '法律风险识别 Agent', version: '2.4.1', scope: '任务、合同、附件', trigger: '任务创建或重大变更', success: 91.8, approval: '高风险结果需审批', status: '启用' },
  { id: 'ad', name: '广告合规检查 Agent', version: '1.8.0', scope: '口播、脚本、素材', trigger: '人工或规则触发', success: 93.1, approval: '全部结果需审批', status: '启用' },
  { id: 'archive', name: '文件归档 Agent', version: '1.3.5', scope: '已确认任务文件', trigger: '结案后', success: 84.2, approval: '写入前审批', status: '暂停' },
];

export default function AgentCenterPage() {
  const columns: ColumnsType<(typeof installedAgents)[number]> = [
    { title: 'Agent', dataIndex: 'name', render: (name, row) => <div className="agent-name"><RobotOutlined /><div><strong>{name}</strong><span>{row.id} · v{row.version}</span></div></div> },
    { title: '可访问数据范围', dataIndex: 'scope' },
    { title: '触发方式', dataIndex: 'trigger' },
    { title: '成功率', dataIndex: 'success', render: (value) => <div style={{ width: 130 }}><Progress percent={value} size="small" /></div> },
    { title: '人工审批', dataIndex: 'approval' },
    { title: '状态', dataIndex: 'status', render: (value) => <Tag color={value === '启用' ? 'green' : 'default'}>{value}</Tag> },
    { title: '操作', render: (_, row) => <Button icon={row.status === '启用' ? <PauseCircleOutlined /> : <PlayCircleOutlined />}>{row.status === '启用' ? '暂停' : '启用'}</Button> },
  ];

  const runColumns: ColumnsType<AgentRun> = [
    { title: 'Agent', dataIndex: 'agentName' },
    { title: '任务', dataIndex: 'taskId' },
    { title: '状态', dataIndex: 'status', render: (value) => <Tag color={value === '成功' ? 'green' : value === '失败' ? 'red' : value === '待审批' ? 'gold' : 'blue'}>{value}</Tag> },
    { title: '开始时间', dataIndex: 'startedAt' },
    { title: '耗时', dataIndex: 'duration' },
    { title: '置信度', dataIndex: 'confidence', render: (value) => value ? `${Math.round(value * 100)}%` : '—' },
    { title: '成本', dataIndex: 'cost', render: (value) => `¥${value.toFixed(2)}` },
    { title: '结果摘要', dataIndex: 'output', ellipsis: true },
  ];

  return <div className="page">
    <div className="page-title-row"><div><span className="eyebrow">AGENT ORCHESTRATION</span><Title level={2}>Agent 中心</Title><Text type="secondary">统一管理专业 Agent 的权限、版本、触发器、执行与回写。</Text></div><Button type="primary" icon={<SettingOutlined />}>安装或配置 Agent</Button></div>
    <Alert type="info" showIcon message="统一 Agent 接口" description="每次调用均记录输入、输出、版本、置信度、风险等级、审批状态、成本与回写位置；写操作默认需要可配置的人工审批。" />
    <Card title="已安装 Agent" bordered={false}><Table rowKey="id" columns={columns} dataSource={installedAgents} pagination={false} /></Card>
    <Card title="最近执行记录" bordered={false}><Table rowKey="id" columns={runColumns} dataSource={agentRuns} pagination={false} /></Card>
  </div>;
}
