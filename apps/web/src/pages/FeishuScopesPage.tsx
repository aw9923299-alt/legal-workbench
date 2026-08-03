import {
  PauseCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  StopOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { useState } from 'react';
import { QueryState } from '../components/QueryState';
import {
  ApiError,
  createMutationContext,
  legalApi,
} from '../services/api';
import type {
  DeferredFeishuCompensation,
  FeishuScope,
  FeishuScopeSyncMode,
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
  all_messages: '指定群全部消息',
  disabled: '不同步',
};

type ScopeMutation =
  | { kind: 'register'; chatId: string; displayName?: string }
  | {
    kind: 'change';
    scope: FeishuScope;
    action: 'allow' | 'exclude' | 'pause' | 'resume';
    syncMode?: FeishuScopeSyncMode;
  }
  | { kind: 'compensate'; scope: FeishuScope };

function ErrorEvidence({ error }: { error: ApiError }) {
  return <Space direction="vertical" size={2}>
    <Text>{error.message}</Text>
    {error.code && <Text type="danger">错误码：{error.code}</Text>}
    {error.correlationId && <Text>Correlation ID：{error.correlationId}</Text>}
  </Space>;
}

export default function FeishuScopesPage() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm<{ chatId: string; displayName?: string }>();
  const [deferred, setDeferred] = useState<DeferredFeishuCompensation>();
  const scopes = useQuery({
    queryKey: ['settings', 'feishu-scopes'],
    queryFn: () => legalApi.listFeishuScopes(),
  });
  const mutation = useMutation<
    FeishuScope | DeferredFeishuCompensation,
    Error,
    ScopeMutation
  >({
    mutationFn: (value: ScopeMutation) => {
      const context = createMutationContext();
      if (value.kind === 'register') {
        return legalApi.registerFeishuScope(
          { chatId: value.chatId, displayName: value.displayName },
          context,
        );
      }
      if (value.kind === 'compensate') {
        return legalApi.compensateFeishuScope(
          value.scope.id,
          value.scope.version,
          context,
        );
      }
      return legalApi.changeFeishuScope(
        value.scope.id,
        value.scope.version,
        { action: value.action, syncMode: value.syncMode },
        context,
      );
    },
    onSuccess: (result, variables) => {
      const scope = 'scope' in result ? result.scope : result;
      queryClient.setQueryData<FeishuScope[]>(
        ['settings', 'feishu-scopes'],
        (current = []) => {
          const next = current.filter((item) => item.id !== scope.id);
          return [...next, scope].sort((left, right) => (
            left.displayName ?? left.externalScopeId
          ).localeCompare(right.displayName ?? right.externalScopeId, 'zh-CN'));
        },
      );
      if (variables.kind === 'compensate' && 'state' in result) {
        setDeferred(result);
        message.warning('补偿请求已记录，但真实同步未执行。');
      } else {
        setDeferred(undefined);
        message.success('群聊范围决定已写入 PostgreSQL 和审计记录。');
      }
      if (variables.kind === 'register') form.resetFields();
    },
  });
  const apiError = mutation.error instanceof ApiError ? mutation.error : undefined;

  const change = (
    scope: FeishuScope,
    action: 'allow' | 'exclude' | 'pause' | 'resume',
    syncMode?: FeishuScopeSyncMode,
  ) => mutation.mutate({ kind: 'change', scope, action, syncMode });

  return <div className="page feishu-scopes-page">
    <div className="page-title-row">
      <div>
        <span className="eyebrow">FEISHU SCOPE CONTROL</span>
        <Title level={2}>飞书群聊授权范围</Title>
        <Text type="secondary">敏感群默认不接入。所有允许、排除、暂停和恢复均由法务人工确认并使用版本锁。</Text>
      </div>
      <Button icon={<ReloadOutlined />} onClick={() => void scopes.refetch()}>刷新</Button>
    </div>

    <Alert
      type="warning"
      showIcon
      message="真实飞书消息与官方长连接仍为未执行"
      description="当前页面管理可审计的授权事实。手动补偿只记录请求，不调用飞书接口，也不会显示为同步成功。"
      style={{ marginBottom: 16 }}
    />
    {deferred && <Alert
      type="warning"
      showIcon
      closable
      onClose={() => setDeferred(undefined)}
      message={`${deferred.state} · ${deferred.errorCode}`}
      description={<Space direction="vertical" size={2}>
        <Text>{deferred.message}</Text>
        <Text>Correlation ID：{deferred.correlationId}</Text>
      </Space>}
      style={{ marginBottom: 16 }}
    />}
    {apiError && <Alert
      type="error"
      showIcon
      message="范围操作失败"
      description={<ErrorEvidence error={apiError} />}
      style={{ marginBottom: 16 }}
    />}

    <Card title="登记已知测试群" variant="borderless" style={{ marginBottom: 16 }}>
      <Form
        form={form}
        layout="inline"
        onFinish={(values) => mutation.mutate({ kind: 'register', ...values })}
      >
        <Form.Item
          name="chatId"
          label="chat_id"
          rules={[{ required: true, message: '请输入 chat_id' }]}
        >
          <Input placeholder="oc_..." autoComplete="off" />
        </Form.Item>
        <Form.Item name="displayName" label="群名称">
          <Input placeholder="仅作为本地显示名称" autoComplete="off" />
        </Form.Item>
        <Form.Item>
          <Button
            htmlType="submit"
            icon={<PlusOutlined />}
            loading={mutation.isPending}
          >登记为未批准</Button>
        </Form.Item>
      </Form>
    </Card>

    <Card title={`已知群聊（${scopes.data?.length ?? 0}）`} variant="borderless">
      <QueryState
        loading={scopes.isLoading}
        error={scopes.error}
        empty={!scopes.data?.length}
        emptyDescription="尚无已知群聊。可先手工登记测试群；真实事件发现功能仍在延后阶段。"
        onRetry={() => void scopes.refetch()}
      >
        <Table<FeishuScope>
          rowKey="id"
          dataSource={scopes.data}
          pagination={false}
          scroll={{ x: 1220 }}
          columns={[
            {
              title: '群聊',
              width: 220,
              render: (_, item) => <Space direction="vertical" size={1}>
                <Text strong>{item.displayName ?? '未命名群聊'}</Text>
                <Text code>{item.externalScopeId}</Text>
                <Text type="secondary">版本 {item.version}</Text>
              </Space>,
            },
            {
              title: '授权',
              width: 100,
              render: (_, item) => <Tag color={statusColor[item.status]}>{statusLabel[item.status]}</Tag>,
            },
            {
              title: '同步范围',
              width: 140,
              render: (_, item) => <Tag>{syncModeLabel[item.syncMode]}</Tag>,
            },
            {
              title: '最近状态',
              width: 260,
              render: (_, item) => <Space direction="vertical" size={1}>
                <Text>最近消息：{item.lastMessageAt ? new Date(item.lastMessageAt).toLocaleString() : '—'}</Text>
                <Text type={item.lastErrorCode ? 'danger' : 'secondary'}>
                  最近错误：{item.lastErrorCode ?? '—'}
                  {item.lastErrorMessage ? ` · ${item.lastErrorMessage}` : ''}
                </Text>
                <Text>最近补偿：{item.lastCompensatedAt ? new Date(item.lastCompensatedAt).toLocaleString() : '—'} · {item.lastCompensationStatus ?? '—'}</Text>
              </Space>,
            },
            {
              title: '人工操作',
              width: 470,
              render: (_, item) => <Space wrap>
                {(item.status === 'unapproved' || item.status === 'excluded') && <>
                  <Button
                    size="small"
                    icon={<SafetyCertificateOutlined />}
                    loading={mutation.isPending}
                    onClick={() => change(item, 'allow', 'mentions_only')}
                  >仅 @机器人</Button>
                  <Button
                    size="small"
                    loading={mutation.isPending}
                    onClick={() => change(item, 'allow', 'all_messages')}
                  >允许全部消息</Button>
                </>}
                {item.status === 'allowed' && <Button
                  size="small"
                  icon={<PauseCircleOutlined />}
                  onClick={() => change(item, 'pause')}
                >暂停</Button>}
                {item.status === 'paused' && <>
                  <Button size="small" onClick={() => change(item, 'resume', 'mentions_only')}>恢复仅 @</Button>
                  <Button size="small" onClick={() => change(item, 'resume', 'all_messages')}>恢复全部</Button>
                </>}
                {item.status !== 'excluded' && <Button
                  danger
                  size="small"
                  icon={<StopOutlined />}
                  onClick={() => change(item, 'exclude')}
                >排除</Button>}
                <Button
                  size="small"
                  icon={<SyncOutlined />}
                  loading={mutation.isPending}
                  onClick={() => mutation.mutate({ kind: 'compensate', scope: item })}
                >记录补偿请求</Button>
              </Space>,
            },
          ]}
        />
      </QueryState>
    </Card>
  </div>;
}
