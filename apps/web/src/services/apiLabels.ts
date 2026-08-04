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

export const recommendedActionLabels: Record<string, string> = {
  create_matter: '创建新事项',
  link_matter: '关联已有事项',
  update_matter: '更新已有事项',
  request_more_information: '补充信息',
  reopen_matter: '重新开启事项',
  information_only: '仅作信息记录',
  ignore: '忽略',
  defer: '暂缓',
  merge: '合并事项',
};

export const messageRoleLabels: Record<string, string> = {
  new_request: '新需求',
  existing_matter_update: '既有事项更新',
  supplemental_material: '补充材料',
  deadline_change: '期限变化',
  decision_record: '决策记录',
  completion_update: '完成更新',
  information_only: '仅作信息',
};

export const legalRelevanceLabels: Record<string, string> = {
  relevant: '与法务相关',
  possibly_relevant: '可能与法务相关',
  not_relevant: '与法务无关',
  irrelevant: '与法务无关',
  unknown: '相关性待判断',
};

export const workStatusLabels: Record<string, string> = {
  todo: '待开始',
  in_progress: '处理中',
  waiting: '等待中',
  blocked: '阻塞',
  pending_review: '待审核',
  done: '已完成',
  cancelled: '已取消',
};

export const matterWorkStatusLabels: Record<string, string> = {
  ready: '待处理',
  in_progress: '处理中',
  waiting: '等待中',
  blocked: '阻塞',
  done: '已完成',
};

export const reviewPackageStatusLabels: Record<string, string> = {
  draft: '草稿',
  pending_review: '待审核',
  approved: '已批准',
  rejected: '已驳回',
  needs_information: '待补充信息',
  superseded: '已被新版本替代',
};

export const reviewDecisionLabels: Record<string, string> = {
  approved: '原样通过',
  approved_with_edits: '修改后通过',
  needs_information: '要求补充信息',
  rejected: '驳回',
};

export const agentRunStatusLabels: Record<string, string> = {
  queued: '等待运行',
  preparing: '准备中',
  running: '运行中',
  validating: '校验中',
  completed: '运行完成',
  needs_more_information: '需要更多信息',
  failed: '运行失败',
  timed_out: '运行超时',
  cancelled: '已取消',
  dead_letter: '已进入死信',
};

export function technicalStatusLabel(labels: Record<string, string>, value: string): string {
  return `${labels[value] ?? '未知状态'}（${value}）`;
}

export function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  return JSON.stringify(value);
}
