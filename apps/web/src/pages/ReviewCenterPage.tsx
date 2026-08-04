import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Checkbox,
  Drawer,
  Input,
  List,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ReloadOutlined, SendOutlined } from '@ant-design/icons';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import DataBoundaryBanner from '../components/DataBoundaryBanner';
import PageHeader from '../components/PageHeader';
import ResponsiveCollection from '../components/ResponsiveCollection';
import StatePanel from '../components/StatePanel';
import { legalApi } from '../services/api';
import { classifyApiFailure, type ApiFailureState } from '../services/apiFailure';
import { formatCommunicationTarget } from '../services/communicationTarget';
import {
  displayValue,
  reviewDecisionLabels,
  reviewPackageStatusLabels,
  technicalStatusLabel,
} from '../services/apiLabels';
import type { ReviewDecision, ReviewPackage, ReviewRecord } from '../types/api';

const { Title, Text, Paragraph } = Typography;

interface ReviewDraft {
  decision: ReviewDecision;
  comments: string;
  finalContent: string;
  reusableAsExample: boolean;
}

type ReviewCenterProps = {
  reviewPackageId?: string;
  onReviewSelected: (reviewPackageId: string) => void;
  onReviewClosed: () => void;
  onMatterSelected: (matterId: string) => void;
};

const statusColor: Record<string, string> = {
  approved: 'green',
  pending_review: 'blue',
  rejected: 'red',
  needs_information: 'gold',
  superseded: 'default',
  draft: 'default',
};

function reviewStatus(value: string) {
  return <Tag color={statusColor[value]}>{technicalStatusLabel(reviewPackageStatusLabels, value)}</Tag>;
}

function submittedAt(value: string | null) {
  return value ? new Date(value).toLocaleString() : '尚未提交';
}

function reviewValidationMessage(draft: ReviewDraft, active?: ReviewPackage): string | undefined {
  const approvalDecision = ['approved', 'approved_with_edits'].includes(draft.decision);
  if (approvalDecision && active && !formatCommunicationTarget(active.target).recognized) {
    return '无法核验真实外发目标，不能批准';
  }
  if (approvalDecision && !draft.finalContent.trim()) return '通过审核前必须保留最终正文';
  if (draft.decision === 'approved_with_edits' && !draft.comments.trim()) return '修改后通过必须填写修改原因';
  if (draft.decision === 'rejected' && !draft.comments.trim()) return '驳回必须填写审核理由';
  if (draft.decision === 'needs_information' && !draft.comments.trim()) return '要求补充信息必须填写具体理由';
  return undefined;
}

