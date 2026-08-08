import { Space, Typography } from 'antd';
import type { ReactNode } from 'react';

const { Title, Text } = Typography;

export type PageHeaderProps = {
  title: ReactNode;
  description?: ReactNode;
  eyebrow?: ReactNode;
  metadata?: ReactNode;
  primaryAction?: ReactNode;
  secondaryActions?: ReactNode[];
  className?: string;
};

export default function PageHeader({ title, description, eyebrow, metadata, primaryAction, secondaryActions = [], className }: PageHeaderProps) {
  return (
    <header className={['page-header', className].filter(Boolean).join(' ')}>
      <div className="page-header__copy">
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <Title level={2}>{title}</Title>
        {description && <Text type="secondary" className="page-header__description">{description}</Text>}
        {metadata && <div className="page-header__metadata">{metadata}</div>}
      </div>
      {(secondaryActions.length > 0 || primaryAction) && (
        <Space className="page-header__actions" wrap>
          {secondaryActions.map((action, index) => <span key={index}>{action}</span>)}
          {primaryAction && <span className="page-header__primary-action lw-touch-target">{primaryAction}</span>}
        </Space>
      )}
    </header>
  );
}
