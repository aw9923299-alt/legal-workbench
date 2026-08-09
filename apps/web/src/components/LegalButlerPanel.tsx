import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  Empty,
  List,
  Space,
  Spin,
  Tag,
  Timeline,
  Typography,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type {
  AgentExecutionPlanRecord,
  AgentExecutionPlanStatus,
  AgentRunRecord,
} from '../types/api';

const { Paragraph, Text, Title } = Typography;

const planStatus: Record<AgentExecutionPlanStatus, { label: string; color: string }> = {
  queued: { label: '排队中', color: 'gold' },
  planning: { label: '规划中', color: 'blue' },
  planned: { label: '已规划', color: 'cyan' },
  running: { label: '运行中', color: 'blue' },
  completed: { label: '已完成', color: 'green' },
  partial: { label: '部分成功', color: 'orange' },
  failed: { label: '失败', color: 'red' },
  needs_information: { label: '待补信息', color: 'gold' },
  cancelled: { label: '已取消', color: 'default' },
};

const agentLabels: Record<string, string> = {
  legal_consultation: '一般法律咨询',
  contract_review: '合同审查',
  dispute_complaint: '争议与投诉',
  ip_copyright: '知识产权与著作权',
  labor_employment: '劳动用工',
  legal_butler: '法务管家',
};

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function objects(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
    : [];
}

function synthesisRun(plan: AgentExecutionPlanRecord): AgentRunRecord | undefined {
  const synthesisRuns = plan.agentRuns.filter((run) => run.runRole === 'butler_synthesis');
  return synthesisRuns[synthesisRuns.length - 1];
}

function Synthesis({ run }: { run?: AgentRunRecord }) {
  const output = run?.outputPayload;
  if (!output) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="综合意见尚未形成" />;
  const citations = objects(output.citations);
  const conflicts = objects(output.conflicts);
  const risks = objects(output.integratedRisks);
  return <div className="butler-synthesis">
    <Descriptions column={1} size="small" items={[
      { key: 'assessment', label: '事项判断', children: String(output.matterAssessment ?? '—') },
      { key: 'facts', label: '核心事实', children: strings(output.coreFacts).join('；') || '—' },
      { key: 'issues', label: '关键法律问题', children: strings(output.keyLegalIssues).join('；') || '—' },
      { key: 'risks', label: '综合风险', children: risks.length === 0 ? '—' : risks.map((risk) => `${String(risk.description ?? '未命名风险')}（${String(risk.severity ?? 'unknown')} / ${String(risk.likelihood ?? 'unknown')}）`).join('；') },
      { key: 'strategy', label: '推荐处理策略', children: strings(output.recommendedStrategy).join('；') || '—' },
      { key: 'actions', label: '下一步行动', children: strings(output.nextActions).join('；') || '—' },
      { key: 'missing', label: '待补充信息', children: strings(output.missingInformation).join('；') || '无' },
      { key: 'agents', label: '参与 Agents', children: strings(output.participatingAgents).map((agent) => <Tag key={agent}>{agentLabels[agent] ?? agent}</Tag>) },
    ]} />
    {conflicts.length > 0 && <Alert
      type="warning"
      showIcon
      message="专业意见存在冲突"
      description={conflicts.map((conflict) => String(conflict.topic ?? '未命名冲突')).join('；')}
    />}
    <div className="butler-draft">
      <Text strong>建议回复</Text>
      <Paragraph copyable>{String(output.draftResponse ?? '暂无回复草稿')}</Paragraph>
    </div>
    <div className="butler-citations">
      <Text strong>引用依据</Text>
      {citations.length === 0 ? <Text type="secondary">暂无引用</Text> : <List
        size="small"
        dataSource={citations}
        renderItem={(citation) => <List.Item>
          <div><Text>{String(citation.title ?? citation.sourceRef ?? '引用来源')}</Text><br />
            <Text type="secondary">{String(citation.locator ?? '未标注位置')} · {String(citation.sourceRef ?? '')}</Text>
            {citation.internalPrecedent === true && <Tag color="purple">内部先例</Tag>}
          </div>
        </List.Item>}
      />}
    </div>
  </div>;
}

export default function LegalButlerPanel({
  plans,
  loading,
  onRefresh,
  onRerun,
}: {
  plans: AgentExecutionPlanRecord[];
  loading: boolean;
  onRefresh: () => void;
  onRerun: (planId: string, stepId: string) => Promise<void>;
}) {
  return <Card
    bordered={false}
    className="legal-butler-panel"
    title={<div><Title level={4}>法务管家</Title><Text type="secondary">计划、专业分析与综合意见均来自持久化 AgentRun；最终结果仍需人工审核。</Text></div>}
    extra={<Button icon={<ReloadOutlined />} onClick={onRefresh}>刷新</Button>}
  >
    <Spin spinning={loading}>
      {plans.length === 0 ? <Empty description="尚无管家执行计划" /> : <Collapse
        defaultActiveKey={[plans[0]?.id]}
        items={plans.map((plan) => {
          const status = planStatus[plan.status];
          return {
            key: plan.id,
            label: <div className="butler-plan-heading">
              <div><Text strong>{plan.objective}</Text><Text type="secondary">{new Date(plan.createdAt).toLocaleString()}</Text></div>
              <Tag color={status.color}>{status.label}</Tag>
            </div>,
            children: <div className="butler-plan-detail">
              {plan.status === 'partial' && <Alert type="warning" showIcon message="部分专业步骤失败，综合意见保留已成功结果。" />}
              {plan.status === 'failed' && <Alert type="error" showIcon message="本次执行失败，请查看 Run 失败码后重跑对应 Step。" />}
              <section>
                <Title level={5}>执行计划</Title>
                <Timeline items={plan.steps.map((step) => ({
                  color: step.status === 'completed' ? 'green' : step.status === 'failed' ? 'red' : 'blue',
                  children: <div className="butler-step">
                    <div><Text strong>{agentLabels[step.agentKey] ?? step.agentKey}</Text><Tag>{step.status}</Tag></div>
                    <Paragraph>{step.objective}</Paragraph>
                    <Text type="secondary">依赖：{step.dependsOn.join('、') || '无'} · 尝试 {step.attemptCount} 次</Text>
                    {step.latestRunId && <Button type="link" onClick={() => void onRerun(plan.id, step.stepId)}>重新运行此 Step</Button>}
                  </div>,
                }))} />
              </section>
              <section>
                <Title level={5}>Specialist Runs</Title>
                <Space wrap>{plan.agentRuns.filter((run) => run.runRole === 'specialist').map((run) => <Tag key={run.id} color={run.status === 'completed' ? 'green' : run.status === 'failed' ? 'red' : 'blue'}>{agentLabels[run.agentKey] ?? run.agentKey} · {run.status}</Tag>)}</Space>
              </section>
              <section>
                <Title level={5}>综合意见</Title>
                <Synthesis run={synthesisRun(plan)} />
              </section>
            </div>,
          };
        })}
      />}
    </Spin>
  </Card>;
}
