import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Input,
  Row,
  Space,
  Steps,
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
  CodexCheckRequested,
  SetupActionResult,
  SetupComponent,
  SetupState,
} from '../types/api';

const { Title, Text, Paragraph } = Typography;

const stateLabels: Record<SetupState, string> = {
  not_configured: '未配置',
  invalid_credentials: '凭证无效',
  permission_missing: '权限不足',
  connected: '已连接',
  disconnected: '已断开',
  cli_missing: 'CLI 缺失',
  version_mismatch: '版本不一致',
  unauthenticated: '未认证',
  authenticated: '已认证',
  runtime_unreachable: 'Runtime 不可达',
  ready: '就绪',
  not_executed: '未执行',
  pending: '排队中',
};

const stateColors: Record<SetupState, string> = {
  ready: 'green',
  connected: 'green',
  authenticated: 'green',
  pending: 'blue',
  not_executed: 'default',
  not_configured: 'default',
  disconnected: 'orange',
  invalid_credentials: 'red',
  permission_missing: 'red',
  cli_missing: 'red',
  version_mismatch: 'orange',
  unauthenticated: 'orange',
  runtime_unreachable: 'red',
};

type SetupOperation =
  | { kind: 'validate_feishu'; appId: string; appSecret: string }
  | { kind: 'start_feishu' }
  | { kind: 'stop_feishu' }
  | { kind: 'validate_codex' }
  | { kind: 'smoke_codex' };

function StatusDetail({ value }: { value: SetupComponent }) {
  return <Space direction="vertical" size={3}>
    <Tag color={stateColors[value.state]}>{stateLabels[value.state]}</Tag>
    <Text>{value.message}</Text>
    {value.errorCode && <Text type="danger">错误码：{value.errorCode}</Text>}
    <Text type="secondary">Correlation ID：{value.correlationId}</Text>
  </Space>;
}

