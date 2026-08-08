import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { WorkItemStatus } from '../types/api';
import WorkItemActions, { availableWorkItemActions } from './WorkItemActions';

const expected: Record<WorkItemStatus, string[]> = {
  todo: ['start', 'wait', 'block', 'cancel', 'owner', 'changeDeadline', 'nextAction'],
  in_progress: ['pause', 'wait', 'block', 'complete', 'cancel', 'owner', 'changeDeadline', 'nextAction'],
  paused: ['resume', 'block', 'cancel', 'owner', 'changeDeadline', 'nextAction'],
  waiting: ['resume', 'block', 'cancel', 'owner', 'changeDeadline', 'nextAction'],
  blocked: ['resume', 'cancel', 'owner', 'changeDeadline', 'nextAction'],
  pending_review: ['complete', 'cancel', 'owner', 'changeDeadline', 'nextAction'],
  done: ['reopen'],
  cancelled: ['reopen'],
};

describe('WorkItemActions', () => {
  afterEach(cleanup);

  it('covers every server-supported lifecycle action through status-specific controls', () => {
    for (const [status, actions] of Object.entries(expected)) {
      expect(availableWorkItemActions(status as WorkItemStatus).map(({ action }) => action))
        .toEqual(actions);
    }
    expect(new Set(Object.values(expected).flat())).toEqual(new Set([
      'start', 'pause', 'wait', 'block', 'resume', 'complete', 'cancel', 'reopen',
      'owner', 'changeDeadline', 'nextAction',
    ]));
  });

  it('dispatches lifecycle and deterministic field operations separately', () => {
    const onLifecycle = vi.fn();
    const onPriority = vi.fn();
    const onDeadline = vi.fn();
    const onDependency = vi.fn();
    render(
      <WorkItemActions
        status="todo"
        onLifecycle={onLifecycle}
        onPriority={onPriority}
        onDeadline={onDeadline}
        onDependency={onDependency}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /开\s*始/ }));
    fireEvent.click(screen.getByRole('button', { name: '改负责人' }));
    fireEvent.click(screen.getByRole('button', { name: '确认优先级' }));
    fireEvent.click(screen.getByRole('button', { name: '添加期限' }));
    fireEvent.click(screen.getByRole('button', { name: '添加依赖' }));

    expect(onLifecycle).toHaveBeenNthCalledWith(1, 'start');
    expect(onLifecycle).toHaveBeenNthCalledWith(2, 'owner');
    expect(onPriority).toHaveBeenCalledOnce();
    expect(onDeadline).toHaveBeenCalledOnce();
    expect(onDependency).toHaveBeenCalledOnce();
  });

  it('does not offer formal mutations when the actor cannot edit', () => {
    render(
      <WorkItemActions
        status="in_progress"
        disabledReason="当前账号没有修改权限"
        onLifecycle={vi.fn()}
        onPriority={vi.fn()}
        onDeadline={vi.fn()}
        onDependency={vi.fn()}
      />,
    );

    expect(screen.getByText('当前账号没有修改权限')).toBeInTheDocument();
    expect(screen.getAllByRole('button').every((button) => button.hasAttribute('disabled')))
      .toBe(true);
  });
});
