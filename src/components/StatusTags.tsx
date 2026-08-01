import { Tag } from 'antd';
import type { BusinessImpact, LegalRisk, Priority, TaskStatus } from '../types/domain';

const priorityColors: Record<Priority, string> = { 紧急: 'red', 高: 'orange', 中: 'blue', 低: 'default' };
const riskColors: Record<LegalRisk, string> = { 严重: 'red', 高: 'volcano', 中: 'gold', 低: 'green', 待评估: 'default' };
const statusColors: Partial<Record<TaskStatus, string>> = { 处理中: 'processing', 待确认: 'purple', 待开始: 'default', 等待业务反馈: 'cyan', 等待外部反馈: 'geekblue', 等待材料: 'gold', 待审批: 'blue', 存在阻塞: 'red', 已完成: 'green', 已关闭: 'default', 已取消: 'default' };
const impactColors: Record<BusinessImpact, string> = { 公司级: 'magenta', 部门级: 'purple', 项目级: 'blue', 一般事项: 'default' };

export const PriorityTag = ({ value }: { value: Priority }) => <Tag color={priorityColors[value]}>{value}</Tag>;
export const RiskTag = ({ value }: { value: LegalRisk }) => <Tag color={riskColors[value]}>{value}风险</Tag>;
export const StatusTag = ({ value }: { value: TaskStatus }) => <Tag color={statusColors[value]}>{value}</Tag>;
export const ImpactTag = ({ value }: { value: BusinessImpact }) => <Tag color={impactColors[value]}>{value}</Tag>;