export default function SetupPage() {
  const queryClient = useQueryClient();
  const [appId, setAppId] = useState('');
  const [appSecret, setAppSecret] = useState('');
  const [lastResult, setLastResult] = useState<SetupActionResult | CodexCheckRequested>();
  const setup = useQuery({
    queryKey: ['setup', 'status'],
    queryFn: () => legalApi.getSetupStatus(),
    refetchInterval: (query) => query.state.data?.steps.some(
      (step) => step.component.state === 'pending',
    ) ? 2_000 : 10_000,
  });
  const operation = useMutation({
    mutationFn: async (input: SetupOperation) => {
      if (input.kind === 'validate_feishu') {
        return legalApi.validateFeishuSetup({
          appId: input.appId || undefined,
          appSecret: input.appSecret || undefined,
        });
      }
      if (input.kind === 'start_feishu') return legalApi.startFeishuSetup();
      if (input.kind === 'stop_feishu') return legalApi.stopFeishuSetup();
      const context = createMutationContext();
      return input.kind === 'validate_codex'
        ? legalApi.validateCodexSetup(context)
        : legalApi.smokeTestCodexSetup(context);
    },
    onSuccess: (result) => {
      setLastResult(result);
      if (result.state === 'not_executed') {
        message.warning('操作未执行。请查看稳定错误码和实施阶段说明。');
      } else {
        message.info('检查已提交。页面会从 PostgreSQL 状态持续刷新。');
      }
      void queryClient.invalidateQueries({ queryKey: ['setup', 'status'] });
    },
    onSettled: (_data, _error, variables) => {
      if (variables.kind === 'validate_feishu') setAppSecret('');
    },
  });
  const apiError = operation.error instanceof ApiError ? operation.error : undefined;

  return <div className="page setup-page">
    <div className="page-title-row">
      <div>
        <span className="eyebrow">LOCAL ONBOARDING</span>
        <Title level={2}>首次配置与真实运行检查</Title>
        <Text type="secondary">页面只显示掩码与状态。Secret 不会保存在浏览器、API 响应、PostgreSQL 或 Codex 工作目录。</Text>
      </div>
      <Button icon={<ReloadOutlined />} onClick={() => void setup.refetch()}>刷新状态</Button>
    </div>

    <Alert
      type="warning"
      showIcon
      message="真实飞书测试消息与官方长连接本阶段明确延后"
      description="相关步骤统一显示“未执行”和 REAL_FEISHU_PHASE_DEFERRED。系统不会模拟个人客户端、打开飞书会话或改变个人账号已读状态。"
      style={{ marginBottom: 16 }}
    />

    {lastResult && <Alert
      type={lastResult.state === 'not_executed' ? 'warning' : 'info'}
      showIcon
      closable
      onClose={() => setLastResult(undefined)}
      message={`${stateLabels[lastResult.state]}：${lastResult.message}`}
      description={<Space direction="vertical">
        {'errorCode' in lastResult && lastResult.errorCode && <Text>错误码：{lastResult.errorCode}</Text>}
        <Text>Correlation ID：{lastResult.correlationId}</Text>
      </Space>}
      style={{ marginBottom: 16 }}
    />}
    {apiError && <Alert
      type="error"
      showIcon
      message={apiError.message}
      description={<Space direction="vertical">
        {apiError.code && <Text>错误码：{apiError.code}</Text>}
        {apiError.correlationId && <Text>Correlation ID：{apiError.correlationId}</Text>}
      </Space>}
      style={{ marginBottom: 16 }}
    />}

    <QueryState loading={setup.isLoading} error={setup.error} onRetry={() => void setup.refetch()}>
      {setup.data && <>
        <Card variant="borderless" title="九步初始化进度">
          <Steps
            direction="vertical"
            size="small"
            items={setup.data.steps.map((step) => ({
              title: `${step.number}. ${step.title}`,
              status: step.component.state === 'ready'
                || step.component.state === 'authenticated'
                || step.component.state === 'connected'
                ? 'finish'
                : step.component.state === 'pending' ? 'process' : 'wait',
              icon: step.component.state === 'ready'
                ? <CheckCircleOutlined />
                : step.component.state === 'pending'
                  ? <ClockCircleOutlined />
                  : <ExclamationCircleOutlined />,
              description: <StatusDetail value={step.component} />,
            }))}
          />
        </Card>

        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} xl={12}>
            <Card title="飞书凭证与连接范围" variant="borderless">
              <Alert
                type="info"
                showIcon
                message="当前表单为写入前预检入口"
                description="由于真实飞书阶段已延后，提交不会验证或保存新 Secret，也不会启动长连接。"
                style={{ marginBottom: 14 }}
              />
              <Space direction="vertical" style={{ width: '100%' }}>
                <label htmlFor="setup-feishu-app-id">Feishu App ID</label>
                <Input
                  id="setup-feishu-app-id"
                  value={appId}
                  onChange={(event) => setAppId(event.target.value)}
                  placeholder={setup.data.feishu.credentials.appIdMasked ?? 'cli_••••'}
                  autoComplete="off"
                />
                <label htmlFor="setup-feishu-app-secret">Feishu App Secret（仅写入）</label>
                <Input.Password
                  id="setup-feishu-app-secret"
                  value={appSecret}
                  onChange={(event) => setAppSecret(event.target.value)}
                  placeholder={setup.data.feishu.credentials.secretMasked ?? '未配置'}
                  autoComplete="new-password"
                />
                <Space wrap>
                  <Button
                    type="primary"
                    icon={<SafetyCertificateOutlined />}
                    loading={operation.isPending}
                    onClick={() => operation.mutate({ kind: 'validate_feishu', appId, appSecret })}
                  >验证凭证</Button>
                  <Button loading={operation.isPending} onClick={() => operation.mutate({ kind: 'start_feishu' })}>启动长连接</Button>
                  <Button loading={operation.isPending} onClick={() => operation.mutate({ kind: 'stop_feishu' })}>停止长连接</Button>
                </Space>
              </Space>
              <Descriptions bordered size="small" column={1} style={{ marginTop: 16 }}>
                <Descriptions.Item label="凭证已配置">{setup.data.feishu.credentials.configured ? '是' : '否'}</Descriptions.Item>
                <Descriptions.Item label="App ID 掩码">{setup.data.feishu.credentials.appIdMasked ?? '—'}</Descriptions.Item>
                <Descriptions.Item label="Secret 掩码">{setup.data.feishu.credentials.secretMasked ?? '—'}</Descriptions.Item>
                <Descriptions.Item label="事件源">{setup.data.feishu.eventSource}</Descriptions.Item>
                <Descriptions.Item label="机器人单聊">{setup.data.feishu.receiveDirectMessages ? '接收' : '不接收'}</Descriptions.Item>
                <Descriptions.Item label="群聊 @机器人">{setup.data.feishu.groupMentionsOnly ? '接收' : '不接收'}</Descriptions.Item>
                <Descriptions.Item label="指定群全部消息">{setup.data.feishu.configuredGroupAllMessages ? '接收' : '不接收'}</Descriptions.Item>
                <Descriptions.Item label="允许群">{setup.data.feishu.allowedScopeCount}</Descriptions.Item>
                <Descriptions.Item label="排除群">{setup.data.feishu.excludedScopeCount}</Descriptions.Item>
              </Descriptions>
              <Paragraph type="secondary" style={{ marginTop: 12 }}>
                人工验收项：用户 B 不打开会话时，由测试账号 A 确认 B 侧仍为未读。本页面不会自动声称该项通过。
              </Paragraph>
            </Card>
          </Col>

          <Col xs={24} xl={12}>
            <Card title="Codex CLI 与隔离 Worker" variant="borderless">
              <Descriptions bordered size="small" column={1}>
                <Descriptions.Item label="期望版本">{setup.data.codex.expectedVersion}</Descriptions.Item>
                <Descriptions.Item label="检测版本">{setup.data.codex.detectedVersion ?? '—'}</Descriptions.Item>
                <Descriptions.Item label="CLI"><StatusDetail value={setup.data.codex.cli} /></Descriptions.Item>
                <Descriptions.Item label="版本"><StatusDetail value={setup.data.codex.version} /></Descriptions.Item>
                <Descriptions.Item label="认证"><StatusDetail value={setup.data.codex.authentication} /></Descriptions.Item>
                <Descriptions.Item label="冒烟"><StatusDetail value={setup.data.codex.smokeTest} /></Descriptions.Item>
              </Descriptions>
              <Space wrap style={{ marginTop: 16 }}>
                <Button
                  type="primary"
                  loading={operation.isPending}
                  onClick={() => operation.mutate({ kind: 'validate_codex' })}
                >验证 Codex</Button>
                <Button
                  loading={operation.isPending}
                  onClick={() => operation.mutate({ kind: 'smoke_codex' })}
                >真实 Codex 冒烟</Button>
              </Space>
              <Paragraph type="secondary" style={{ marginTop: 12 }}>
                API 只写入检查请求和 Outbox。认证与真实推理由并发为 1 的隔离 Worker 执行，结果脱敏后写回 PostgreSQL。
              </Paragraph>
            </Card>
          </Col>
        </Row>
        <div className="updated-at">状态快照：{new Date(setup.data.generatedAt).toLocaleString()} · Correlation ID：{setup.data.correlationId}</div>
      </>}
    </QueryState>
  </div>;
}
