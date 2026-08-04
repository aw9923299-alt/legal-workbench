import { Empty, Result, Skeleton, Spin } from 'antd';
import type { ReactNode } from 'react';

export type StatePanelVariant = 'loading' | 'empty' | 'filtered-empty' | 'error' | 'permission' | 'unavailable' | 'stale';

export type StatePanelProps = {
  variant: StatePanelVariant;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  correlationId?: string;
  className?: string;
};

const resultStatusByVariant: Partial<Record<StatePanelVariant, 'error' | 'warning' | '403' | '404'>> = {
  error: 'error',
  permission: '403',
  unavailable: '404',
  stale: 'warning',
};

export default function StatePanel({ variant, title, description, action, correlationId, className }: StatePanelProps) {
  const classes = ['state-panel', `state-panel--${variant}`, className].filter(Boolean).join(' ');

  if (variant === 'loading') {
    return (
      <section
        className={classes}
        role="status"
        aria-label={typeof title === 'string' ? title : undefined}
        aria-busy="true"
        aria-live="polite"
      >
        <div className="state-panel__loading-copy">
          <strong>{title}</strong>
          {description && <span>{description}</span>}
        </div>
        <Spin />
        <Skeleton active paragraph={{ rows: 3 }} title={false} />
      </section>
    );
  }
  if (variant === 'empty' || variant === 'filtered-empty') {
    return <section className={classes}><Empty description={<span><strong>{title}</strong>{description && <small>{description}</small>}</span>}>{action}</Empty></section>;
  }
  return (
    <section className={classes} role={variant === 'error' || variant === 'permission' ? 'alert' : 'status'}>
      <Result status={resultStatusByVariant[variant]} title={title} subTitle={<>{description}{correlationId && <small className="state-panel__correlation-id">关联 ID：{correlationId}</small>}</>} extra={action} />
    </section>
  );
}
