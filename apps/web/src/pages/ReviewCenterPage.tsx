import {
  Alert,
  Button,
  Card,
  Checkbox,
  Empty,
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
import { ReloadOutlined, SendOutlined } from '@ant-design/icons';
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { legalApi } from '../services/api';
import { displayValue } from '../services/apiLabels';
import type { ReviewDecision, ReviewPackage } from '../types/api';

const { Title, Text, Paragraph } = Typography;

interface ReviewDraft {
  decision: ReviewDecision;
  comments: string;
  finalContent: string;
  reusableAsExample: boolean;
}

export default function ReviewCenterPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedPackageId = searchParams.get('packageId');
  const [packages, setPackages] = useState<ReviewPackage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [active, setActive] = useState<ReviewPackage>();
  const [submitting, setSubmitting] = useState(false);
  const [draft, setDraft] = useState<ReviewDraft>({
    decision: 'approved',
    comments: '',
    finalContent: '',
    reusableAsExample: false,
  });

  const open = useCallback((value: ReviewPackage) => {
    setActive(value);
    setDraft({
      decision: 'approved',
      comments: '',
      finalContent: value.proposedContent,
      reusableAsExample: false,
    });
  }, []);

  const close = () => {
    setActive(undefined);
    if (requestedPackageId) setSearchParams({}, { replace: true });
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const values = await legalApi.listReviewPackages();
      setPackages(values);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '加载审核包失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!requestedPackageId) return;
    const requested = packages.find((value) => value.id === requestedPackageId);
    if (requested) open(requested);
  }, [open, packages, requestedPackageId]);

  const submitReview = async () => {
    if (!active) return;
    setSubmitting(true);
    try {
      await legalApi.reviewPackage(active.id, {
        packageVersion: active.version,
        decision: draft.decision,
        comments: draft.comments || undefined,
        finalContent: ['approved', 'approved_with_edits'].includes(draft.decision)
          ? draft.finalContent
          : undefined,
        reusableAsExample: draft.reusableAsExample,
      });
      message.success('审核结果已保存');
      close();
      await load();
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : '审核失败');
    } finally {
      setSubmitting(false);
    }
  };

  const queue = async (value: ReviewPackage) => {
    try {
      const result = await legalApi.queueCommunication(value.id);
      message.success(`外发已进入队列：${result.status}`);
      await load();
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : '发送门禁未通过');
    }
  };

  return (
    <div className="page">
      <div className="page-title-row">
        <div>
          <span className="eyebrow">REVIEW GATE</span>
          <Title level={2}>审核中心</Title>
          <Text type="secondary">所有外发内容必须经过法务审核，批准版本才能进入发送队列。</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
      </div>
      {error && <Alert type="error" showIcon message={error} />}
      <Spin spinning={loading}>
        {!loading && packages.length === 0 ? <Empty description="暂无审核包" /> : (
          <List
            grid={{ gutter: 16, column: 2 }}
            dataSource={packages}
            renderItem={(item) => (
              <List.Item>
                <Card bordered={false} actions={[
                  <Button key="review" type="link" onClick={() => {
                    setSearchParams({ packageId: item.id }, { replace: true });
                    open(item);
                  }}>审核</Button>,
                  <Button key="send" type="link" icon={<SendOutlined />} disabled={item.status !== 'approved'} onClick={() => void queue(item)}>进入外发队列</Button>,
                ]}>
                  <Space wrap><Tag color={item.status === 'approved' ? 'green' : item.status === 'pending_review' ? 'blue' : 'default'}>{item.status}</Tag><Tag>{item.packageType}</Tag></Space>
                  <Title level={4}>{item.title}</Title>
                  <Paragraph ellipsis={{ rows: 3 }}>{item.background}</Paragraph>
                  <Text type="secondary">Matter {item.matterId} · 版本 {item.version}</Text>
                </Card>
              </List.Item>
            )}
          />
        )}
      </Spin>

      <Modal
        open={Boolean(active)}
        width={900}
        title={active?.title}
        okText="提交审核"
        cancelText="取消"
        confirmLoading={submitting}
        onCancel={close}
        onOk={() => void submitReview()}
      >
        {active && (
          <div className="review-package-layout">
            <Alert type="info" showIcon message="审核包同时展示背景、事实、依据、理由、风险和拟发送内容。" />
            <ReviewSection title="背景"><Paragraph>{active.background}</Paragraph></ReviewSection>
            <ReviewSection title="已确认事实"><StructuredList values={active.confirmedFacts} /></ReviewSection>
            <ReviewSection title="未确认事实"><StructuredList values={active.unconfirmedFacts} /></ReviewSection>
            <ReviewSection title="处理理由"><Paragraph>{active.reasoning}</Paragraph></ReviewSection>
            <ReviewSection title="风险"><StructuredList values={active.risks} /></ReviewSection>
            <ReviewSection title="替代方案"><StructuredList values={active.alternatives} /></ReviewSection>
            <ReviewSection title="引用依据"><StructuredList values={active.citations} /></ReviewSection>
            <ReviewSection title="拟发送内容">
              <Input.TextArea rows={8} value={draft.finalContent} onChange={(event) => setDraft((current) => ({ ...current, finalContent: event.target.value }))} />
            </ReviewSection>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Text strong>审核决定</Text>
              <Select
                value={draft.decision}
                style={{ width: 240 }}
                onChange={(value: ReviewDecision) => setDraft((current) => ({ ...current, decision: value }))}
                options={[
                  { value: 'approved', label: '原样通过' },
                  { value: 'approved_with_edits', label: '修改后通过' },
                  { value: 'needs_information', label: '要求补充信息' },
                  { value: 'rejected', label: '驳回' },
                ]}
              />
              <Input.TextArea rows={3} placeholder="审核意见和修改原因" value={draft.comments} onChange={(event) => setDraft((current) => ({ ...current, comments: event.target.value }))} />
              <Checkbox checked={draft.reusableAsExample} onChange={(event) => setDraft((current) => ({ ...current, reusableAsExample: event.target.checked }))}>允许作为未来审核样例</Checkbox>
            </Space>
          </div>
        )}
      </Modal>
    </div>
  );
}

function ReviewSection({ title, children }: { title: string; children: ReactNode }) {
  return <section style={{ marginTop: 18 }}><Title level={5}>{title}</Title>{children}</section>;
}

function StructuredList({ values }: { values: Array<Record<string, unknown>> }) {
  if (values.length === 0) return <Text type="secondary">无</Text>;
  return <List size="small" dataSource={values} renderItem={(value) => <List.Item>{Object.entries(value).map(([key, content]) => `${key}: ${displayValue(content)}`).join('；')}</List.Item>} />;
}
