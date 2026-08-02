import { Alert, Button, Empty, Result, Spin } from 'antd';
import { ApiError } from '../services/api';

export function QueryState({
  loading,
  error,
  empty,
  onRetry,
  children,
}: {
  loading: boolean;
  error: unknown;
  empty?: boolean;
  onRetry: () => void;
  children: React.ReactNode;
}) {
  if (loading) return <div className="query-state"><Spin size="large" /></div>;
  if (error instanceof ApiError && error.status === 401) {
    return <Result status="403" title="未授权" subTitle="本地会话无效或已过期。" extra={<Button onClick={onRetry}>重试认证</Button>} />;
  }
  if (error instanceof ApiError && error.status === 503) {
    return <Result status="500" title="服务不可用" subTitle={error.message} extra={<Button onClick={onRetry}>重试</Button>} />;
  }
  if (error) {
    const typed = error instanceof ApiError ? error : undefined;
    const message = error instanceof Error ? error.message : '请求失败';
    return <Alert type="error" showIcon message={message} description={typed?.correlationId ? `Correlation ID：${typed.correlationId}` : undefined} action={<Button onClick={onRetry}>重试</Button>} />;
  }
  if (empty) return <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  return <>{children}</>;
}
