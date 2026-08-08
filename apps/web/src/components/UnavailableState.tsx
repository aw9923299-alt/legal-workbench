import { Result } from 'antd';
import type { ReactNode } from 'react';

export type UnavailableStateProps = {
  title: ReactNode;
  description: ReactNode;
  alternative?: ReactNode;
  backendGap?: ReactNode;
  className?: string;
};

export default function UnavailableState({ title, description, alternative, backendGap, className }: UnavailableStateProps) {
  return (
    <section className={['unavailable-state', className].filter(Boolean).join(' ')} role="status">
      <Result
        status="warning"
        title={title}
        subTitle={<><span>{description}</span>{backendGap && <small className="unavailable-state__gap">后端缺口：{backendGap}</small>}</>}
        extra={alternative}
      />
    </section>
  );
}
