import {
  Alert,
  App as AntApp,
  Button,
  Collapse,
  DatePicker,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd';
import { ArrowLeftOutlined, CalendarOutlined, LinkOutlined, ReloadOutlined, RobotOutlined } from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import { useCallback, useEffect, useRef, useState } from 'react';
import StatePanel from '../components/StatePanel';
import { legalApi } from '../services/api';
import { classifyApiFailure, type ApiFailureState } from '../services/apiFailure';
import { categoryLabels, matterWorkStatusLabels, priorityLabels, riskLabels, workStatusLabels } from '../services/apiLabels';
import type { Deadline, LegalMatter, Priority, WorkItem, WorkItemDependency } from '../types/api';

const { Title, Text, Paragraph } = Typography;

type Dialog = { type: 'priority' | 'deadline' | 'dependency'; workItem: WorkItem } | undefined;

interface PriorityValues { priority: Priority; completeAt?: Dayjs; reasons: string; overrideReason?: string }
interface DeadlineValues { deadlineType: string; dueAt: Dayjs; isHard: boolean; sourceReference?: string }
interface DependencyValues { dependencyType: string; dependsOnWorkItemId?: string; externalPartyId?: string; description?: string }
interface ReviewPackageValues { title: string; background: string; reasoning: string; proposedContent: string; receiveId?: string; replyToMessageId?: string }

const lifecycleLabels: Record<LegalMatter['lifecycleStatus'], string> = {
  open: '进行中',
  resolved: '已解决',
  closed: '已关闭',
  reopened: '已重新开启',
  cancelled: '已取消',
};

const businessImpactLabels: Record<LegalMatter['businessImpact'], string> = {
  company: '公司级',
  department: '部门级',
  project: '项目级',
  general: '一般事项',
};

const confidentialityLabels: Record<LegalMatter['confidentiality'], string> = {
  internal: '内部',
  confidential: '保密',
  restricted: '严格限制',
};

const stageLabels: Record<string, string> = {
  intake: '需求接收',
  analysis: '分析处理中',
  drafting: '起草处理中',
  review: '审核准备',
  response: '应对处理',
  closing: '结项处理中',
};

const deadlineTypeLabels: Record<string, string> = {
  legal: '法定期限',
  platform: '平台期限',
  contractual: '合同期限',
  business: '业务期限',
  internal: '内部期限',
  reminder: '提醒节点',
};

const dependencyTypeLabels: Record<string, string> = {
  finish_to_start: '前置任务完成',
  start_to_start: '同步开始',
  external_input: '等待外部输入',
  approval: '等待审批',
  material: '等待材料',
};

function errorMessage(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}

function isFormValidationError(reason: unknown) {
  return typeof reason === 'object' && reason !== null && 'errorFields' in reason;
}

export default function TaskDetailPage({ matterId, onBack, onReviewPackageCreated }: { matterId: string; onBack: () => void; onReviewPackageCreated: (reviewPackageId: string) => void }) {
  const { message: messageApi, modal: modalApi } = AntApp.useApp();
  const [matter, setMatter] = useState<LegalMatter>();
  const [workItems, setWorkItems] = useState<WorkItem[]>([]);
  const [matterLoading, setMatterLoading] = useState(true);
  const [workItemsLoading, setWorkItemsLoading] = useState(true);
  const [matterFailure, setMatterFailure] = useState<ApiFailureState>();
  const [workItemsFailure, setWorkItemsFailure] = useState<ApiFailureState>();
  const [dialog, setDialog] = useState<Dialog>();
  const [dialogDirty, setDialogDirty] = useState(false);
  const [reviewDirty, setReviewDirty] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [resourceRevision, setResourceRevision] = useState(0);
  const submitInFlight = useRef(false);
  const [priorityForm] = Form.useForm<PriorityValues>();
  const [deadlineForm] = Form.useForm<DeadlineValues>();
  const [dependencyForm] = Form.useForm<DependencyValues>();
  const [reviewForm] = Form.useForm<ReviewPackageValues>();
  const [reviewOpen, setReviewOpen] = useState(false);

  const loadMatter = useCallback(async () => {
    setMatterLoading(true);
    setMatterFailure(undefined);
    try {
      setMatter(await legalApi.getMatter(matterId));
    } catch (reason) {
      setMatter(undefined);
      setMatterFailure(classifyApiFailure(reason, '事项详情', '事项详情加载失败', '加载事项详情失败'));
    } finally {
      setMatterLoading(false);
    }
  }, [matterId]);

  const loadWorkItems = useCallback(async () => {
    setWorkItemsLoading(true);
    setWorkItemsFailure(undefined);
    try {
      setWorkItems(await legalApi.listWorkItems(matterId));
    } catch (reason) {
      setWorkItems([]);
      setWorkItemsFailure(classifyApiFailure(reason, '行动任务', '行动任务加载失败', '加载行动任务失败'));
    } finally {
      setWorkItemsLoading(false);
    }
  }, [matterId]);

  useEffect(() => {
    void loadMatter();
    void loadWorkItems();
  }, [loadMatter, loadWorkItems]);

  const refresh = () => {
    void loadMatter();
    void loadWorkItems();
    setResourceRevision((value) => value + 1);
  };

  const openPriority = (workItem: WorkItem) => {
    priorityForm.setFieldsValue({
      priority: workItem.priority,
      completeAt: workItem.plannedCompleteAt ? dayjs(workItem.plannedCompleteAt) : undefined,
      reasons: workItem.priorityReasons.join('\n'),
      overrideReason: workItem.overrideReason ?? undefined,
    });
    setDialogDirty(false);
    setDialog({ type: 'priority', workItem });
  };

  const openDeadline = (workItem: WorkItem) => {
    deadlineForm.setFieldsValue({ deadlineType: 'internal', dueAt: dayjs().add(1, 'day'), isHard: false, sourceReference: undefined });
    setDialogDirty(false);
    setDialog({ type: 'deadline', workItem });
  };

  const openDependency = (workItem: WorkItem) => {
    dependencyForm.setFieldsValue({ dependencyType: 'material', dependsOnWorkItemId: undefined, externalPartyId: undefined, description: undefined });
    setDialogDirty(false);
    setDialog({ type: 'dependency', workItem });
  };

  const openReviewPackage = () => {
    if (!matter) return;
    reviewForm.setFieldsValue({
      title: `${matter.title} - 外发回复审核`,
      background: matter.summary ?? matter.title,
      reasoning: '基于当前已确认事实和公司处理口径形成回复，所有外发内容须经法务审核。',
      proposedContent: '',
      receiveId: undefined,
      replyToMessageId: undefined,
    });
    setReviewDirty(false);
    setReviewOpen(true);
  };

  const confirmDiscard = (onDiscard: () => void) => {
    modalApi.confirm({
      title: '放弃未保存的修改？',
      content: '当前填写的内容尚未保存。',
      okText: '放弃修改',
      cancelText: '继续编辑',
      okButtonProps: { danger: true },
      onOk: onDiscard,
    });
  };

  const requestDialogClose = () => {
    if (submitting) return;
    if (!dialogDirty) {
      setDialog(undefined);
      return;
    }
    confirmDiscard(() => {
      setDialogDirty(false);
      setDialog(undefined);
    });
  };

  const requestReviewClose = () => {
    if (submitting) return;
    if (!reviewDirty) {
      setReviewOpen(false);
      return;
    }
    confirmDiscard(() => {
      setReviewDirty(false);
      setReviewOpen(false);
    });
  };

  const createReviewPackage = async () => {
    if (!matter || submitInFlight.current) return;
    submitInFlight.current = true;
    setSubmitting(true);
    try {
      const values = await reviewForm.validateFields();
      const replyToMessageId = values.replyToMessageId?.trim();
      const receiveId = values.receiveId?.trim();
      if (!replyToMessageId && !receiveId) {
        reviewForm.setFields([
          { name: 'replyToMessageId', errors: ['请填写回复原消息 ID 或收件人 Open ID'] },
          { name: 'receiveId', errors: [] },
        ]);
        return;
      }
      const result = await legalApi.createReviewPackage({
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
        target: replyToMessageId
          ? { replyToMessageId, messageType: 'text' }
          : { receiveId, receiveIdType: 'open_id', messageType: 'text' },
        submitForReview: true,
      });
      messageApi.success('审核包已创建并提交审核');
      setReviewDirty(false);
      setReviewOpen(false);
      onReviewPackageCreated(result.reviewPackageId);
    } catch (reason) {
      if (!isFormValidationError(reason)) messageApi.error(errorMessage(reason, '创建审核包失败'));
    } finally {
      submitInFlight.current = false;
      setSubmitting(false);
    }
  };

  const submitDialog = async () => {
    if (!dialog || submitInFlight.current) return;
    submitInFlight.current = true;
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
        messageApi.success('优先级和完成时间已确认');
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
        messageApi.success('期限已创建');
      } else {
        const values = await dependencyForm.validateFields();
        await legalApi.createDependency(dialog.workItem.id, values);
        messageApi.success('依赖关系已创建');
      }
      setDialogDirty(false);
      setDialog(undefined);
      await loadWorkItems();
      setResourceRevision((value) => value + 1);
    } catch (reason) {
      if (!isFormValidationError(reason)) messageApi.error(errorMessage(reason, '操作失败'));
    } finally {
      submitInFlight.current = false;
      setSubmitting(false);
    }
  };

  const dialogOkText = dialog?.type === 'priority' ? '确认优先级' : dialog?.type === 'deadline' ? '创建期限' : '创建依赖';

  return (
    <div className="page task-detail-page">
      <Button type="text" icon={<ArrowLeftOutlined />} onClick={onBack}>返回事项中心</Button>

      {matterLoading && !matter && <StatePanel variant="loading" title="正在加载事项详情" description="正在读取已确认的事项信息。" />}
      {matterFailure && (
        <StatePanel
          {...matterFailure}
          action={<Button onClick={() => void loadMatter()}>重试事项</Button>}
        />
      )}

      {matter && (
        <>
          <header className="detail-header">
            <div>
              <Text type="secondary">{matter.matterNumber}</Text>
              <Title level={2}>{matter.title}</Title>
              <Space wrap>
                <Tag color="blue">{categoryLabels[matter.primaryCategory]}</Tag>
                <Tag>{lifecycleLabels[matter.lifecycleStatus]}</Tag>
              </Space>
            </div>
            <Space wrap>
              <Button icon={<RobotOutlined />} onClick={openReviewPackage}>创建审核包</Button>
              <Button icon={<ReloadOutlined />} onClick={refresh}>刷新</Button>
            </Space>
          </header>

          <section className="matter-overview" role="region" aria-label="事项决策概览">
            <OverviewItem label="法律风险" value={`${riskLabels[matter.legalRisk]}风险`} tone={matter.legalRisk === 'critical' || matter.legalRisk === 'high' ? 'danger' : 'default'} />
            <OverviewItem label="工作状态" value={matterWorkStatusLabels[matter.workStatus]} />
            <OverviewItem label="负责人标识" value={matter.ownerId} />
            <OverviewItem label="处理目标" value={matter.objective || '待确认'} />
            <OverviewItem label="当前阶段" value={matter.currentStage ? (stageLabels[matter.currentStage] ?? '处理中') : '待确认'} />
          </section>

          <div className="detail-grid">
            <main className="detail-main">
              <section className="detail-section" aria-labelledby="work-items-title">
                <div className="detail-section-heading">
                  <Title level={4} id="work-items-title">行动任务（{workItems.length}）</Title>
                </div>
                {workItemsLoading ? (
                  <StatePanel variant="loading" title="正在加载行动任务" />
                ) : workItemsFailure ? (
                  <StatePanel
                    {...workItemsFailure}
                    action={<Button onClick={() => void loadWorkItems()}>重试任务</Button>}
                  />
                ) : workItems.length === 0 ? (
                  <Empty description="暂无行动任务" />
                ) : (
                  <List
                    className="work-item-list"
                    dataSource={workItems}
                    renderItem={(item) => (
                      <WorkItemPanel
                        item={item}
                        resourceRevision={resourceRevision}
                        onPriority={() => openPriority(item)}
                        onDeadline={() => openDeadline(item)}
                        onDependency={() => openDependency(item)}
                      />
                    )}
                  />
                )}
              </section>
            </main>

            <aside className="detail-sidebar">
              <section className="detail-section" aria-labelledby="matter-fields-title">
                <Title level={4} id="matter-fields-title">补充信息</Title>
                <dl className="matter-field-list">
                  <div><dt>业务影响</dt><dd>{businessImpactLabels[matter.businessImpact]}</dd></div>
                  <div><dt>保密等级</dt><dd>{confidentialityLabels[matter.confidentiality]}</dd></div>
                  <div><dt>开启时间</dt><dd>{new Date(matter.openedAt).toLocaleString()}</dd></div>
                </dl>
                <Collapse
                  className="technical-details"
                  ghost
                  items={[{
                    key: 'technical',
                    label: '技术详情',
                    children: (
                      <dl className="matter-field-list">
                        <div><dt>lifecycleStatus</dt><dd>{matter.lifecycleStatus}</dd></div>
                        <div><dt>workStatus</dt><dd>{matter.workStatus}</dd></div>
                        <div><dt>currentStage</dt><dd>{matter.currentStage || 'null'}</dd></div>
                        <div><dt>version</dt><dd>{matter.version}</dd></div>
                      </dl>
                    ),
                  }]}
                />
              </section>
            </aside>
          </div>

          <section className="detail-section matter-context" aria-labelledby="matter-context-title">
            <Title level={4} id="matter-context-title">事项背景</Title>
            <Paragraph>{matter.summary || '尚未填写事项背景。'}</Paragraph>
          </section>
        </>
      )}

      <Modal
        className="matter-action-modal matter-review-modal"
        open={reviewOpen}
        title="创建外发审核包"
        width={760}
        okText="创建并提交审核"
        cancelText="取消"
        confirmLoading={submitting}
        okButtonProps={{ disabled: submitting }}
        cancelButtonProps={{ disabled: submitting }}
        closable={!submitting}
        maskClosable={!submitting}
        keyboard={!submitting}
        destroyOnHidden
        forceRender
        onCancel={requestReviewClose}
        onOk={() => void createReviewPackage()}
      >
        <Alert type="warning" showIcon message="创建后仅进入待审核状态，不会直接发送。审核通过后仍需执行外发入队操作。" style={{ marginBottom: 16 }} />
        <Form form={reviewForm} layout="vertical" onValuesChange={() => setReviewDirty(true)}>
          <Form.Item name="title" label="审核包标题" rules={[{ required: true, message: '请填写审核包标题' }]}><Input /></Form.Item>
          <Form.Item name="background" label="事项背景" rules={[{ required: true, message: '请填写事项背景' }]}><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="reasoning" label="为什么这样处理" rules={[{ required: true, message: '请填写处理理由' }]}><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="proposedContent" label="拟发送内容" rules={[{ required: true, message: '请填写拟发送内容' }]}><Input.TextArea rows={7} /></Form.Item>
          <div className="review-target-grid">
            <Form.Item name="replyToMessageId" label="回复原消息 ID"><Input /></Form.Item>
            <Form.Item name="receiveId" label="收件人 Open ID"><Input /></Form.Item>
          </div>
        </Form>
      </Modal>

      <Modal
        className="matter-action-modal"
        open={Boolean(dialog)}
        title={dialog?.type === 'priority' ? '确认优先级与完成时间' : dialog?.type === 'deadline' ? '创建期限' : '创建任务依赖'}
        okText={dialogOkText}
        cancelText="取消"
        confirmLoading={submitting}
        okButtonProps={{ disabled: submitting }}
        cancelButtonProps={{ disabled: submitting }}
        closable={!submitting}
        maskClosable={!submitting}
        keyboard={!submitting}
        destroyOnHidden
        forceRender
        onCancel={requestDialogClose}
        onOk={() => void submitDialog()}
      >
        {dialog?.type === 'priority' && (
          <Form form={priorityForm} layout="vertical" onValuesChange={() => setDialogDirty(true)}>
            <Form.Item name="priority" label="确认优先级" rules={[{ required: true, message: '请选择优先级' }]}><Select options={Object.entries(priorityLabels).map(([value, label]) => ({ value, label }))} /></Form.Item>
            <Form.Item name="completeAt" label="计划完成时间"><DatePicker showTime style={{ width: '100%' }} /></Form.Item>
            <Form.Item name="reasons" label="排序理由"><Input.TextArea rows={3} placeholder="每行一条理由" /></Form.Item>
            <Form.Item name="overrideReason" label="覆盖 AI 建议原因"><Input.TextArea rows={2} /></Form.Item>
          </Form>
        )}
        {dialog?.type === 'deadline' && (
          <Form form={deadlineForm} layout="vertical" onValuesChange={() => setDialogDirty(true)}>
            <Form.Item name="deadlineType" label="期限类型" rules={[{ required: true, message: '请选择期限类型' }]}><Select options={Object.entries(deadlineTypeLabels).map(([value, label]) => ({ value, label }))} /></Form.Item>
            <Form.Item name="dueAt" label="到期时间" rules={[{ required: true, message: '请选择到期时间' }]}><DatePicker showTime style={{ width: '100%' }} /></Form.Item>
            <Form.Item name="isHard" label="是否硬期限"><Select options={[{ value: true, label: '是' }, { value: false, label: '否' }]} /></Form.Item>
            <Form.Item name="sourceReference" label="期限来源"><Input placeholder="例如：法院通知、业务上线计划" /></Form.Item>
          </Form>
        )}
        {dialog?.type === 'dependency' && (
          <Form form={dependencyForm} layout="vertical" onValuesChange={() => setDialogDirty(true)}>
            <Form.Item name="dependencyType" label="依赖类型" rules={[{ required: true, message: '请选择依赖类型' }]}><Select options={Object.entries(dependencyTypeLabels).map(([value, label]) => ({ value, label }))} /></Form.Item>
            <Form.Item name="dependsOnWorkItemId" label="前置任务 ID"><Input /></Form.Item>
            <Form.Item name="externalPartyId" label="等待对象"><Input /></Form.Item>
            <Form.Item
              name="description"
              label="依赖说明"
              dependencies={['dependsOnWorkItemId', 'externalPartyId']}
              rules={[
                ({ getFieldValue }) => ({
                  validator(_, value: string | undefined) {
                    const candidates = [getFieldValue('dependsOnWorkItemId'), getFieldValue('externalPartyId'), value];
                    return candidates.some((candidate) => typeof candidate === 'string' && candidate.trim())
                      ? Promise.resolve()
                      : Promise.reject(new Error('请填写前置任务 ID、等待对象或依赖说明中的至少一项'));
                  },
                }),
              ]}
            >
              <Input.TextArea rows={3} />
            </Form.Item>
          </Form>
        )}
      </Modal>
    </div>
  );
}

