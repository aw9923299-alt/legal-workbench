import {
  CloudOutlined,
  FolderOpenOutlined,
  LinkOutlined,
  PauseCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  StopOutlined,
  SyncOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Divider,
  Form,
  Input,
  InputNumber,
  List,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { useMemo, useState } from 'react';
import { QueryState } from '../components/QueryState';
import { ApiError, createMutationContext, legalApi } from '../services/api';
import type {
  FeishuCapabilityName,
  FeishuCapabilityStatus,
  FeishuDocumentSearchResult,
  FeishuIdentityType,
  FeishuScope,
  FeishuScopeSyncMode,
  FeishuScopeType,
} from '../types/api';

const { Title, Text } = Typography;

const statusLabel = {
  unapproved: '未批准',
  allowed: '已允许',
  excluded: '已排除',
  paused: '已暂停',
};
const statusColor = {
  unapproved: 'default',
  allowed: 'green',
  excluded: 'red',
  paused: 'orange',
};
const syncModeLabel: Record<FeishuScopeSyncMode, string> = {
  mentions_only: '仅 @机器人',
  all_messages: '采集范围内消息',
  disabled: '不同步',
};
const authorizationStatusLabel = {
  connected: '已连接',
  refreshing: '刷新中',
  reauth_required: '需要重新授权',
  expired: '授权已过期',
  permission_missing: '权限不足',
  revoked: '已撤销',
  degraded: '连接异常',
};
const capabilityStatusLabel: Record<FeishuCapabilityStatus, string> = {
  ready: '已就绪',
  partial: '部分可用',
  permission_missing: '权限不足',
  unsupported: '不支持',
};
const capabilityStatusColor: Record<FeishuCapabilityStatus, string> = {
  ready: 'green',
  partial: 'gold',
  permission_missing: 'red',
  unsupported: 'default',
};

function readableError(error: unknown): string {
  if (error instanceof ApiError) {
    return [error.message, error.code, error.correlationId].filter(Boolean).join(' · ');
  }
  return error instanceof Error ? error.message : '请求失败';
}

function documentIdentity(value: FeishuDocumentSearchResult) {
  return {
    token: value.token ?? value.objToken ?? value.docToken ?? '',
    type: (value.type ?? value.docType ?? 'docx').toLowerCase(),
    title: value.title ?? value.name ?? '未命名文档',
    url: value.url ?? '',
  };
}

export default function FeishuScopesPage() {
  const queryClient = useQueryClient();
  const [scopeForm] = Form.useForm();
  const [documentForm] = Form.useForm();
  const [folderForm] = Form.useForm();
  const [authorizationUrl, setAuthorizationUrl] = useState<string>();
  const [documentResults, setDocumentResults] = useState<FeishuDocumentSearchResult[]>([]);

  const authorizations = useQuery({
    queryKey: ['settings', 'feishu-user-authorizations'],
    queryFn: () => legalApi.listFeishuUserAuthorizations(),
  });
  const scopes = useQuery({
    queryKey: ['settings', 'feishu-scopes'],
    queryFn: () => legalApi.listFeishuScopes(),
  });
  const activeAuthorization = authorizations.data?.find((item) => item.usable);
  const capabilityReady = (name: FeishuCapabilityName) => {
    const status = activeAuthorization?.capabilities.find((item) => item.capability === name)?.status;
    return status === 'ready';
  };
  const messageHistoryReady = capabilityReady('message_history');
  const chatDiscoveryReady = capabilityReady('chat_discovery');
  const documentReadReady = capabilityReady('document_read');
  const driveSearchReady = capabilityReady('drive_search');
  const subscriptions = useQuery({
    queryKey: ['settings', 'feishu-folder-subscriptions', activeAuthorization?.id],
    queryFn: () => legalApi.listFeishuFolderSubscriptions(activeAuthorization?.id),
    enabled: Boolean(activeAuthorization),
  });

  const refreshAll = () => {
    void Promise.all([authorizations.refetch(), scopes.refetch(), subscriptions.refetch()]);
  };
  const invalidateScopes = () => queryClient.invalidateQueries({
    queryKey: ['settings', 'feishu-scopes'],
  });

  const authorize = useMutation({
    mutationFn: () => legalApi.startFeishuUserAuthorization(
      `${window.location.origin}/api/v1/integrations/feishu-user/callback`,
      createMutationContext(),
    ),
    onSuccess: (result) => setAuthorizationUrl(result.authorizationUrl),
  });
  const revoke = useMutation({
    mutationFn: (authorizationId: string) => legalApi.revokeFeishuUserAuthorization(
      authorizationId,
      createMutationContext(),
    ),
    onSuccess: () => {
      message.success('个人授权已撤销，本地 Token Secret 已删除。');
      void queryClient.invalidateQueries({ queryKey: ['settings', 'feishu-user-authorizations'] });
    },
  });
  const discover = useMutation({
    mutationFn: (authorizationId: string) => legalApi.discoverFeishuUserScopes(
      authorizationId,
      createMutationContext(),
    ),
    onSuccess: (items) => {
      message.success(`发现 ${items.length} 个群聊，均以未批准状态保存。`);
      void invalidateScopes();
    },
  });
  const register = useMutation({
    mutationFn: (values: {
      chatId: string;
      displayName?: string;
      identityType: FeishuIdentityType;
      scopeType: FeishuScopeType;
      backfillDays: number;
    }) => legalApi.registerFeishuScope({
      ...values,
      authorizationId: values.identityType === 'user' ? activeAuthorization?.id : undefined,
    }, createMutationContext()),
    onSuccess: () => {
      scopeForm.resetFields();
      message.success('数据范围已登记为未批准，等待人工 Allow / Exclude。');
      void invalidateScopes();
    },
  });
  const changeScope = useMutation({
    mutationFn: (value: {
      scope: FeishuScope;
      action: 'allow' | 'exclude' | 'pause' | 'resume';
      syncMode?: FeishuScopeSyncMode;
    }) => legalApi.changeFeishuScope(
      value.scope.id,
      value.scope.version,
      { action: value.action, syncMode: value.syncMode },
      createMutationContext(),
    ),
    onSuccess: () => void invalidateScopes(),
  });
  const synchronize = useMutation({
    mutationFn: (scope: FeishuScope) => legalApi.syncFeishuUserScope(
      scope.id,
      createMutationContext(),
    ),
    onSuccess: (result) => {
      message.success(`同步完成：统一 Ingestion 接收 ${result.ingestedCount} 条消息。`);
      void invalidateScopes();
    },
  });
  const documentSearch = useMutation({
    mutationFn: (values: { query: string }) => {
      if (!activeAuthorization) throw new Error('请先授权个人飞书账号。');
      return legalApi.searchFeishuUserDocuments(activeAuthorization.id, values.query);
    },
    onSuccess: setDocumentResults,
  });
  const documentImport = useMutation({
    mutationFn: (value: FeishuDocumentSearchResult) => {
      if (!activeAuthorization) throw new Error('请先授权个人飞书账号。');
      const document = documentIdentity(value);
      if (document.type !== 'docx' || !document.token || !document.url) {
        throw new Error('首期仅导入官方 API 可返回 Markdown 的 docx 文档。');
      }
      return legalApi.importFeishuUserDocument(document.token, {
        authorizationId: activeAuthorization.id,
        documentType: 'docx',
        title: document.title,
        sourceUrl: document.url,
      }, createMutationContext());
    },
    onSuccess: (result) => message.success(
      result.createdVersion
        ? `已创建文档版本并写入 ${result.segmentCount} 个 Segment。`
        : '文档内容未变化，未创建重复版本。',
    ),
  });
  const subscribeFolder = useMutation({
    mutationFn: (values: { folderToken: string; recursive?: boolean }) => {
      if (!activeAuthorization) throw new Error('请先授权个人飞书账号。');
      return legalApi.subscribeFeishuFolder(values.folderToken, {
        authorizationId: activeAuthorization.id,
        recursive: Boolean(values.recursive),
      }, createMutationContext());
    },
    onSuccess: () => {
      folderForm.resetFields();
      message.success('文件夹订阅已写入 PostgreSQL；不会镜像全部云空间。');
      void subscriptions.refetch();
    },
  });

  const operationError = useMemo(() => [
    authorize.error,
    revoke.error,
    discover.error,
    register.error,
    changeScope.error,
    synchronize.error,
    documentSearch.error,
    documentImport.error,
    subscribeFolder.error,
  ].find(Boolean), [
    authorize.error,
    changeScope.error,
    discover.error,
    documentImport.error,
    documentSearch.error,
    register.error,
    revoke.error,
    subscribeFolder.error,
    synchronize.error,
  ]);

  const scopeActions = (item: FeishuScope) => <Space wrap>
    {(item.status === 'unapproved' || item.status === 'excluded') && <Button size="small" icon={<SafetyCertificateOutlined />} onClick={() => changeScope.mutate({ scope: item, action: 'allow', syncMode: item.identityType === 'user' ? 'all_messages' : 'mentions_only' })}>允许采集</Button>}
    {item.status === 'allowed' && <Button size="small" icon={<PauseCircleOutlined />} onClick={() => changeScope.mutate({ scope: item, action: 'pause' })}>暂停</Button>}
    {item.status === 'paused' && <Button size="small" onClick={() => changeScope.mutate({ scope: item, action: 'resume', syncMode: item.identityType === 'user' ? 'all_messages' : 'mentions_only' })}>恢复</Button>}
    {item.status !== 'excluded' && <Button danger size="small" onClick={() => changeScope.mutate({ scope: item, action: 'exclude' })}>排除</Button>}
    {item.identityType === 'user' && item.status === 'allowed' && <Button size="small" icon={<SyncOutlined />} disabled={!messageHistoryReady} loading={synchronize.isPending} onClick={() => synchronize.mutate(item)}>立即同步</Button>}
  </Space>;

  return <div className="page feishu-personal-page">
    <div className="page-title-row">
      <div>
        <span className="eyebrow">FEISHU PERSONAL DATA SOURCES</span>
        <Title level={2}>飞书个人数据源</Title>
        <Text type="secondary">个人消息与云文档只读同步；采集、Codex 分析和正式外发保持三道独立门禁。</Text>
      </div>
      <Button icon={<ReloadOutlined />} onClick={refreshAll}>刷新</Button>
    </div>

    <Alert
      className="data-boundary-banner data-boundary-banner--pending"
      type="warning"
      showIcon
      message="本机真实飞书能力尚未验收"
      description="无真实 OAuth 凭证的能力保持 not_executed。页面只展示 PostgreSQL 中的同步事实，不把接口入口或模拟数据写成已通过。"
    />
    {operationError && <Alert
      type="error"
      showIcon
      closable
      message="飞书个人数据源操作失败"
      description={readableError(operationError)}
      style={{ marginBottom: 14 }}
    />}
    {authorizationUrl && <Alert
      type="info"
      showIcon
      closable
      onClose={() => setAuthorizationUrl(undefined)}
      message="授权请求已创建"
      description="在飞书官方页面确认授权后，回调会把 Token 仅写入 LocalSecretProvider。"
      action={<Button type="primary" href={authorizationUrl}>前往飞书授权</Button>}
      style={{ marginBottom: 14 }}
    />}

    <section className="feishu-account-section">
      <div className="section-heading">
        <div><Title level={4}>个人账号授权</Title><Text type="secondary">保留 App/Bot 接入，同时增加只读 User OAuth 身份。</Text></div>
        {!activeAuthorization && <Button
          type="primary"
          icon={<UserOutlined />}
          loading={authorize.isPending}
          onClick={() => authorize.mutate()}
        >授权个人飞书账号</Button>}
      </div>
      <QueryState loading={authorizations.isLoading} error={authorizations.error} onRetry={() => void authorizations.refetch()}>
        <div className="feishu-account-grid">
          {(authorizations.data ?? []).map((item) => <Card key={item.id} className="feishu-account-card" variant="borderless">
            <div className="feishu-account-card__main">
              <div className="feishu-source-icon"><UserOutlined /></div>
              <div>
                <Space wrap><Text strong>{item.displayName ?? item.openId}</Text><Tag color={item.usable ? 'green' : 'orange'}>{authorizationStatusLabel[item.status]}</Tag></Space>
                <Text type="secondary">{item.tenantKey} · Token 版本只以 Secret Reference 保存</Text>
                <Text type="secondary">访问到期：{new Date(item.accessExpiresAt).toLocaleString()}</Text>
                {item.missingScopes.length > 0 && <Space wrap size={[4, 4]}>
                  <Text type="danger">缺少权限：</Text>
                  {item.missingScopes.map((scope) => <Tag color="red" key={scope}>{scope}</Tag>)}
                </Space>}
                <div className="feishu-capability-grid">
                  {item.capabilities.map((projection) => <div className="feishu-capability" key={projection.capability}>
                    <Space size={6}><Text>{projection.label}</Text><Tag color={capabilityStatusColor[projection.status]}>{capabilityStatusLabel[projection.status]}</Tag></Space>
                    {projection.missingScopes.length > 0 && <Space wrap size={[4, 4]}>
                      {projection.missingScopes.map((scope) => <Tag key={scope}>{scope}</Tag>)}
                    </Space>}
                  </div>)}
                </div>
              </div>
            </div>
            <Space wrap>
              {item.usable && <Button icon={<SearchOutlined />} disabled={!chatDiscoveryReady} loading={discover.isPending} onClick={() => discover.mutate(item.id)}>发现群聊</Button>}
              <Button danger icon={<StopOutlined />} loading={revoke.isPending} onClick={() => revoke.mutate(item.id)}>撤销授权</Button>
            </Space>
          </Card>)}
          {!authorizations.isLoading && !authorizations.data?.length && <Card className="feishu-empty-card" variant="borderless"><Text type="secondary">尚未授权个人账号。现有 App/Bot 接入不受影响。</Text></Card>}
        </div>
      </QueryState>
    </section>

    <div className="feishu-source-stats">
      <Row gutter={[0, 0]}>
        <Col xs={12} md={6}><Statistic title="User 授权" value={authorizations.data?.filter((item) => item.usable).length ?? 0} /></Col>
        <Col xs={12} md={6}><Statistic title="消息范围" value={scopes.data?.filter((item) => item.identityType === 'user').length ?? 0} /></Col>
        <Col xs={12} md={6}><Statistic title="已允许" value={scopes.data?.filter((item) => item.identityType === 'user' && item.status === 'allowed').length ?? 0} /></Col>
        <Col xs={12} md={6}><Statistic title="文件夹订阅" value={subscriptions.data?.filter((item) => item.active).length ?? 0} /></Col>
      </Row>
    </div>

    <Row gutter={[14, 14]} align="top">
      <Col xs={24} xl={16}>
        <Card className="feishu-source-card" title="消息范围与同步" variant="borderless">
          <Form
            className="feishu-scope-form"
            form={scopeForm}
            layout="vertical"
            initialValues={{ identityType: 'user', scopeType: 'group', backfillDays: 7 }}
            onFinish={(values) => register.mutate(values)}
          >
            <Form.Item name="chatId" label="已知 chat_id" rules={[{ required: true }]}><Input placeholder="oc_... / P2P chat_id" autoComplete="off" /></Form.Item>
            <Form.Item name="displayName" label="本地名称"><Input placeholder="仅用于工作台显示" /></Form.Item>
            <Form.Item name="identityType" label="身份"><Select options={[{ value: 'user', label: 'User OAuth' }, { value: 'app', label: 'App / Bot' }]} /></Form.Item>
            <Form.Item name="scopeType" label="类型"><Select options={[{ value: 'group', label: '群聊' }, { value: 'p2p', label: 'P2P' }]} /></Form.Item>
            <Form.Item name="backfillDays" label="首次回溯（天）"><InputNumber min={0} max={90} /></Form.Item>
            <Form.Item label=" "><Button htmlType="submit" icon={<PlusOutlined />} loading={register.isPending}>登记为未批准</Button></Form.Item>
          </Form>
          <Divider />
          <QueryState
            loading={scopes.isLoading}
            error={scopes.error}
            empty={!scopes.data?.length}
            emptyDescription="尚无飞书数据范围。可手工登记已知 P2P / 群聊，或授权后发现群聊。"
            onRetry={() => void scopes.refetch()}
          >
            <Table<FeishuScope>
              className="feishu-scope-table"
              rowKey="id"
              dataSource={scopes.data}
              pagination={false}
              scroll={{ x: 720 }}
              columns={[
                { title: '范围', width: 190, render: (_, item) => <Space direction="vertical" size={1}><Text strong>{item.displayName ?? '未命名范围'}</Text><Text code>{item.externalScopeId}</Text><Space><Tag>{item.identityType === 'user' ? 'User' : 'App/Bot'}</Tag><Tag>{item.scopeType === 'p2p' ? 'P2P' : '群聊'}</Tag></Space></Space> },
                { title: '采集决定', width: 140, render: (_, item) => <Space direction="vertical" size={2}><Tag color={statusColor[item.status]}>{statusLabel[item.status]}</Tag><Text type="secondary">{syncModeLabel[item.syncMode]} · 回溯 {item.backfillDays} 天</Text></Space> },
                { title: '最近事实', width: 160, render: (_, item) => <Space direction="vertical" size={1}><Text>{item.lastMessageAt ? new Date(item.lastMessageAt).toLocaleString() : '尚无同步消息'}</Text><Text type={item.lastErrorCode ? 'danger' : 'secondary'}>{item.lastErrorCode ?? '无已记录错误'}</Text></Space> },
                { title: '人工操作', width: 230, render: (_, item) => scopeActions(item) },
              ]}
            />
            <div className="feishu-scope-mobile-list">
              {(scopes.data ?? []).map((item) => <article key={item.id} className="feishu-scope-mobile-card">
                <div className="feishu-scope-mobile-card__heading">
                  <div><Text strong>{item.displayName ?? '未命名范围'}</Text><Text code>{item.externalScopeId}</Text></div>
                  <Tag color={statusColor[item.status]}>{statusLabel[item.status]}</Tag>
                </div>
                <dl>
                  <div><dt>身份 / 类型</dt><dd>{item.identityType === 'user' ? 'User' : 'App/Bot'} · {item.scopeType === 'p2p' ? 'P2P' : '群聊'}</dd></div>
                  <div><dt>同步范围</dt><dd>{syncModeLabel[item.syncMode]} · 回溯 {item.backfillDays} 天</dd></div>
                  <div><dt>最近事实</dt><dd>{item.lastMessageAt ? new Date(item.lastMessageAt).toLocaleString() : '尚无同步消息'}{item.lastErrorCode ? ` · ${item.lastErrorCode}` : ''}</dd></div>
                </dl>
                <div className="feishu-scope-mobile-card__actions">{scopeActions(item)}</div>
              </article>)}
            </div>
          </QueryState>
        </Card>
      </Col>

      <Col xs={24} xl={8}>
        <Card className="feishu-source-card" title={<Space><CloudOutlined />云文档</Space>} variant="borderless">
          <Text type="secondary">手动搜索导入，或订阅明确选择的文件夹；不会默认镜像全部云空间。</Text>
          <Form className="feishu-document-form" form={documentForm} layout="inline" onFinish={(values) => documentSearch.mutate(values)}>
            <Form.Item name="query" rules={[{ required: true }]}><Input prefix={<SearchOutlined />} placeholder="搜索我的飞书文档" /></Form.Item>
            <Form.Item><Button htmlType="submit" disabled={!driveSearchReady} loading={documentSearch.isPending}>搜索</Button></Form.Item>
          </Form>
          {documentResults.length > 0 && <List
            className="feishu-document-results"
            dataSource={documentResults}
            renderItem={(item) => {
              const document = documentIdentity(item);
              return <List.Item actions={[
                <Button
                  key="import"
                  size="small"
                  icon={<LinkOutlined />}
                  disabled={document.type !== 'docx' || !documentReadReady}
                  loading={documentImport.isPending}
                  onClick={() => documentImport.mutate(item)}
                >
                  导入
                </Button>,
              ]}>
                <List.Item.Meta title={document.title} description={`${document.type || '未知类型'} · ${document.token || '无 token'}`} />
              </List.Item>;
            }}
          />}
          <Divider />
          <Title level={5}>文件夹订阅</Title>
          <Form form={folderForm} layout="vertical" onFinish={(values) => subscribeFolder.mutate(values)}>
            <Form.Item name="folderToken" label="folder_token" rules={[{ required: true }]}><Input prefix={<FolderOpenOutlined />} placeholder="只填写明确选择的法务文件夹" /></Form.Item>
            <Form.Item name="recursive" valuePropName="checked"><Checkbox>递归同步子文件夹</Checkbox></Form.Item>
            <Button htmlType="submit" disabled={!driveSearchReady} loading={subscribeFolder.isPending}>订阅文件夹</Button>
          </Form>
          {(subscriptions.data?.length ?? 0) > 0 && <List
            className="feishu-folder-list"
            dataSource={subscriptions.data}
            renderItem={(item) => <List.Item><List.Item.Meta title={<Space><Text code>{item.folderToken}</Text><Tag color={item.active ? 'green' : 'default'}>{item.active ? '启用' : '停用'}</Tag></Space>} description={`${item.recursive ? '递归' : '仅当前层'} · 最近同步 ${item.lastSyncedAt ? new Date(item.lastSyncedAt).toLocaleString() : '—'} · 版本 ${item.version}`} /></List.Item>}
          />}
        </Card>
      </Col>
    </Row>
  </div>;
}
