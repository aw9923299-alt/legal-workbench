import { Tag } from 'antd';
import type { ReactNode } from 'react';
import type { BusinessImpact, LegalRisk, Priority, TaskStatus } from '../types/domain';

const priorityColors: Record<Priority, string> = { 紧急: 'red', 高: 'orange', 中: 'blue', 低: 'default' };
const riskColors: Record<LegalRisk, string> = { 严重: 'red', 高: 'volcano', 中: 'gold', 低: 'green', 待评估: 'default' };
const statusColors: Partial<Record<TaskStatus, string>> = { 处理中: 'processing', 待确认: 'purple', 待开始: 'default', 等待业务反馈: 'cyan', 等待外部反馈: 'geekblue', 等待材料: 'gold', 待审批: 'blue', 存在阻塞: 'red', 已完成: 'green', 已关闭: 'default', 已取消: 'default' };
const impactColors: Record<BusinessImpact, string> = { 公司级: 'magenta', 部门级: 'purple', 项目级: 'blue', 一般事项: 'default' };

type StatusTone = 'critical' | 'warning' | 'info' | 'success' | 'neutral' | 'ai';
export type SemanticStatusKind = 'ai' | 'human' | 'system' | 'api' | 'demo' | 'pending';

function StatusTagFrame({ kind, tone, color, children }: { kind: string; tone: StatusTone; color?: string; children: ReactNode }) {
  return <Tag className={`status-tag status-tag--${kind} status-tag--${tone}`} color={color} data-status-kind={kind} data-status-tone={tone}>{children}</Tag>;
}

const priorityTones: Record<Priority, StatusTone> = { 紧急: 'critical', 高: 'warning', 中: 'info', 低: 'neutral' };
const riskTones: Record<LegalRisk, StatusTone> = { 严重: 'critical', 高: 'critical', 中: 'warning', 低: 'success', 待评估: 'neutral' };
const statusTones: Partial<Record<TaskStatus, StatusTone>> = { 处理中: 'info', 待确认: 'ai', 待开始: 'neutral', 等待业务反馈: 'info', 等待外部反馈: 'info', 等待材料: 'warning', 待审批: 'info', 存在阻塞: 'critical', 已完成: 'success', 已关闭: 'neutral', 已取消: 'neutral' };

export const PriorityTag = ({ value }: { value: Priority }) => <StatusTagFrame kind="priority" tone={priorityTones[value]} color={priorityColors[value]}>{value}</StatusTagFrame>;
export const RiskTag = ({ value }: { value: LegalRisk }) => <StatusTagFrame kind="risk" tone={riskTones[value]} color={riskColors[value]}>{value}风险</StatusTagFrame>;
export const StatusTag = ({ value }: { value: TaskStatus }) => <StatusTagFrame kind="task-status" tone={statusTones[value] ?? 'neutral'} color={statusColors[value]}>{value}</StatusTagFrame>;
export const ImpactTag = ({ value }: { value: BusinessImpact }) => <StatusTagFrame kind="business-impact" tone="info" color={impactColors[value]}>{value}</StatusTagFrame>;

export function SemanticStatusTag({ kind, children }: { kind: SemanticStatusKind; children: ReactNode }) {
  const toneByKind: Record<SemanticStatusKind, StatusTone> = {
    ai: 'ai',
    human: 'info',
    system: 'info',
    api: 'info',
    demo: 'warning',
    pending: 'warning',
  };
  return <StatusTagFrame kind={kind} tone={toneByKind[kind]}>{children}</StatusTagFrame>;
}
