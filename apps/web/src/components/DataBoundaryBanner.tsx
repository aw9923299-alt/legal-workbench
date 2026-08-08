import { Alert } from 'antd';
import type { ReactNode } from 'react';

export type DataBoundaryVariant = 'demo' | 'api' | 'pending' | 'unavailable' | 'stale';

export type DataBoundaryBannerProps = {
  variant: DataBoundaryVariant;
  title: ReactNode;
  description: ReactNode;
  action?: ReactNode;
  className?: string;
};

const alertTypeByVariant: Record<DataBoundaryVariant, 'info' | 'warning'> = {
  demo: 'info',
  api: 'info',
  pending: 'warning',
  unavailable: 'warning',
  stale: 'warning',
};

export default function DataBoundaryBanner({ variant, title, description, action, className }: DataBoundaryBannerProps) {
  return (
    <Alert
      className={['data-boundary-banner', `data-boundary-banner--${variant}`, className].filter(Boolean).join(' ')}
      data-boundary-variant={variant}
      type={alertTypeByVariant[variant]}
      showIcon
      message={title}
      description={description}
      action={action}
    />
  );
}
