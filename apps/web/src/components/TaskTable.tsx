import { Button, Table, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { Task } from '../types/domain';
import { PriorityTag, RiskTag, StatusTag } from './StatusTags';
import ResponsiveCollection from './ResponsiveCollection';

const { Text } = Typography;

function TaskSummary({ task }: { task: Task }) {
  const origin = task.aiCreated ? 'AI 建议' : '人工建立';
  const missingMaterials = task.missingMaterials?.length ?? 0;

  return (
    <>
      <span className="task-risk-reason">{task.riskReasons[0] || '风险理由待补充'}</span>
      <span className="task-summary-meta">缺失材料 {missingMaterials} 项 · {origin}</span>
    </>
  );
}

export default function TaskTable({ data, onOpen }: { data: Task[]; onOpen: (task: Task) => void }) {
  const columns: ColumnsType<Task> = [
    {
      title: '事项与来源',
      dataIndex: 'title',
      width: 270,
      render: (_, task) => (
        <button className="task-title-button" onClick={() => onOpen(task)}>
          <span className="task-id">{task.id}</span>
          <strong>{task.title}</strong>
          <span className="task-meta-line">{task.category} · {task.sourceName}</span>
        </button>
      ),
    },
    {
      title: '风险与优先级',
      width: 124,
      render: (_, task) => <div className="task-tag-stack"><RiskTag value={task.legalRisk} /><PriorityTag value={task.priority} /></div>,
    },
    {
      title: '截止时间',
      dataIndex: 'deadline',
      width: 128,
      render: (value, task) => <Text type={task.deadline?.startsWith('2026-07') ? 'danger' : undefined}>{value || '未设置'}</Text>,
    },
    {
      title: '负责人和等待对象',
      width: 164,
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
      width: 258,
      render: (value, task) => (
        <div className="next-action-cell">
          <Tooltip title={value}><span>{value}</span></Tooltip>
          <TaskSummary task={task} />
        </div>
      ),
    },
    {
      title: '状态与操作',
      width: 128,
      render: (_, task) => (
        <div className="task-status-cell">
          <StatusTag value={task.status} />
          <Button type="link" size="small" onClick={() => onOpen(task)}>进入事项中心</Button>
        </div>
      ),
    },
  ];

  return (
    <ResponsiveCollection
      items={data}
      getKey={(task) => task.id}
      renderDesktop={(items) => (
        <div className="task-table-desktop">
          <Table
            rowKey="id"
            columns={columns}
            dataSource={items}
            pagination={false}
            size="middle"
            tableLayout="fixed"
            rowClassName={(task) => task.status === '存在阻塞' ? 'row-blocked' : ''}
          />
        </div>
      )}
      renderCompact={(task) => (
        <article className="task-compact-card">
          <div className="task-compact-title">
            <span className="task-id">{task.id} · {task.sourceName}</span>
            <h4>{task.title}</h4>
          </div>
          <div className="task-compact-field task-compact-risk"><span>风险</span><RiskTag value={task.legalRisk} /><PriorityTag value={task.priority} /></div>
          <div className="task-compact-field"><span>期限</span><strong className={task.deadline?.startsWith('2026-07') ? 'deadline-overdue' : undefined}>{task.deadline || '未设置'}</strong></div>
          <div className="task-compact-field"><span>负责人</span><strong>{task.owner.name}</strong><small>{task.waitingFor ? `等待 ${task.waitingFor}` : '当前由我处理'}</small></div>
          <div className="task-compact-field task-compact-next"><span>下一步</span><strong>{task.nextAction}</strong></div>
          <div className="task-compact-action"><StatusTag value={task.status} /><Button type="link" onClick={() => onOpen(task)}>进入事项中心</Button></div>
        </article>
      )}
      renderMobile={(task) => (
        <article className="task-mobile-card">
          <span className="task-id">{task.id} · {task.sourceName}</span>
          <h4>{task.title}</h4>
          <div className="task-mobile-tags"><RiskTag value={task.legalRisk} /><PriorityTag value={task.priority} /><StatusTag value={task.status} /></div>
          <dl>
            <div><dt>期限</dt><dd className={task.deadline?.startsWith('2026-07') ? 'deadline-overdue' : undefined}>{task.deadline || '未设置'}</dd></div>
            <div><dt>负责人</dt><dd>{task.owner.name}</dd></div>
            <div><dt>等待 / 缺失</dt><dd>{task.waitingFor ? `等待 ${task.waitingFor}` : '当前由我处理'} · 缺失材料 {task.missingMaterials?.length ?? 0} 项</dd></div>
            <div><dt>下一步</dt><dd>{task.nextAction}</dd></div>
          </dl>
          <TaskSummary task={task} />
          <Button type="link" onClick={() => onOpen(task)}>进入事项中心</Button>
        </article>
      )}
    />
  );
}
