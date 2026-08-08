import { Avatar, Badge, Button, Input, Layout, Menu, Tooltip } from 'antd';
import {
  AppstoreOutlined,
  AuditOutlined,
  BellOutlined,
  BulbOutlined,
  DatabaseOutlined,
  HomeOutlined,
  InboxOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { useEffect, useState } from 'react';
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import AgentCenterPage from './pages/AgentCenterPage';
import AgentRunDetailPage from './pages/AgentRunDetailPage';
import DashboardPage from './pages/DashboardPage';
import InboxPage from './pages/InboxPage';
import LibraryPage from './pages/LibraryPage';
import MessageDetailPage from './pages/MessageDetailPage';
import MatterUpdateProposalPage from './pages/MatterUpdateProposalPage';
import ReviewCenterPage from './pages/ReviewCenterPage';
import SecurityPage from './pages/SecurityPage';
import SetupPage from './pages/SetupPage';
import FeishuScopesPage from './pages/FeishuScopesPage';
import SystemStatusPage from './pages/SystemStatusPage';
import TaskCenterPage from './pages/TaskCenterPage';
import TaskDetailPage from './pages/TaskDetailPage';
import { QueryState } from './components/QueryState';
import { legalApi } from './services/api';
import { useRealtimeStatus } from './services/RealtimeProvider';

const { Sider, Header, Content } = Layout;

const navItems = [
  { key: '/dashboard', icon: <HomeOutlined />, label: '今日工作台' },
  { key: '/inbox', icon: <InboxOutlined />, label: 'AI 收件箱' },
  { key: '/matters', icon: <AppstoreOutlined />, label: '法务事项' },
  { key: '/reviews', icon: <AuditOutlined />, label: '审核中心' },
  { key: '/library', icon: <DatabaseOutlined />, label: '法务事项库' },
  { key: '/agent-runs', icon: <RobotOutlined />, label: 'Agent 运行中心' },
  { key: '/security', icon: <SafetyCertificateOutlined />, label: '数据与权限' },
  { key: '/setup', icon: <SettingOutlined />, label: '首次配置' },
  { key: '/settings/feishu-scopes', icon: <SafetyCertificateOutlined />, label: '飞书个人同步' },
  { key: '/system', icon: <SettingOutlined />, label: '系统状态' },
];

function MatterDetailRoute() {
  const { matterId = '' } = useParams();
  const navigate = useNavigate();
  return <TaskDetailPage matterId={matterId} onBack={() => navigate('/matters')} />;
}

function CandidateRoute() {
  const { candidateId = '' } = useParams();
  const candidate = useQuery({
    queryKey: ['candidate', candidateId],
    queryFn: () => legalApi.getCandidate(candidateId),
    enabled: Boolean(candidateId),
  });
  return <QueryState loading={candidate.isLoading} error={candidate.error} onRetry={() => void candidate.refetch()}>
    {candidate.data?.feishuMessageId
      ? <Navigate replace to={`/inbox/${candidate.data.feishuMessageId}`} />
      : <div className="page placeholder-page"><h2>Candidate 没有关联来源消息</h2><p>请从 AgentRun 或审计记录继续调查。</p></div>}
  </QueryState>;
}

function RouteContent() {
  const navigate = useNavigate();
  const location = useLocation();
  const matterKeyword = new URLSearchParams(location.search).get('q') ?? '';

  const updateMatterKeyword = (keyword: string) => {
    const query = new URLSearchParams(location.search);
    if (keyword.trim()) query.set('q', keyword.trim());
    else query.delete('q');
    query.delete('page');
    navigate(`/matters${query.size ? `?${query.toString()}` : ''}`, { replace: true });
  };

  return <Routes>
    <Route path="/" element={<Navigate replace to="/dashboard" />} />
    <Route path="/dashboard" element={<DashboardPage />} />
    <Route path="/inbox" element={<InboxPage />} />
    <Route path="/inbox/:messageId" element={<MessageDetailPage />} />
    <Route path="/candidates/:candidateId" element={<CandidateRoute />} />
    <Route path="/agent-runs" element={<AgentCenterPage />} />
    <Route path="/agent-runs/:runId" element={<AgentRunDetailPage />} />
    <Route path="/system" element={<SystemStatusPage />} />
    <Route path="/setup" element={<SetupPage />} />
    <Route path="/settings/feishu-scopes" element={<FeishuScopesPage />} />
    <Route path="/matters" element={<TaskCenterPage keyword={matterKeyword} onKeywordChange={updateMatterKeyword} onOpenMatter={(id) => navigate(`/matters/${id}`)} />} />
    <Route path="/matters/:matterId" element={<MatterDetailRoute />} />
    <Route path="/matter-update-proposals/:proposalId" element={<MatterUpdateProposalPage />} />
    <Route path="/reviews" element={<ReviewCenterPage />} />
    <Route path="/library" element={<LibraryPage onBrowseCategory={(category) => navigate(`/matters?category=${encodeURIComponent(category)}`)} />} />
    <Route path="/security" element={<SecurityPage />} />
    <Route path="*" element={<div className="page placeholder-page"><h2>页面不存在</h2><Button onClick={() => navigate('/inbox')}>返回收件箱</Button></div>} />
  </Routes>;
}

function selectedNav(pathname: string): string {
  return navItems.find((item) => pathname === item.key || pathname.startsWith(`${item.key}/`))?.key ?? '/inbox';
}

export default function RootApp() {
  const [collapsed, setCollapsed] = useState(false);
  const [darkMode, setDarkMode] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const realtime = useRealtimeStatus();

  useEffect(() => {
    document.body.classList.toggle('dark-mode', darkMode);
  }, [darkMode]);

  return <Layout className="app-shell">
    <Sider width={228} collapsedWidth={72} collapsed={collapsed} className="app-sider" trigger={null}>
      <div className="brand"><div className="brand-mark">律</div>{!collapsed && <div><strong>法务工作台</strong><span>Legal Workbench</span></div>}</div>
      <Menu mode="inline" selectedKeys={[selectedNav(location.pathname)]} items={navItems} onClick={({ key }) => navigate(key)} />
      <div className="sider-footer"><div className={`sync-dot ${realtime.connected ? '' : 'degraded'}`} />{!collapsed && <span>{realtime.connected ? '实时状态已连接' : '实时断开，轮询中'}</span>}</div>
    </Sider>
    <Layout>
      <Header className="app-header">
        <Button type="text" icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />} onClick={() => setCollapsed((value) => !value)} />
        <Input className="global-search" prefix={<SearchOutlined />} placeholder="在 AI 收件箱搜索真实消息" onPressEnter={(event) => navigate(`/inbox?search=${encodeURIComponent(event.currentTarget.value)}`)} />
        <div className="header-actions">
          <Tooltip title={realtime.connected ? 'SSE 实时连接正常' : 'SSE 断开，已回退到轮询'}><Button type="text" icon={<SafetyCertificateOutlined />} onClick={() => navigate('/system')}><span className="header-status">{realtime.connected ? '实时' : '降级'}</span></Button></Tooltip>
          <Tooltip title={darkMode ? '切换浅色模式' : '切换深色模式'}><Button type="text" icon={<BulbOutlined />} onClick={() => setDarkMode((value) => !value)} /></Tooltip>
          <Tooltip title="Agent 运行中心"><Button type="text" icon={<RobotOutlined />} onClick={() => navigate('/agent-runs')} /></Tooltip>
          <Badge dot={!realtime.connected}><Button type="text" icon={<BellOutlined />} onClick={() => navigate('/system')} /></Badge>
          <Avatar>法</Avatar>
        </div>
      </Header>
      <Content className="app-content"><RouteContent /></Content>
    </Layout>
  </Layout>;
}
