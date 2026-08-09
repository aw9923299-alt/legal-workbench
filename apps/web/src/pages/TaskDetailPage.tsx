import {
  Alert,
  Button,
  Card,
  DatePicker,
  Descriptions,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import { ArrowLeftOutlined, CalendarOutlined, LinkOutlined, ReloadOutlined, RobotOutlined } from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import { useCallback, useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import WorkItemActions, { type WorkItemLifecycleAction } from '../components/WorkItemActions';
import LegalButlerPanel from '../components/LegalButlerPanel';
import {
  clearMutationContext,
  getOrCreateMutationContext,
  isDefinitiveMutationFailure,
  legalApi,
} from '../services/api';
import { categoryLabels, priorityLabels, riskLabels, workStatusLabels } from '../services/apiLabels';
import type { AgentExecutionPlanRecord, Deadline, LegalMatter, Priority, WorkItem, WorkItemDependency } from '../types/api';

const { Title, Text, Paragraph } = Typography;

type Dialog = { type: 'priority' | 'deadline' | 'dependency'; workItem: WorkItem } | undefined;
type LifecycleDialog = { action: WorkItemLifecycleAction; workItem: WorkItem } | undefined;

interface PriorityValues { priority: Priority; completeAt?: Dayjs; reasons: string; overrideReason?: string }
interface DeadlineValues { deadlineType: string; dueAt: Dayjs; isHard: boolean; sourceReference?: string }
interface DependencyValues { dependencyType: string; dependsOnWorkItemId?: string; externalPartyId?: string; description?: string }
interface LifecycleValues { reason?: string; waitingPartyId?: string; blockerOwnerId?: string; ownerId?: string; deadline?: Dayjs; nextAction?: string }
interface ReviewPackageValues { title: string; background: string; reasoning: string; proposedContent: string; receiveId?: string; replyToMessageId?: string }
interface ButlerValues { objective?: string; specialRequirements?: string; specialistOnly?: string; workItemId?: string }

export default function TaskDetailPage({ matterId, onBack }: { matterId: string; onBack: () => void }) {
  const queryClient = useQueryClient();
  const [matter, setMatter] = useState<LegalMatter>();
  const [workItems, setWorkItems] = useState<WorkItem[]>([]);
  const [agentPlans, setAgentPlans] = useState<AgentExecutionPlanRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [dialog, setDialog] = useState<Dialog>();
  const [submitting, setSubmitting] = useState(false);
  const [priorityForm] = Form.useForm<PriorityValues>();
  const [deadlineForm] = Form.useForm<DeadlineValues>();
  const [dependencyForm] = Form.useForm<DependencyValues>();
  const [reviewForm] = Form.useForm<ReviewPackageValues>();
  const [reviewOpen, setReviewOpen] = useState(false);
  const [lifecycleDialog, setLifecycleDialog] = useState<LifecycleDialog>();
  const [lifecycleForm] = Form.useForm<LifecycleValues>();
  const [butlerForm] = Form.useForm<ButlerValues>();
  const [butlerOpen, setButlerOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const [matterValue, workItemValues, planValues] = await Promise.all([
        legalApi.getMatter(matterId),
        legalApi.listWorkItems(matterId),
        legalApi.listLegalAgentPlans(matterId),
      ]);
      setMatter(matterValue);
      setWorkItems(workItemValues);
      setAgentPlans(planValues);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '加载事项详情失败');
    } finally {
      setLoading(false);
    }
  }, [matterId]);

  useEffect(() => { void load(); }, [load]);

  const refreshOperationalState = async () => {
    await load();
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['matter', matterId] }),
      queryClient.invalidateQueries({ queryKey: ['matters'] }),
      queryClient.invalidateQueries({ queryKey: ['work-items', matterId] }),
      queryClient.invalidateQueries({ queryKey: ['dashboard', 'today'] }),
    ]);
  };

  const openPriority = (workItem: WorkItem) => {
    priorityForm.setFieldsValue({
      priority: workItem.priority,
      completeAt: workItem.plannedCompleteAt ? dayjs(workItem.plannedCompleteAt) : undefined,
      reasons: workItem.priorityReasons.join('\n'),
      overrideReason: workItem.overrideReason ?? undefined,
    });
    setDialog({ type: 'priority', workItem });
  };

  const openDeadline = (workItem: WorkItem) => {
    deadlineForm.setFieldsValue({ deadlineType: 'internal', dueAt: dayjs().add(1, 'day'), isHard: false });
    setDialog({ type: 'deadline', workItem });
  };

  const openDependency = (workItem: WorkItem) => {
    dependencyForm.setFieldsValue({ dependencyType: 'material' });
    setDialog({ type: 'dependency', workItem });
  };

  const openLifecycle = (workItem: WorkItem, action: WorkItemLifecycleAction) => {
    lifecycleForm.setFieldsValue({
      reason: undefined,
      waitingPartyId: workItem.waitingPartyId ?? undefined,
      blockerOwnerId: workItem.blockerOwnerId ?? undefined,
      ownerId: workItem.ownerId,
      deadline: workItem.plannedCompleteAt ? dayjs(workItem.plannedCompleteAt) : undefined,
      nextAction: workItem.nextAction,
    });
    setLifecycleDialog({ action, workItem });
  };

  const openReviewPackage = () => {
    if (!matter) return;
    reviewForm.setFieldsValue({
      title: `${matter.title} - 外发回复审核`,
      background: matter.summary ?? matter.title,
      reasoning: '基于当前已确认事实和公司处理口径形成回复，所有外发内容须经法务审核。',
      proposedContent: '',
    });
    setReviewOpen(true);
  };

  const openButler = () => {
    butlerForm.setFieldsValue({
      objective: matter?.objective ?? undefined,
      workItemId: workItems[0]?.id,
      specialRequirements: undefined,
      specialistOnly: undefined,
    });
    setButlerOpen(true);
  };

  const requestButler = async () => {
    if (!matter) return;
    const values = await butlerForm.validateFields();
    const key = `legal-butler:${matter.id}`;
    const context = getOrCreateMutationContext(key, values);
    setSubmitting(true);
    try {
      await legalApi.requestLegalAgentPlan(matter.id, values, context);
      clearMutationContext(key);
      message.success('管家任务已进入确定性执行队列，不会自动发送消息');
      setButlerOpen(false);
      await load();
    } catch (reason) {
      if (isDefinitiveMutationFailure(reason)) clearMutationContext(key);
      message.error(reason instanceof Error ? reason.message : '管家任务提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  const rerunButlerStep = async (planId: string, stepId: string) => {
    const key = `legal-agent-rerun:${planId}:${stepId}`;
    const context = getOrCreateMutationContext(key, { planId, stepId });
    try {
      await legalApi.rerunLegalAgentStep(planId, stepId, context);
      clearMutationContext(key);
      message.success('Step 已重新进入执行队列');
      await load();
    } catch (reason) {
      if (isDefinitiveMutationFailure(reason)) clearMutationContext(key);
      message.error(reason instanceof Error ? reason.message : 'Step 重跑失败');
    }
  };

  const createReviewPackage = async () => {
    if (!matter) return;
    const values = await reviewForm.validateFields();
    if (!values.replyToMessageId?.trim() && !values.receiveId?.trim()) {
      message.error('请填写回复原消息ID或收件人Open ID');
      return;
    }
    setSubmitting(true);
    try {
      await legalApi.createReviewPackage({
        matterId: matter.id,
        workItemId: workItems[0]?.id,
        packageType: 'external_message',
        title: values.title,
        background: values.background,
        confirmedFacts: [],
        unconfirmedFacts: [],
        reasoning: values.reasoning,
        risks: [],
        alternatives: [],
        citations: [],
        proposedContent: values.proposedContent,
        target: values.replyToMessageId
          ? { replyToMessageId: values.replyToMessageId, messageType: 'text' }
          : { receiveId: values.receiveId, receiveIdType: 'open_id', messageType: 'text' },
        submitForReview: true,
      });
      message.success('审核包已创建并提交审核');
      setReviewOpen(false);
      await queryClient.invalidateQueries({ queryKey: ['dashboard', 'today'] });
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : '创建审核包失败');
    } finally {
      setSubmitting(false);
    }
  };

  const submitDialog = async () => {
    if (!dialog) return;
    let dependencyMutationKey: string | undefined;
    setSubmitting(true);
    try {
      if (dialog.type === 'priority') {
        const values = await priorityForm.validateFields();
        await legalApi.confirmPriority(dialog.workItem.id, {
          workItemVersion: dialog.workItem.version,
          confirmedPriority: values.priority,
          confirmedCompleteAt: values.completeAt?.toISOString(),
          reasons: values.reasons.split('\n').map((value) => value.trim()).filter(Boolean),
          overrideReason: values.overrideReason,
        });
        message.success('优先级和完成时间已确认');
      } else if (dialog.type === 'deadline') {
        const values = await deadlineForm.validateFields();
        await legalApi.createDeadline(dialog.workItem.id, {
          deadlineType: values.deadlineType,
          source: 'legal_confirmed',
          dueAt: values.dueAt.toISOString(),
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Singapore',
          isHard: values.isHard,
          sourceReference: values.sourceReference,
          reminderPolicy: { reminders: ['24h', '2h'] },
        });
        message.success('期限已创建');
      } else {
        const values = await dependencyForm.validateFields();
        const payload = {
          ...values,
          workItemVersion: dialog.workItem.version,
        };
        dependencyMutationKey = `create-dependency:${dialog.workItem.id}`;
        const context = getOrCreateMutationContext(dependencyMutationKey, payload);
        await legalApi.createDependency(dialog.workItem.id, payload, context);
        clearMutationContext(dependencyMutationKey);
        message.success('依赖关系已创建');
      }
      setDialog(undefined);
      await refreshOperationalState();
    } catch (reason) {
      if (dependencyMutationKey && isDefinitiveMutationFailure(reason)) {
        clearMutationContext(dependencyMutationKey);
      }
      message.error(reason instanceof Error ? reason.message : '操作失败');
    } finally {
      setSubmitting(false);
    }
  };

  const submitLifecycle = async () => {
    if (!lifecycleDialog) return;
    const values = await lifecycleForm.validateFields();
    const { workItem, action } = lifecycleDialog;
    const payload = { ...values, deadline: values.deadline?.toISOString() };
    const key = `work-item:${workItem.id}:${action}`;
    const context = getOrCreateMutationContext(key, payload);
    setSubmitting(true);
    try {
      if (action === 'owner') {
        await legalApi.changeWorkItemOwner(workItem.id, workItem.version, {
          ownerId: values.ownerId!, reason: values.reason,
        }, context);
      } else if (action === 'changeDeadline') {
        await legalApi.changeWorkItemDeadline(workItem.id, workItem.version, {
          deadline: values.deadline!.toISOString(), reason: values.reason,
        }, context);
      } else if (action === 'nextAction') {
        await legalApi.changeWorkItemNextAction(workItem.id, workItem.version, {
          nextAction: values.nextAction!, reason: values.reason,
        }, context);
      } else {
        await legalApi.applyWorkItemAction(workItem.id, action, workItem.version, {
          reason: values.reason,
          waitingPartyId: values.waitingPartyId,
          blockerOwnerId: values.blockerOwnerId,
        }, context);
      }
      clearMutationContext(key);
      message.success('WorkItem 已更新');
      setLifecycleDialog(undefined);
      await refreshOperationalState();
    } catch (reason) {
      if (isDefinitiveMutationFailure(reason)) clearMutationContext(key);
      message.error(reason instanceof Error ? reason.message : 'WorkItem 更新失败');
    } finally {
      setSubmitting(false);
    }
  };

  const resolveDependency = async (item: WorkItem, dependency: WorkItemDependency) => {
    const payload = { dependencyVersion: dependency.version, reason: '依赖条件已经满足' };
    const key = `resolve-dependency:${dependency.id}`;
    const context = getOrCreateMutationContext(key, payload);
    try {
      await legalApi.resolveDependency(
        item.id, dependency.id, item.version, dependency.version,
        payload.reason, context,
      );
      clearMutationContext(key);
      message.success('依赖已解决');
      await refreshOperationalState();
    } catch (reason) {
      if (isDefinitiveMutationFailure(reason)) clearMutationContext(key);
      message.error(reason instanceof Error ? reason.message : '解决依赖失败');
    }
  };

  return (
    <div className="page task-detail-page">
      <Button type="text" icon={<ArrowLeftOutlined />} onClick={onBack}>返回事项中心</Button>
      {error && <Alert type="error" showIcon message={error} action={<Button onClick={() => void load()}>重试</Button>} />}
      <Spin spinning={loading}>
        {matter && (
          <>
            <div className="detail-header">
              <div>
                <Text type="secondary">{matter.matterNumber}</Text>
                <Title level={2}>{matter.title}</Title>
                <Space wrap>
                  <Tag color="blue">{categoryLabels[matter.primaryCategory]}</Tag>
                  <Tag color={matter.legalRisk === 'critical' ? 'red' : 'gold'}>{riskLabels[matter.legalRisk]}</Tag>
                  <Tag>{matter.lifecycleStatus}</Tag><Tag>{matter.workStatus}</Tag>
                </Space>
              </div>
              <Space><Button type="primary" icon={<RobotOutlined />} onClick={openButler}>让管家处理</Button><Button onClick={openReviewPackage}>创建审核包</Button><Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button></Space>
            </div>
            <div className="detail-grid">
              <main className="detail-main">
                <Card bordered={false} title="事项背景与目标">
                  <Paragraph>{matter.summary || '尚未填写事项背景。'}</Paragraph>
                  <Text strong>处理目标</Text>
                  <Paragraph>{matter.objective || '尚未填写处理目标。'}</Paragraph>
                </Card>
                <Card bordered={false} title={`行动任务（${workItems.length}）`}>
                  {workItems.length === 0 ? <Empty description="暂无行动任务" /> : (
                    <List
                      dataSource={workItems}
                      renderItem={(item) => (
                        <WorkItemCard
                          item={item}
                          onPriority={() => openPriority(item)}
                          onDeadline={() => openDeadline(item)}
                          onDependency={() => openDependency(item)}
                          onLifecycle={(action) => openLifecycle(item, action)}
                          onResolveDependency={(dependency) => void resolveDependency(item, dependency)}
                        />
                      )}
                    />
                  )}
                </Card>
                <LegalButlerPanel
                  plans={agentPlans}
                  loading={loading}
                  onRefresh={() => void load()}
                  onRerun={rerunButlerStep}
                />
              </main>
              <aside className="detail-sidebar">
                <Card title="事项字段" bordered={false}>
                  <Descriptions column={1} size="small" items={[
                    { key: 'owner', label: '负责人', children: matter.ownerId },
                    { key: 'priority', label: '事项优先级', children: `${priorityLabels[matter.priority]} · ${matter.prioritySource === 'legal_confirmed' ? '法务确认' : matter.prioritySource}` },
                    { key: 'deadline', label: '目标期限', children: matter.targetDeadlineAt ? new Date(matter.targetDeadlineAt).toLocaleString() : '待确认' },
                    { key: 'next-action', label: '下一步行动', children: matter.nextAction || '待确认' },
                    { key: 'risk', label: '法律风险', children: riskLabels[matter.legalRisk] },
                    { key: 'impact', label: '业务影响', children: matter.businessImpact },
                    { key: 'secret', label: '保密等级', children: matter.confidentiality },
                    { key: 'opened', label: '开启时间', children: new Date(matter.openedAt).toLocaleString() },
                    { key: 'version', label: '版本', children: matter.version },
                  ]} />
                </Card>
              </aside>
            </div>
          </>
        )}
      </Spin>

      <Modal
        open={butlerOpen}
        title="让法务管家处理"
        width={680}
        confirmLoading={submitting}
        onCancel={() => setButlerOpen(false)}
        onOk={() => void requestButler()}
        okText="进入执行队列"
      >
        <Alert
          type="info"
          showIcon
          message="管家只负责规划、调用注册专业 Agent 并综合；结果进入人工审核，不会自动发送。"
          style={{ marginBottom: 16 }}
        />
        <Form form={butlerForm} layout="vertical">
          <Form.Item name="objective" label="本次目标"><Input.TextArea rows={3} placeholder="例如：审查第8.2条责任上限及图片授权链" /></Form.Item>
          <Form.Item name="specialRequirements" label="特别要求"><Input.TextArea rows={3} placeholder="例如：优先给出今日可执行的补件清单" /></Form.Item>
          <Form.Item name="workItemId" label="关联 WorkItem"><Select allowClear options={workItems.map((item) => ({ value: item.id, label: item.title }))} /></Form.Item>
          <Form.Item name="specialistOnly" label="只运行某个专业 Agent（可选）"><Select allowClear options={[
            { value: 'legal_consultation', label: '一般法律咨询' },
            { value: 'contract_review', label: '合同审查' },
            { value: 'dispute_complaint', label: '争议与投诉' },
            { value: 'ip_copyright', label: '知识产权与著作权' },
            { value: 'labor_employment', label: '劳动用工' },
          ]} /></Form.Item>
        </Form>
      </Modal>

      <Modal open={reviewOpen} title="创建外发审核包" width={760} confirmLoading={submitting} onCancel={() => setReviewOpen(false)} onOk={() => void createReviewPackage()}>
        <Alert type="warning" showIcon message="创建后仅进入待审核状态，不会直接发送。审核通过后仍需执行外发入队操作。" style={{ marginBottom: 16 }} />
        <Form form={reviewForm} layout="vertical">
          <Form.Item name="title" label="审核包标题" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="background" label="事项背景" rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="reasoning" label="为什么这样处理" rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="proposedContent" label="拟发送内容" rules={[{ required: true }]}><Input.TextArea rows={7} /></Form.Item>
          <Space align="start" wrap>
            <Form.Item name="replyToMessageId" label="回复原消息ID"><Input style={{ width: 280 }} /></Form.Item>
            <Form.Item name="receiveId" label="收件人Open ID"><Input style={{ width: 280 }} /></Form.Item>
          </Space>
        </Form>
      </Modal>

      <Modal open={dialog?.type === 'priority'} title="确认优先级与完成时间" confirmLoading={submitting} onCancel={() => setDialog(undefined)} onOk={() => void submitDialog()}>
        <Form form={priorityForm} layout="vertical">
          <Form.Item name="priority" label="确认优先级" rules={[{ required: true }]}><Select options={Object.entries(priorityLabels).map(([value, label]) => ({ value, label }))} /></Form.Item>
          <Form.Item name="completeAt" label="计划完成时间"><DatePicker showTime style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="reasons" label="排序理由"><Input.TextArea rows={3} placeholder="每行一条理由" /></Form.Item>
          <Form.Item name="overrideReason" label="覆盖AI建议原因"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      <Modal open={dialog?.type === 'deadline'} title="创建期限" confirmLoading={submitting} onCancel={() => setDialog(undefined)} onOk={() => void submitDialog()}>
        <Form form={deadlineForm} layout="vertical">
          <Form.Item name="deadlineType" label="期限类型" rules={[{ required: true }]}><Select options={[
            ['legal', '法定期限'], ['platform', '平台期限'], ['contractual', '合同期限'], ['business', '业务期限'], ['internal', '内部期限'], ['reminder', '提醒节点'],
          ].map(([value, label]) => ({ value, label }))} /></Form.Item>
          <Form.Item name="dueAt" label="到期时间" rules={[{ required: true }]}><DatePicker showTime style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="isHard" label="是否硬期限"><Select options={[{ value: true, label: '是' }, { value: false, label: '否' }]} /></Form.Item>
          <Form.Item name="sourceReference" label="期限来源"><Input placeholder="例如：法院通知、业务上线计划" /></Form.Item>
        </Form>
      </Modal>

      <Modal open={dialog?.type === 'dependency'} title="创建任务依赖" confirmLoading={submitting} onCancel={() => setDialog(undefined)} onOk={() => void submitDialog()}>
        <Form form={dependencyForm} layout="vertical">
          <Form.Item name="dependencyType" label="依赖类型" rules={[{ required: true }]}><Select options={[
            ['finish_to_start', '前置任务完成'], ['start_to_start', '同步开始'], ['external_input', '等待外部输入'], ['approval', '等待审批'], ['material', '等待材料'],
          ].map(([value, label]) => ({ value, label }))} /></Form.Item>
          <Form.Item name="dependsOnWorkItemId" label="前置任务ID"><Input /></Form.Item>
          <Form.Item name="externalPartyId" label="等待对象"><Input /></Form.Item>
          <Form.Item name="description" label="依赖说明"><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Modal>

      <Modal open={Boolean(lifecycleDialog)} title="更新 WorkItem" confirmLoading={submitting} onCancel={() => setLifecycleDialog(undefined)} onOk={() => void submitLifecycle()}>
        <Alert type="info" showIcon message="所有状态和字段修改都经过领域规则、版本校验、审计与幂等保护。" style={{ marginBottom: 16 }} />
        <Form form={lifecycleForm} layout="vertical">
          {lifecycleDialog?.action === 'owner' && <Form.Item name="ownerId" label="新负责人" rules={[{ required: true }]}><Input /></Form.Item>}
          {lifecycleDialog?.action === 'changeDeadline' && <Form.Item name="deadline" label="新计划完成时间" rules={[{ required: true }]}><DatePicker showTime style={{ width: '100%' }} /></Form.Item>}
          {lifecycleDialog?.action === 'nextAction' && <Form.Item name="nextAction" label="新下一步行动" rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item>}
          {lifecycleDialog?.action === 'wait' && <Form.Item name="waitingPartyId" label="等待对象"><Input /></Form.Item>}
          {lifecycleDialog?.action === 'block' && <Form.Item name="blockerOwnerId" label="阻塞责任人" rules={[{ required: true }]}><Input /></Form.Item>}
          <Form.Item name="reason" label="操作原因" rules={['pause', 'wait', 'block', 'cancel', 'reopen'].includes(lifecycleDialog?.action ?? '') ? [{ required: true }] : undefined}><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

function WorkItemCard({ item, onPriority, onDeadline, onDependency, onLifecycle, onResolveDependency }: {
  item: WorkItem;
  onPriority: () => void;
  onDeadline: () => void;
  onDependency: () => void;
  onLifecycle: (action: WorkItemLifecycleAction) => void;
  onResolveDependency: (dependency: WorkItemDependency) => void;
}) {
  const [deadlines, setDeadlines] = useState<Deadline[]>([]);
  const [dependencies, setDependencies] = useState<WorkItemDependency[]>([]);
  useEffect(() => {
    void Promise.all([legalApi.listDeadlines(item.id), legalApi.listDependencies(item.id)])
      .then(([deadlineValues, dependencyValues]) => { setDeadlines(deadlineValues); setDependencies(dependencyValues); })
      .catch(() => undefined);
  }, [item.id]);

  return (
    <List.Item>
      <Card size="small" style={{ width: '100%' }}>
        <Space wrap>
          <Tag>{workStatusLabels[item.status] ?? item.status}</Tag>
          <Tag color={item.priority === 'urgent' ? 'red' : item.priority === 'high' ? 'orange' : 'blue'}>{priorityLabels[item.priority]}</Tag>
          {item.priorityConfirmedBy && <Tag color="green">法务已确认</Tag>}
          {item.isBlocked && <Tag color="red">阻塞</Tag>}
        </Space>
        <Title level={5} style={{ marginTop: 12 }}>{item.title}</Title>
        <Paragraph>下一步：{item.nextAction}</Paragraph>
        <Text type="secondary">负责人：{item.ownerId} · 计划完成：{item.plannedCompleteAt ? new Date(item.plannedCompleteAt).toLocaleString() : '待确认'}</Text>
        <div style={{ marginTop: 12 }}>
          {deadlines.map((value) => <Tag icon={<CalendarOutlined />} key={value.id} color={value.isHard ? 'red' : 'gold'}>{new Date(value.dueAt).toLocaleString()}</Tag>)}
          {dependencies.map((value) => <Tag icon={<LinkOutlined />} key={value.id}>{value.dependencyType}: {value.description || value.externalPartyId || value.dependsOnWorkItemId}{value.status === 'active' && <Button type="link" size="small" onClick={() => onResolveDependency(value)}>解决</Button>}</Tag>)}
        </div>
        <WorkItemActions
          status={item.status}
          onPriority={onPriority}
          onDeadline={onDeadline}
          onDependency={onDependency}
          onLifecycle={onLifecycle}
        />
      </Card>
    </List.Item>
  );
}