export default function ReviewCenterPage({ reviewPackageId, onReviewSelected, onReviewClosed, onMatterSelected }: ReviewCenterProps) {
  const { message, modal } = AntApp.useApp();
  const [packages, setPackages] = useState<ReviewPackage[]>([]);
  const [active, setActive] = useState<ReviewPackage>();
  const [records, setRecords] = useState<ReviewRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [failure, setFailure] = useState<ApiFailureState>();
  const [detailFailure, setDetailFailure] = useState<ApiFailureState>();
  const [submitFailure, setSubmitFailure] = useState<ApiFailureState>();
  const [queueNotice, setQueueNotice] = useState<string>();
  const [queueError, setQueueError] = useState<string>();
  const [submitting, setSubmitting] = useState(false);
  const [queueingId, setQueueingId] = useState<string>();
  const [draftDirty, setDraftDirty] = useState(false);
  const submittingRef = useRef(false);
  const queueingIds = useRef(new Set<string>());
  const [draft, setDraft] = useState<ReviewDraft>({
    decision: 'approved',
    comments: '',
    finalContent: '',
    reusableAsExample: false,
  });

  const resetDraft = useCallback((value: ReviewPackage) => {
    setDraft({
      decision: 'approved',
      comments: '',
      finalContent: value.proposedContent,
      reusableAsExample: false,
    });
    setDraftDirty(false);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setFailure(undefined);
    try {
      const values = await legalApi.listReviewPackages();
      setPackages(values);
    } catch (reason) {
      setPackages([]);
      setFailure(classifyApiFailure(reason, '审核数据', '审核队列加载失败', '加载审核包失败'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!reviewPackageId) {
      setActive(undefined);
      setRecords([]);
      setDetailFailure(undefined);
      setSubmitFailure(undefined);
      return;
    }
    let current = true;
    const loadDetail = async () => {
      setDetailLoading(true);
      setDetailFailure(undefined);
      setSubmitFailure(undefined);
      try {
        const fromList = packages.find((item) => item.id === reviewPackageId);
        const value = fromList ?? await legalApi.getReviewPackage(reviewPackageId);
        const reviewRecords = await legalApi.listReviewRecords(reviewPackageId);
        if (!current) return;
        setActive(value);
        setRecords(reviewRecords);
        resetDraft(value);
      } catch (reason) {
        if (current) {
          setActive(undefined);
          setRecords([]);
          setDetailFailure(classifyApiFailure(reason, '审核包详情', '审核包详情加载失败', '加载审核包详情失败'));
        }
      } finally {
        if (current) setDetailLoading(false);
      }
    };
    void loadDetail();
    return () => { current = false; };
  }, [packages, resetDraft, reviewPackageId]);

  const latestRecord = useMemo(
    () => [...records].sort((left, right) => Date.parse(right.reviewedAt) - Date.parse(left.reviewedAt))[0],
    [records],
  );
  const validationMessage = reviewValidationMessage(draft, active);
  const canSubmit = !validationMessage;

  const requestReviewNavigation = (onNavigate: () => void) => {
    if (submitting) return;
    if (!draftDirty) {
      onNavigate();
      return;
    }
    modal.confirm({
      title: '放弃未保存的审核决定？',
      content: '当前审核决定、最终正文或审核意见尚未提交。',
      okText: '放弃修改',
      cancelText: '继续审核',
      okButtonProps: { danger: true },
      onOk: () => {
        setDraftDirty(false);
        onNavigate();
      },
    });
  };

  const requestReviewClose = () => requestReviewNavigation(onReviewClosed);
  const requestMatterNavigation = () => {
    if (active) requestReviewNavigation(() => onMatterSelected(active.matterId));
  };

  const submitReview = async () => {
    if (!active || submittingRef.current || !canSubmit) return;
    submittingRef.current = true;
    setSubmitting(true);
    setSubmitFailure(undefined);
    try {
      await legalApi.reviewPackage(active.id, {
        packageVersion: active.version,
        decision: draft.decision,
        comments: draft.comments || undefined,
        finalContent: ['approved', 'approved_with_edits'].includes(draft.decision) ? draft.finalContent : undefined,
        reusableAsExample: draft.reusableAsExample,
      });
      message.success('审核决定已保存');
      setDraftDirty(false);
      onReviewClosed();
      await load();
    } catch (reason) {
      setSubmitFailure(classifyApiFailure(reason, '审核决定', '审核提交失败', '审核失败'));
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  const queue = async (value: ReviewPackage) => {
    if (value.status !== 'approved' || !formatCommunicationTarget(value.target).recognized || queueingIds.current.has(value.id)) return;
    queueingIds.current.add(value.id);
    setQueueingId(value.id);
    setQueueNotice(undefined);
    setQueueError(undefined);
    try {
      const result = await legalApi.queueCommunication(value.id);
      if (result.status !== 'queued') throw new Error(`外发接口返回未确认状态：${result.status}`);
      setQueueNotice('已进入外发队列，不等于已发送');
    } catch (reason) {
      setQueueError(reason instanceof Error ? reason.message : '外发入队门禁未通过');
    } finally {
      queueingIds.current.delete(value.id);
      setQueueingId(undefined);
    }
  };

  const columns: ColumnsType<ReviewPackage> = [
    { title: '状态', dataIndex: 'status', width: 150, render: (value: string) => reviewStatus(value) },
    {
      title: '审核包',
      dataIndex: 'title',
      width: 280,
      render: (_, item) => (
        <button className="review-title-button" aria-label={`查看审核包：${item.title}`} onClick={() => onReviewSelected(item.id)}>
          <strong>{item.title}</strong>
          <span>{item.packageType}</span>
        </button>
      ),
    },
    { title: '事项', dataIndex: 'matterId', width: 145 },
    { title: '提交时间', dataIndex: 'submittedAt', width: 170, render: submittedAt },
    { title: '目标', dataIndex: 'target', width: 210, render: (value: Record<string, unknown>) => formatCommunicationTarget(value).display },
    { title: '版本', dataIndex: 'version', width: 70, render: (value: number) => `v${value}` },
    {
      title: '外发门禁',
      width: 170,
      render: (_, item) => (
        <Button
          type="link"
          icon={<SendOutlined />}
          aria-label={`将${item.title}进入外发队列`}
          title={!formatCommunicationTarget(item.target).recognized ? '无法识别真实外发目标，不能进入外发队列' : item.status === 'approved' ? '进入外发队列，不等于已发送' : '仅已批准审核包可进入外发队列'}
          disabled={item.status !== 'approved' || !formatCommunicationTarget(item.target).recognized || Boolean(queueingId)}
          loading={queueingId === item.id}
          onClick={() => void queue(item)}
        >进入外发队列</Button>
      ),
    },
  ];

  const renderCard = (item: ReviewPackage, className: string) => (
    <article className={className}>
      <div className="review-card-heading">
        <div><span className="review-card-id">审核包 · v{item.version}</span><h3>{item.title}</h3></div>
        {reviewStatus(item.status)}
      </div>
      <dl>
        <div><dt>事项</dt><dd>{item.matterId}</dd></div>
        <div><dt>提交时间</dt><dd>{submittedAt(item.submittedAt)}</dd></div>
        <div><dt>目标</dt><dd>{formatCommunicationTarget(item.target).display}</dd></div>
      </dl>
      <div className="review-card-actions">
        <Button type="link" aria-label={`查看审核包：${item.title}`} onClick={() => onReviewSelected(item.id)}>查看审核包</Button>
        <Button
          type="link"
          icon={<SendOutlined />}
          aria-label={`将${item.title}进入外发队列`}
          title={!formatCommunicationTarget(item.target).recognized ? '无法识别真实外发目标，不能进入外发队列' : item.status === 'approved' ? '进入外发队列，不等于已发送' : '仅已批准审核包可进入外发队列'}
          disabled={item.status !== 'approved' || !formatCommunicationTarget(item.target).recognized || Boolean(queueingId)}
          loading={queueingId === item.id}
          onClick={() => void queue(item)}
        >进入外发队列</Button>
      </div>
    </article>
  );

  return (
    <div className="page review-center-page">
      <PageHeader
        eyebrow="人工审核门禁"
        title="审核中心"
        description="核对证据、风险和最终正文；只有已批准版本可以进入外发队列。"
        primaryAction={<Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新审核队列</Button>}
      />
      <DataBoundaryBanner
        variant="api"
        title="由服务接口提供"
        description="审核结果和外发入队均以接口响应为准；进入队列不等于已发送。"
      />
      {queueNotice && <Alert className="review-queue-notice" type="info" showIcon message={queueNotice} closable />}
      {queueError && <Alert className="review-queue-notice" type="error" showIcon message={queueError} closable />}
      {loading ? (
        <StatePanel variant="loading" title="正在加载审核队列" description="等待服务接口返回审核包。" />
      ) : failure ? (
        <StatePanel {...failure} action={<Button onClick={() => void load()}>重试</Button>} />
      ) : packages.length === 0 ? (
        <StatePanel variant="empty" title="暂无审核包" description="当前没有等待法务处理的审核包。" />
      ) : (
        <Card className="review-queue-surface" variant="borderless">
          <ResponsiveCollection
            className="review-queue-collection"
            items={packages}
            getKey={(item) => item.id}
            renderDesktop={(items) => <Table className="review-queue-table" rowKey="id" columns={columns} dataSource={[...items]} pagination={false} scroll={{ x: 1195 }} tableLayout="fixed" />}
            renderCompact={(item) => renderCard(item, 'review-compact-card')}
            renderMobile={(item) => renderCard(item, 'review-mobile-card')}
          />
        </Card>
      )}

      <Drawer
        className="review-detail-drawer"
        width={920}
        open={Boolean(reviewPackageId)}
        onClose={requestReviewClose}
        title="审核包详情"
        extra={<Space>{active && <Button onClick={requestMatterNavigation}>返回事项</Button>}<Button onClick={requestReviewClose}>返回审核队列</Button></Space>}
        footer={active?.status === 'pending_review' ? (
          <div className="review-detail-footer">
            <Text type="secondary">提交后形成不可变审核记录；批准正文必须与后续入队版本一致。</Text>
            <Button type="primary" loading={submitting} disabled={!canSubmit || submitting} onClick={() => void submitReview()}>提交审核决定</Button>
          </div>
        ) : null}
      >
        {detailLoading ? (
          <StatePanel variant="loading" title="正在加载审核包详情" />
        ) : detailFailure ? (
          <StatePanel {...detailFailure} action={<Button onClick={onReviewClosed}>返回审核队列</Button>} />
        ) : active ? (
          <div className="review-package-layout">
            <div className="review-detail-summary">
              {reviewStatus(active.status)}
              <Title level={3}>{active.title}</Title>
              <Text type="secondary">事项 {active.matterId} · 审核包版本 v{active.version} · 提交 {submittedAt(active.submittedAt)}</Text>
            </div>
            <section className="review-target-panel" role="region" aria-label="外发目标">
              <Title level={4}>外发目标</Title>
              <Text strong>{formatCommunicationTarget(active.target).display}</Text>
              {!formatCommunicationTarget(active.target).recognized && <Alert type="error" showIcon message="无法核验真实外发目标，不能批准" />}
            </section>
            <ReviewSection title="背景"><Paragraph>{active.background}</Paragraph></ReviewSection>
            <ReviewSection title="已确认事实"><StructuredList values={active.confirmedFacts} /></ReviewSection>
            <ReviewSection title="未确认事实"><StructuredList values={active.unconfirmedFacts} /></ReviewSection>
            <ReviewSection title="处理理由"><Paragraph>{active.reasoning}</Paragraph></ReviewSection>
            <ReviewSection title="风险"><StructuredList values={active.risks} /></ReviewSection>
            <ReviewSection title="替代方案"><StructuredList values={active.alternatives} /></ReviewSection>
            <ReviewSection title="引用依据"><StructuredList values={active.citations} /></ReviewSection>
            <ReviewSection title="拟发送内容"><Paragraph className="review-proposed-content">{active.proposedContent}</Paragraph></ReviewSection>

            <section className="review-decision-panel">
              <Title level={4}>审核决定与最终正文</Title>
              {latestRecord ? (
                <>
                  <Space wrap><Tag color="green">{technicalStatusLabel(reviewDecisionLabels, latestRecord.decision)}</Tag><Text type="secondary">审核人 {latestRecord.reviewerId} · {new Date(latestRecord.reviewedAt).toLocaleString()}</Text></Space>
                  <Paragraph className="review-final-content">{latestRecord.finalContent ?? '该决定未形成可外发正文。'}</Paragraph>
                  {latestRecord.comments && <Text type="secondary">审核意见：{latestRecord.comments}</Text>}
                </>
              ) : (
                <div className="review-decision-form">
                  <label><Text strong>审核决定</Text><Select
                    aria-label="审核决定"
                    value={draft.decision}
                    onChange={(value: ReviewDecision) => { setDraftDirty(true); setDraft((current) => ({ ...current, decision: value })); }}
                    options={Object.entries(reviewDecisionLabels).map(([value, label]) => ({ value, label }))}
                  /></label>
                  <label><Text strong>最终正文</Text><Input.TextArea aria-label="最终正文" rows={7} value={draft.finalContent} onChange={(event) => { setDraftDirty(true); setDraft((current) => ({ ...current, finalContent: event.target.value })); }} /></label>
                  <label><Text strong>审核意见和修改原因</Text><Input.TextArea aria-label="审核意见和修改原因" rows={3} value={draft.comments} onChange={(event) => { setDraftDirty(true); setDraft((current) => ({ ...current, comments: event.target.value })); }} /></label>
                  <Checkbox checked={draft.reusableAsExample} onChange={(event) => { setDraftDirty(true); setDraft((current) => ({ ...current, reusableAsExample: event.target.checked })); }}>允许作为未来审核样例</Checkbox>
                  {validationMessage && <Alert type="warning" showIcon message={validationMessage} />}
                </div>
              )}
              {submitFailure && (
                <StatePanel
                  {...submitFailure}
                  className="review-submit-error"
                  action={<Button onClick={() => setSubmitFailure(undefined)}>继续核对</Button>}
                />
              )}
            </section>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}

function ReviewSection({ title, children }: { title: string; children: ReactNode }) {
  return <section className="review-read-section" data-review-section><Title level={4}>{title}</Title>{children}</section>;
}

function StructuredList({ values }: { values: Array<Record<string, unknown>> }) {
  if (values.length === 0) return <Text type="secondary">无</Text>;
  return <List size="small" dataSource={values} renderItem={(value) => <List.Item>{Object.entries(value).map(([key, content]) => `${key}: ${displayValue(content)}`).join('；')}</List.Item>} />;
}