function OverviewItem({ label, value, tone = 'default' }: { label: string; value: string; tone?: 'default' | 'danger' }) {
  return (
    <div className={`matter-overview-item matter-overview-item--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function WorkItemPanel({ item, resourceRevision, onPriority, onDeadline, onDependency }: {
  item: WorkItem;
  resourceRevision: number;
  onPriority: () => void;
  onDeadline: () => void;
  onDependency: () => void;
}) {
  const [deadlines, setDeadlines] = useState<Deadline[]>([]);
  const [dependencies, setDependencies] = useState<WorkItemDependency[]>([]);
  const [deadlinesLoading, setDeadlinesLoading] = useState(true);
  const [dependenciesLoading, setDependenciesLoading] = useState(true);
  const [deadlinesFailure, setDeadlinesFailure] = useState<ApiFailureState>();
  const [dependenciesFailure, setDependenciesFailure] = useState<ApiFailureState>();

  const loadDeadlines = useCallback(async () => {
    setDeadlinesLoading(true);
    setDeadlinesFailure(undefined);
    try {
      setDeadlines(await legalApi.listDeadlines(item.id));
    } catch (reason) {
      setDeadlines([]);
      setDeadlinesFailure(classifyApiFailure(reason, '期限信息', '期限信息加载失败', '期限信息加载失败'));
    } finally {
      setDeadlinesLoading(false);
    }
  }, [item.id]);

  const loadDependencies = useCallback(async () => {
    setDependenciesLoading(true);
    setDependenciesFailure(undefined);
    try {
      setDependencies(await legalApi.listDependencies(item.id));
    } catch (reason) {
      setDependencies([]);
      setDependenciesFailure(classifyApiFailure(reason, '依赖信息', '依赖信息加载失败', '依赖信息加载失败'));
    } finally {
      setDependenciesLoading(false);
    }
  }, [item.id]);

  useEffect(() => { void loadDeadlines(); }, [loadDeadlines, resourceRevision]);
  useEffect(() => { void loadDependencies(); }, [loadDependencies, resourceRevision]);

  const nearestHardDeadline = deadlines
    .filter((deadline) => deadline.isHard && deadline.status === 'active')
    .sort((left, right) => new Date(left.dueAt).getTime() - new Date(right.dueAt).getTime())[0];
  const displayDate = (value: string | null | undefined) => value
    ? new Date(value).toLocaleString('zh-CN', { hour12: false })
    : '当前未记录';
  const hardDeadlineSummary = deadlinesLoading
    ? '正在加载…'
    : deadlinesFailure?.title ?? displayDate(nearestHardDeadline?.dueAt);

  return (
    <List.Item>
      <article className="work-item-panel" aria-labelledby={`work-item-${item.id}`}>
        <Space wrap>
          <Tag>{workStatusLabels[item.status] ?? '待确认'}</Tag>
          <Tag color={item.priority === 'urgent' ? 'red' : item.priority === 'high' ? 'orange' : 'blue'}>{priorityLabels[item.priority]}</Tag>
          {item.priorityConfirmedBy && <Tag color="green">法务已确认</Tag>}
          {item.isBlocked && <Tag color="red">存在阻塞</Tag>}
        </Space>
        <Title level={5} id={`work-item-${item.id}`}>{item.title}</Title>
        <section className="work-item-decision-summary" role="region" aria-label="任务决策摘要">
          <div className="work-item-decision-summary__primary">
            <span>下一步</span>
            <strong>{item.nextAction || '当前未记录'}</strong>
          </div>
          <dl>
            <div><dt>负责人标识</dt><dd>{item.ownerId || '当前未记录'}</dd></div>
            <div><dt>计划完成</dt><dd>{displayDate(item.plannedCompleteAt)}</dd></div>
            <div><dt>最近硬期限</dt><dd>{hardDeadlineSummary}</dd></div>
            <div><dt>等待对象</dt><dd>{item.waitingPartyId || '当前未记录'}</dd></div>
            <div><dt>等待原因</dt><dd>{item.waitingReason || '当前未记录'}</dd></div>
            <div><dt>阻塞原因</dt><dd>{item.blockerReason || '当前未记录'}</dd></div>
            <div><dt>解除阻塞负责人</dt><dd>{item.blockerOwnerId || '当前未记录'}</dd></div>
          </dl>
        </section>

        <div className="work-item-resources">
          <section className="work-item-resource" role="region" aria-label="期限信息">
            <strong>期限</strong>
            {deadlinesLoading ? <Text type="secondary">正在加载期限…</Text> : deadlinesFailure ? (
              <Alert
                type={deadlinesFailure.variant === 'stale' ? 'warning' : 'error'}
                showIcon
                message={deadlinesFailure.title}
                description={deadlinesFailure.description}
                action={<Button size="small" onClick={() => void loadDeadlines()}>重试期限</Button>}
              />
            ) : deadlines.length === 0 ? <Text type="secondary">暂无期限</Text> : (
              <div className="work-item-resource-tags">
                {deadlines.map((value) => (
                  <Tag icon={<CalendarOutlined />} key={value.id} color={value.isHard ? 'red' : 'gold'}>
                    {deadlineTypeLabels[value.deadlineType]} · {new Date(value.dueAt).toLocaleString()}
                  </Tag>
                ))}
              </div>
            )}
          </section>

          <section className="work-item-resource" role="region" aria-label="依赖信息">
            <strong>依赖</strong>
            {dependenciesLoading ? <Text type="secondary">正在加载依赖…</Text> : dependenciesFailure ? (
              <Alert
                type={dependenciesFailure.variant === 'stale' ? 'warning' : 'error'}
                showIcon
                message={dependenciesFailure.title}
                description={dependenciesFailure.description}
                action={<Button size="small" onClick={() => void loadDependencies()}>重试依赖</Button>}
              />
            ) : dependencies.length === 0 ? <Text type="secondary">暂无依赖</Text> : (
              <div className="work-item-resource-tags">
                {dependencies.map((value) => (
                  <Tag icon={<LinkOutlined />} key={value.id}>
                    {dependencyTypeLabels[value.dependencyType]}
                    {' · '}{value.externalPartyId || value.dependsOnWorkItemId || '对象当前未记录'}
                    {value.description ? ` · ${value.description}` : ''}
                  </Tag>
                ))}
              </div>
            )}
          </section>
        </div>

        <Space className="work-item-actions" wrap>
          <Button onClick={onPriority}>确认优先级</Button>
          <Button onClick={onDeadline}>添加期限</Button>
          <Button onClick={onDependency}>添加依赖</Button>
        </Space>
      </article>
    </List.Item>
  );
}
