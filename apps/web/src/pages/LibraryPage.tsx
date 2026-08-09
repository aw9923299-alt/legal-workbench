import {
  Alert,
  Button,
  Card,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  List,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import DataBoundaryBanner from '../components/DataBoundaryBanner';
import PageHeader from '../components/PageHeader';
import { createMutationContext, legalApi } from '../services/api';
import type {
  AuthorityRole,
  AuthorityStatus,
  AuthorityType,
  KnowledgeDocument,
} from '../types/api';

const { Paragraph, Text, Title } = Typography;

const authorityTypeLabels: Record<AuthorityType, string> = {
  unknown: '待人工分类',
  law: '法律',
  administrative_regulation: '行政法规',
  judicial_interpretation: '司法解释',
  department_rule: '部门规章',
  local_regulation: '地方性法规',
  local_government_rule: '地方政府规章',
  normative_document: '规范性文件',
  guiding_case: '指导性案例',
  court_case: '法院案例',
  regulatory_guidance: '监管指引',
  contract: '合同',
  company_policy: '公司制度',
  business_rule: '业务规则',
  legal_opinion: '法律意见',
  internal_precedent: '内部先例',
};

const authorityRoleByType: Record<AuthorityType, AuthorityRole | null> = {
  unknown: null,
  law: 'formal_legal_basis',
  administrative_regulation: 'formal_legal_basis',
  judicial_interpretation: 'formal_legal_basis',
  department_rule: 'formal_legal_basis',
  local_regulation: 'formal_legal_basis',
  local_government_rule: 'formal_legal_basis',
  normative_document: 'formal_legal_basis',
  guiding_case: 'persuasive_authority',
  court_case: 'persuasive_authority',
  regulatory_guidance: 'persuasive_authority',
  contract: 'contractual_basis',
  company_policy: 'internal_basis',
  business_rule: 'internal_basis',
  legal_opinion: 'strategy_reference',
  internal_precedent: 'strategy_reference',
};

const roleLabels: Record<AuthorityRole, string> = {
  formal_legal_basis: '正式法律依据',
  persuasive_authority: '说服性依据',
  contractual_basis: '合同依据',
  internal_basis: '内部依据',
  strategy_reference: '策略参考',
};

interface MetadataFormValues {
  title: string;
  authorityType: AuthorityType;
  authorityRole: AuthorityRole | null;
  authorityStatus: AuthorityStatus;
  jurisdiction: string;
  effectiveFrom: string;
  effectiveTo: string;
  issuer: string;
  documentNumber: string;
  enabled: boolean;
}

export default function LibraryPage() {
  const [activeId, setActiveId] = useState<string>();
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<MetadataFormValues>();
  const documents = useQuery({
    queryKey: ['knowledge-documents'],
    queryFn: () => legalApi.listKnowledgeDocuments(),
  });
  const details = useQuery({
    queryKey: ['knowledge-document', activeId],
    queryFn: () => legalApi.getKnowledgeDocument(activeId ?? ''),
    enabled: Boolean(activeId),
  });

  useEffect(() => {
    const value = details.data?.document;
    if (!value) return;
    form.setFieldsValue({
      title: value.title,
      authorityType: value.authorityType,
      authorityRole: value.authorityRole,
      authorityStatus: value.authorityStatus,
      jurisdiction: value.jurisdiction,
      effectiveFrom: value.effectiveFrom ?? '',
      effectiveTo: value.effectiveTo ?? '',
      issuer: value.issuer ?? '',
      documentNumber: value.documentNumber ?? '',
      enabled: value.enabled,
    });
  }, [details.data, form]);

  const pendingCount = useMemo(
    () => documents.data?.filter((value) => value.metadataStatus === 'pending_metadata').length ?? 0,
    [documents.data],
  );

  const save = async (values: MetadataFormValues) => {
    const current = details.data?.document;
    if (!current) return;
    setSaving(true);
    try {
      await legalApi.updateKnowledgeMetadata(current.id, current.version, {
        title: values.title,
        authorityType: values.authorityType,
        authorityRole: authorityRoleByType[values.authorityType],
        authorityStatus: values.authorityType === 'unknown' ? 'unknown' : values.authorityStatus,
        jurisdiction: values.jurisdiction,
        effectiveFrom: values.effectiveFrom || null,
        effectiveTo: values.effectiveTo || null,
        issuer: values.issuer || null,
        documentNumber: values.documentNumber || null,
        enabled: values.enabled,
      }, createMutationContext());
      message.success('知识资料元数据已保存');
      await Promise.all([documents.refetch(), details.refetch()]);
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : '保存知识资料失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page library-page knowledge-library-page">
      <PageHeader
        eyebrow="POSTGRESQL KNOWLEDGE"
        title="法务知识库"
        description="本地资料已通过只读增量管道进入 Document、Segment 和 Knowledge 索引；Agent 仅能读取检索预算内的相关 Chunk。"
        metadata={<Space wrap><Tag color="blue">{documents.data?.length ?? 0} 份资料</Tag><Tag color={pendingCount ? 'orange' : 'green'}>{pendingCount} 份待分类</Tag></Space>}
        primaryAction={<Button icon={<ReloadOutlined />} onClick={() => void documents.refetch()}>刷新资料</Button>}
      />
      <DataBoundaryBanner
        variant="api"
        title="数据库真实数据"
        description="资料正文保存在 PostgreSQL；这里不展示原始绝对路径，也不会把整个资料库发送给 Codex。类型和效力状态由确定性规则约束，可人工修正。"
      />
      {documents.error && <Alert type="error" showIcon message={documents.error.message} />}
      <Card className="knowledge-directory" variant="borderless">
        <Spin spinning={documents.isLoading}>
          {!documents.isLoading && !documents.data?.length ? <Empty description="尚未导入法务资料" /> : (
            <Table<KnowledgeDocument>
              rowKey="id"
              pagination={{ pageSize: 20, showSizeChanger: false }}
              dataSource={documents.data ?? []}
              onRow={(record) => ({ onClick: () => setActiveId(record.id) })}
              columns={[
                {
                  title: '资料', dataIndex: 'title', key: 'title',
                  render: (title: string, record) => <div className="knowledge-title-cell"><Text strong>{title}</Text><Text type="secondary">{record.issuer || record.sourceType}</Text></div>,
                },
                {
                  title: '来源类型', dataIndex: 'authorityType', key: 'authorityType', width: 160,
                  responsive: ['md'],
                  render: (value: AuthorityType) => <Tag color={value === 'unknown' ? 'orange' : 'blue'}>{authorityTypeLabels[value]}</Tag>,
                },
                {
                  title: '依据角色', dataIndex: 'authorityRole', key: 'authorityRole', width: 150,
                  responsive: ['lg'],
                  render: (value: AuthorityRole | null) => value ? roleLabels[value] : '待确认',
                },
                { title: '法域', dataIndex: 'jurisdiction', key: 'jurisdiction', width: 90, responsive: ['md'] },
                {
                  title: '状态', key: 'state', width: 130,
                  render: (_, record) => <Space size={4} wrap><Tag color={record.enabled ? 'green' : 'default'}>{record.enabled ? '启用' : '停用'}</Tag>{record.metadataStatus === 'pending_metadata' && <Tag color="orange">待分类</Tag>}</Space>,
                },
                { title: '版本', dataIndex: 'version', key: 'version', width: 70, responsive: ['sm'] },
              ]}
            />
          )}
        </Spin>
      </Card>

      <Drawer
        open={Boolean(activeId)}
        width={760}
        className="knowledge-detail-drawer"
        title={details.data?.document.title ?? '知识资料'}
        onClose={() => setActiveId(undefined)}
      >
        <Spin spinning={details.isLoading}>
          {details.error && <Alert type="error" showIcon message={details.error.message} />}
          {details.data && <Tabs items={[
            {
              key: 'metadata', label: '分类与效力',
              children: <Form form={form} layout="vertical" onFinish={(values) => void save(values)}>
                <Form.Item name="title" label="资料标题" rules={[{ required: true }]}><Input /></Form.Item>
                <div className="knowledge-form-grid">
                  <Form.Item name="authorityType" label="资料类型" rules={[{ required: true }]}>
                    <Select
                      options={(Object.keys(authorityTypeLabels) as AuthorityType[]).map((value) => ({ value, label: authorityTypeLabels[value] }))}
                      onChange={(value: AuthorityType) => {
                        form.setFieldValue('authorityRole', authorityRoleByType[value]);
                        if (value === 'unknown') form.setFieldValue('authorityStatus', 'unknown');
                      }}
                    />
                  </Form.Item>
                  <Form.Item name="authorityRole" label="依据角色（确定性映射）">
                    <Select disabled allowClear options={(Object.keys(roleLabels) as AuthorityRole[]).map((value) => ({ value, label: roleLabels[value] }))} />
                  </Form.Item>
                  <Form.Item name="authorityStatus" label="效力状态" rules={[{ required: true }]}>
                    <Select options={[
                      { value: 'effective', label: '现行有效' },
                      { value: 'superseded', label: '已被替代' },
                      { value: 'repealed', label: '已废止' },
                      { value: 'unknown', label: '未知' },
                    ]} />
                  </Form.Item>
                  <Form.Item name="jurisdiction" label="法域" rules={[{ required: true }]}><Input placeholder="CN" /></Form.Item>
                  <Form.Item name="effectiveFrom" label="生效日期"><Input type="date" /></Form.Item>
                  <Form.Item name="effectiveTo" label="失效日期"><Input type="date" /></Form.Item>
                  <Form.Item name="issuer" label="发布/签署主体"><Input /></Form.Item>
                  <Form.Item name="documentNumber" label="文号"><Input /></Form.Item>
                </div>
                <Form.Item name="enabled" label="允许检索" valuePropName="checked"><Switch checkedChildren="启用" unCheckedChildren="停用" /></Form.Item>
                <Button type="primary" htmlType="submit" loading={saving}>保存元数据</Button>
              </Form>,
            },
            {
              key: 'chunks', label: `Chunk（${details.data.chunks.length}）`,
              children: details.data.chunks.length ? <List
                dataSource={details.data.chunks}
                renderItem={(chunk) => <List.Item><Card size="small" className="knowledge-chunk-card"><Space wrap><Tag>#{chunk.sequence}</Tag><Tag>{chunk.locator}</Tag><Tag>{chunk.estimatedTokenCount} tokens{chunk.tokenCountEstimated ? ' estimated' : ''}</Tag></Space><Paragraph>{chunk.text}</Paragraph><Text code>{chunk.textHash.slice(0, 16)}…</Text></Card></List.Item>}
              /> : <Empty description="没有可检索 Chunk" />,
            },
            {
              key: 'hits', label: `检索命中（${details.data.retrievalLogs.length}）`,
              children: details.data.retrievalLogs.length ? <List
                dataSource={details.data.retrievalLogs}
                renderItem={(log) => <List.Item><Card size="small" className="knowledge-hit-card"><Descriptions size="small" column={2} items={[
                  { key: 'query', label: 'Query hash', children: <Text code>{log.queryHash.slice(0, 16)}…</Text> },
                  { key: 'run', label: 'Agent Run', children: log.agentRunId ?? '无' },
                  { key: 'candidate', label: '候选/选中', children: `${log.candidateCount} / ${log.selectedChunkCount}` },
                  { key: 'tokens', label: '选中 Token', children: log.selectedTokenCount },
                  { key: 'budget', label: '预算排除', children: log.excludedByTokenBudgetCount },
                  { key: 'time', label: '命中时间', children: new Date(log.createdAt).toLocaleString() },
                ]} /></Card></List.Item>}
              /> : <Empty description="尚无检索命中" />,
            },
          ]} />}
        </Spin>
      </Drawer>
    </div>
  );
}
