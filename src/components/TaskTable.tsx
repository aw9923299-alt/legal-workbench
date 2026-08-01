import { Button, Dropdown, Progress, Table, Tooltip, Typography } from 'antd';
import { EllipsisOutlined, MessageOutlined, PaperClipOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { Task } from '../types/domain';
import { PriorityTag, RiskTag, StatusTag } from './StatusTags';

const { Text } = Typography;

export default function TaskTable({ data, onOpen }: { data: Task[]; onOpen: (task: Task) => void }) {
  const columns: ColumnsType<Task> = [
    {
      title: '任务',
      dataIndex: 'title',
      width: 330,
      render: (_, task) => (
        <button className="task-title-button" onClick={() => onOpen(task)}>
          <span className="task-id">{task.id}</span>
          <strong>{task.title}</strong>
          <span className="task-meta-line">{task.category} · {task.sourceName}</span>
        </button>
      ),
    },
    { title: '优先级', dataIndex: 'priority', width: 82, render: (value) => <PriorityTag value={value} /> },
    { title: '风险', dataIndex: 'legalRisk', width: 100, render: (value) => <RiskTag value={value} /> },
    { title: '状态', dataIndex: 'status', width: 128, render: (value) => <StatusTag value={value} /> },
    {
      title: '截止时间',
      dataIndex: 'deadline',
      width: 142,
      render: (value, task) => <Text type={task.deadline?.startsWith('2026-07') ? 'danger' : undefined}>{value || '未设置'}</Text>,
    },
    {
      title: '当前责任与等待',
      width: 185,
      render: (_, task) => (
        <div className="responsibility-cell">
          <span>负责人：{task.owner.name}</span>
          <span>{task.waitingFor ? `等待：${task.waitingFor}` : '当前：由我处理'}</span>
        </div>
      ),
    },
    {
      title: '下一步行动',
      dataIndex: 'nextAction',
      ellipsis: true,
      render: (value) => <Tooltip title={value}><span>{value}</span></Tooltip>,
    },
    {
      title: 'AI',
      width: 94,
      render: (_, task) => (
        <div className="ai-confidence-cell">
          <Progress percent={Math.round(task.confidence * 100)} showInfo={false} size="small" />
          <span>{Math.round(task.confidence * 100)}%</span>
        </div>
      ),
    },
    {
      title: '',
      width: 86,
      fixed: 'right',
      render: (_, task) => (
        <div className="row-actions">
          <Tooltip title="查看消息"><Button type="text" size="small" icon={<MessageOutlined />} /></Tooltip>
          <Tooltip title="附件"><Button type="text" size="small" icon={<PaperClipOutlined />} /></Tooltip>
          <Dropdown menu={{ items: [{ key: 'open', label: '打开详情' }, { key: 'remind', label: '设置提醒' }, { key: 'close', label: '关闭任务' }], onClick: ({ key }) => key === 'open' && onOpen(task) }}>
            <Button type="text" size="small" icon={<EllipsisOutlined />} />
          </Dropdown>
        </div>
      ),
    },
  ];

  return (
    <Table
      rowKey="id"
      columns={columns}
      dataSource={data}
      pagination={false}
      size="middle"
      scroll={{ x: 1360 }}
      rowClassName={(task) => task.status === '存在阻塞' ? 'row-blocked' : ''}
    />
  );
}
