import { ApiError } from './api';

export interface ApiFailureState {
  variant: 'error' | 'permission' | 'stale';
  title: string;
  description: string;
  correlationId?: string;
}

export function classifyApiFailure(
  reason: unknown,
  resourceName: string,
  fallbackTitle: string,
  fallbackDescription: string,
): ApiFailureState {
  if (reason instanceof ApiError) {
    if (reason.status === 401) {
      return {
        variant: 'permission',
        title: '登录状态已失效',
        description: '请重新登录后再访问；当前页面不会继续展示受保护数据。',
        correlationId: reason.correlationId,
      };
    }
    if (reason.status === 403) {
      return {
        variant: 'permission',
        title: `无权访问${resourceName}`,
        description: '当前账号没有查看该数据的权限；页面已清除相关业务摘要。',
        correlationId: reason.correlationId,
      };
    }
    if (reason.status === 409) {
      return {
        variant: 'stale',
        title: `${resourceName}版本已变化`,
        description: '服务拒绝了当前版本，请刷新后基于最新数据继续处理。',
        correlationId: reason.correlationId,
      };
    }
  }

  return {
    variant: 'error',
    title: fallbackTitle,
    description: reason instanceof Error ? reason.message : fallbackDescription,
    correlationId: reason instanceof ApiError ? reason.correlationId : undefined,
  };
}
