export type TaskStatus =
  | '待确认'
  | '待开始'
  | '处理中'
  | '等待业务反馈'
  | '等待外部反馈'
  | '等待材料'
  | '待审批'
  | '存在阻塞'
  | '已完成'
  | '已关闭'
  | '已取消';

export type Priority = '紧急' | '高' | '中' | '低';
export type LegalRisk = '严重' | '高' | '中' | '低' | '待评估';
export type BusinessImpact = '公司级' | '部门级' | '项目级' | '一般事项';
export type SourceType = '群聊' | '私聊' | '@消息' | '文件' | '通知' | '人工创建';

export interface Person {
  id: string;
  name: string;
  department: string;
  avatar?: string;
}

export interface Task {
  id: string;
  title: string;
  category: string;
  businessLine: string;
  source: SourceType;
  sourceName: string;
  requester: Person;
  owner: Person;
  collaborators: Person[];
  status: TaskStatus;
  priority: Priority;
  legalRisk: LegalRisk;
  businessImpact: BusinessImpact;
  deadline?: string;
  createdAt: string;
  waitingFor?: string;
  waitingSince?: string;
  nextAction: string;
  amount?: number;
  confidence: number;
  aiCreated: boolean;
  missingMaterials?: string[];
  riskReasons: string[];
  tags: string[];
}

export interface InboxItem {
  id: string;
  speaker: Person;
  chatName: string;
  sentAt: string;
  summary: string;
  context: string[];
  aiDecision: '明确交给我的任务' | '可能属于我的工作' | '仅供我知悉' | '等待他人处理' | '与法务无关' | '信息不足';
  suggestedType: string;
  suggestedPriority: Priority;
  suggestedRisk: LegalRisk;
  confidence: number;
  rationale: string[];
  relatedTaskId?: string;
}

export interface AgentRun {
  id: string;
  agentName: string;
  version: string;
  status: '成功' | '运行中' | '失败' | '待审批';
  taskId: string;
  startedAt: string;
  duration: string;
  confidence?: number;
  cost: number;
  output: string;
}
