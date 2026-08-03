import { Alert, Button, Space } from 'antd';
import type { WorkItemStatus } from '../types/api';

export type WorkItemLifecycleAction =
  | 'start'
  | 'pause'
  | 'wait'
  | 'block'
  | 'resume'
  | 'complete'
  | 'cancel'
  | 'reopen'
  | 'owner'
  | 'changeDeadline'
  | 'nextAction';

interface ActionDefinition {
  action: WorkItemLifecycleAction;
  label: string;
  primary?: boolean;
  danger?: boolean;
}

const sharedMutable: ActionDefinition[] = [
  { action: 'cancel', label: '取消', danger: true },
  { action: 'owner', label: '改负责人' },
  { action: 'changeDeadline', label: '改完成时间' },
  { action: 'nextAction', label: '改下一步' },
];

const statusActions: Record<WorkItemStatus, ActionDefinition[]> = {
  todo: [
    { action: 'start', label: '开始', primary: true },
    { action: 'wait', label: '等待' },
    { action: 'block', label: '阻塞', danger: true },
    ...sharedMutable,
  ],
  in_progress: [
    { action: 'pause', label: '暂停' },
    { action: 'wait', label: '等待' },
    { action: 'block', label: '阻塞', danger: true },
    { action: 'complete', label: '完成', primary: true },
    ...sharedMutable,
  ],
  paused: [
    { action: 'resume', label: '恢复', primary: true },
    { action: 'block', label: '阻塞', danger: true },
    ...sharedMutable,
  ],
  waiting: [
    { action: 'resume', label: '恢复', primary: true },
    { action: 'block', label: '阻塞', danger: true },
    ...sharedMutable,
  ],
  blocked: [{ action: 'resume', label: '恢复', primary: true }, ...sharedMutable],
  pending_review: [{ action: 'complete', label: '完成', primary: true }, ...sharedMutable],
  done: [{ action: 'reopen', label: '重新打开' }],
  cancelled: [{ action: 'reopen', label: '重新打开' }],
};

export function availableWorkItemActions(status: WorkItemStatus): ActionDefinition[] {
  return statusActions[status];
}

export default function WorkItemActions({
  status,
  disabledReason,
  onLifecycle,
  onPriority,
  onDeadline,
  onDependency,
}: {
  status: WorkItemStatus;
  disabledReason?: string;
  onLifecycle: (action: WorkItemLifecycleAction) => void;
  onPriority: () => void;
  onDeadline: () => void;
  onDependency: () => void;
}) {
  const terminal = status === 'done' || status === 'cancelled';
  const disabled = Boolean(disabledReason);
  return (
    <>
      {disabledReason && <Alert type="warning" showIcon message={disabledReason} />}
      <Space style={{ marginTop: 14 }} wrap>
        {!terminal && <Button disabled={disabled} onClick={onPriority}>确认优先级</Button>}
        {!terminal && <Button disabled={disabled} onClick={onDeadline}>添加期限</Button>}
        {!terminal && <Button disabled={disabled} onClick={onDependency}>添加依赖</Button>}
        {availableWorkItemActions(status).map((definition) => (
          <Button
            key={definition.action}
            disabled={disabled}
            type={definition.primary ? 'primary' : 'default'}
            danger={definition.danger}
            onClick={() => onLifecycle(definition.action)}
          >
            {definition.label}
          </Button>
        ))}
      </Space>
    </>
  );
}
