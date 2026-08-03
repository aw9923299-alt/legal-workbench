export const categoryLabels: Record<string, string> = {
  contract: '合同审核',
  copy_review: '文案合规',
  employment: '人力劳动',
  dispute: '外部纠纷',
  intellectual_property: '知识产权',
  platform_rules: '平台规则',
  general_consultation: '一般咨询',
};

export const priorityLabels: Record<string, string> = {
  urgent: '紧急',
  high: '高',
  medium: '中',
  low: '低',
};

export const riskLabels: Record<string, string> = {
  critical: '严重',
  high: '高',
  medium: '中',
  low: '低',
  pending: '待评估',
};

export const candidateStatusLabels: Record<string, string> = {
  pending_analysis: '待分析',
  pending_confirmation: '待确认',
  confirmed: '已确认',
  linked: '已关联',
  information_only: '仅记录',
  ignored: '已忽略',
  rejected: '已拒绝',
};

export const workStatusLabels: Record<string, string> = {
  todo: '待开始',
  in_progress: '处理中',
  paused: '已暂停',
  waiting: '等待中',
  blocked: '阻塞',
  pending_review: '待审核',
  done: '已完成',
  cancelled: '已取消',
};

export function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  return JSON.stringify(value);
}
