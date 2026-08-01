import { Avatar, Badge, Button, Input, Layout, Menu, Tooltip } from 'antd';
import {
  AppstoreOutlined,
  AuditOutlined,
  BellOutlined,
  BulbOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  HomeOutlined,
  InboxOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PlusOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { useEffect, useState } from 'react';
import DashboardPage from './pages/DashboardPage';
import InboxPage from './pages/InboxPage';
import TaskCenterPage from './pages/TaskCenterPage';
import TaskDetailPage from './pages/TaskDetailPage';
import ReviewCenterPage from './pages/ReviewCenterPage';
import AgentCenterPage from './pages/AgentCenterPage';
import LibraryPage from './pages/LibraryPage';
import SecurityPage from './pages/SecurityPage';

const { Sider, Header, Content } = Layout;

const navItems = [
  { key: 'dashboard', icon: <HomeOutlined />, label: '今日工作台' },
  { key: 'inbox', icon: <InboxOutlined />, label: <span>AI 收件箱 <Badge count={0} size="small" /></span> },
  { key: 'matters', icon: <AppstoreOutlined />, label: '法务事项' },
  { key: 'reviews', icon: <AuditOutlined />, label: '审核中心' },
  { key: 'library', icon: <DatabaseOutlined />, label: '法务事项库' },
  { key: 'files', icon: <FileTextOutlined />, label: '合同与文件' },
  { key: 'agents', icon: <RobotOutlined />, label: 'Agent 中心' },
  { key: 'security', icon: <SafetyCertificateOutlined />, label: '数据与权限' },
  { key: 'settings', icon: <SettingOutlined />, label: '系统设置' },
];

export default function RootApp() {
  const [collapsed, setCollapsed] = useState(false);
  const [page, setPage] = useState('dashboard');
  const [selectedMatterId, setSelectedMatterId] = useState<string>();
  const [darkMode, setDarkMode] = useState(false);

  useEffect(() => {
    document.body.classList.toggle('dark-mode', darkMode);
  }, [darkMode]);

  const openMatter = (matterId: string) => {
    setPage('matters');
    setSelectedMatterId(matterId);
  };

  const renderPage = () => {
    if (selectedMatterId) {
      return <TaskDetailPage matterId={selectedMatterId} onBack={() => setSelectedMatterId(undefined)} />;
    }
    if (page === 'dashboard') {
      return <DashboardPage onOpenTask={() => setPage('matters')} />;
    }
    if (page === 'inbox') return <InboxPage onMatterCreated={openMatter} />;
    if (page === 'matters') return <TaskCenterPage onOpenMatter={openMatter} />;
    if (page === 'reviews') return <ReviewCenterPage />;
    if (page === 'library') return <LibraryPage />;
    if (page === 'agents') return <AgentCenterPage />;
    if (page === 'security') return <SecurityPage />;
    return <div className="page placeholder-page"><h2>模块已预留</h2><p>该模块将在正式接入文件、系统设置或专项业务能力后启用。</p></div>;
  };

  return (
    <Layout className="app-shell">
      <Sider width={228} collapsedWidth={72} collapsed={collapsed} className="app-sider" trigger={null}>
        <div className="brand"><div className="brand-mark">律</div>{!collapsed && <div><strong>法务工作台</strong><span>Legal Workbench</span></div>}</div>
        <Menu mode="inline" selectedKeys={[page]} items={navItems} onClick={({ key }) => { setPage(key); setSelectedMatterId(undefined); }} />
        <div className="sider-footer"><div className="sync-dot" />{!collapsed && <span>本地服务已连接</span>}</div>
      </Sider>
      <Layout>
        <Header className="app-header">
          <Button type="text" icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />} onClick={() => setCollapsed((value) => !value)} />
          <Input className="global-search" prefix={<SearchOutlined />} placeholder="搜索事项、消息、任务、合同或输入 / 打开命令" />
          <div className="header-actions">
            <Button icon={<PlusOutlined />}>快速创建</Button>
            <Tooltip title="本地服务状态"><Button type="text" icon={<SafetyCertificateOutlined />}><span className="header-status">已连接</span></Button></Tooltip>
            <Tooltip title={darkMode ? '切换浅色模式' : '切换深色模式'}><Button type="text" icon={<BulbOutlined />} onClick={() => setDarkMode((value) => !value)} /></Tooltip>
            <Tooltip title="AI 管家"><Button type="text" icon={<RobotOutlined />} /></Tooltip>
            <Badge dot><Button type="text" icon={<BellOutlined />} /></Badge>
            <Avatar>林</Avatar>
          </div>
        </Header>
        <Content className="app-content">{renderPage()}</Content>
      </Layout>
    </Layout>
  );
}
