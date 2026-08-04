import { Avatar, Button, Drawer, Input, Layout, Menu, type MenuProps } from 'antd';
import {
  AppstoreOutlined,
  AuditOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  HomeOutlined,
  InboxOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { lazy, Suspense, useEffect, useState } from 'react';
import { buildPath, navigate, useAppLocation, type AppRoute } from './navigation';
import StatePanel from './components/StatePanel';
import UnavailableState from './components/UnavailableState';

const { Sider, Header, Content } = Layout;

const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const InboxPage = lazy(() => import('./pages/InboxPage'));
const TaskCenterPage = lazy(() => import('./pages/TaskCenterPage'));
const TaskDetailPage = lazy(() => import('./pages/TaskDetailPage'));
const ReviewCenterPage = lazy(() => import('./pages/ReviewCenterPage'));
const AgentCenterPage = lazy(() => import('./pages/AgentCenterPage'));
const LibraryPage = lazy(() => import('./pages/LibraryPage'));
const SecurityPage = lazy(() => import('./pages/SecurityPage'));

const navItems: MenuProps['items'] = [
  {
    type: 'group',
    label: '工作',
    children: [
      { key: '/today', icon: <HomeOutlined />, label: '今日工作台' },
      { key: '/inbox', icon: <InboxOutlined />, label: '待确认消息' },
      { key: '/matters', icon: <AppstoreOutlined />, label: '法务事项' },
      { key: '/reviews', icon: <AuditOutlined />, label: '审核中心' },
    ],
  },
  {
    type: 'group',
    label: '资料与模板',
    children: [
      { key: '/templates', icon: <DatabaseOutlined />, label: '事项模板' },
      { key: '/files', icon: <FileTextOutlined />, label: '合同与文件' },
    ],
  },
  {
    type: 'group',
    label: '系统与审计',
    children: [
      { key: '/system/agent-runs', icon: <RobotOutlined />, label: 'Agent 执行记录' },
      { key: '/system/data-boundaries', icon: <SafetyCertificateOutlined />, label: '数据边界' },
      { key: '/system/about', icon: <SettingOutlined />, label: '系统信息' },
    ],
  },
];

function selectedNavigationPath(route: AppRoute): string {
  switch (route.name) {
    case 'today': return '/today';
    case 'inbox': return '/inbox';
    case 'matters': return '/matters';
    case 'reviews': return '/reviews';
    case 'templates': return '/templates';
    case 'files': return '/files';
    case 'agent-runs': return '/system/agent-runs';
    case 'data-boundaries': return '/system/data-boundaries';
    case 'about': return '/system/about';
    case 'not-found': return '';
  }
}

export default function RootApp() {
  const [collapsed, setCollapsed] = useState(false);
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth);
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const [matterSearch, setMatterSearch] = useState('');
  const route = useAppLocation();

  useEffect(() => {
    if (window.location.pathname === '/') navigate('/today', { replace: true });
  }, []);

  useEffect(() => {
    const updateViewport = () => setViewportWidth(window.innerWidth);
    window.addEventListener('resize', updateViewport);
    return () => window.removeEventListener('resize', updateViewport);
  }, []);

  useEffect(() => {
    if (route.name === 'matters') {
      setMatterSearch(new URLSearchParams(route.search).get('q') ?? '');
    }
  }, [route.name, route.search]);

  const isMobile = viewportWidth < 768;
  const isCompact = viewportWidth < 1100;
  const isSiderCollapsed = collapsed || isCompact;
  const pageNames: Record<AppRoute['name'], string> = {
    today: '今日工作台',
    inbox: '待确认消息',
    matters: '法务事项',
    reviews: '审核中心',
    templates: '事项模板',
    files: '合同与文件',
    'agent-runs': 'Agent 执行记录',
    'data-boundaries': '数据边界',
    about: '系统信息',
    'not-found': '页面不存在',
  };

  const openMatter = (matterId: string) => {
    const returnTo = route.name === 'matters' ? buildPath(route) : '/matters';
    navigate(buildPath({ name: 'matters', matterId }), { state: { returnTo, returnScrollY: window.scrollY } });
  };

  const openInbox = () => {
    navigate('/inbox');
    setMobileNavigationOpen(false);
  };

  const selectPage = (path: string) => {
    navigate(path);
    setMobileNavigationOpen(false);
  };

  const searchMatters = (value: string) => {
    const query = new URLSearchParams();
    if (value.trim()) query.set('q', value.trim());
    navigate(`/matters${query.size ? `?${query.toString()}` : ''}`);
  };

  const updateMatterFilter = (value: string) => {
    const query = new URLSearchParams(route.name === 'matters' ? route.search : '');
    if (value) query.set('q', value);
    else query.delete('q');
    query.delete('page');
    navigate(`/matters${query.size ? `?${query.toString()}` : ''}`, { replace: true });
  };

  const renderPage = () => {
    if (route.name === 'matters' && route.matterId) {
      return (
        <TaskDetailPage
          matterId={route.matterId}
          onBack={() => {
            const navigationState = window.history.state as { returnTo?: string; returnScrollY?: number } | null;
            navigate(navigationState?.returnTo ?? '/matters', {
              state: { restoreScrollY: navigationState?.returnScrollY },
            });
          }}
          onReviewPackageCreated={(reviewPackageId) => navigate(
            buildPath({ name: 'reviews', reviewPackageId }),
            { state: { returnTo: buildPath(route) } },
          )}
        />
      );
    }
    if (route.name === 'today') {
      return <DashboardPage onOpenTask={() => navigate('/matters')} onOpenInbox={openInbox} />;
    }
    if (route.name === 'inbox') {
      return (
        <InboxPage
          candidateId={route.candidateId}
          onCandidateSelected={(candidateId) => navigate(buildPath({ name: 'inbox', candidateId, search: route.search }))}
          onMatterCreated={openMatter}
          onOpenAgentRun={(runId) => navigate(buildPath({ name: 'agent-runs', runId }))}
        />
      );
    }
    if (route.name === 'matters') {
      return (
        <TaskCenterPage
          keyword={new URLSearchParams(route.search).get('q') ?? ''}
          onKeywordChange={updateMatterFilter}
          onOpenMatter={openMatter}
        />
      );
    }
    if (route.name === 'reviews') {
      return (
        <ReviewCenterPage
          reviewPackageId={route.reviewPackageId}
          onReviewSelected={(reviewPackageId) => navigate(buildPath({ name: 'reviews', reviewPackageId, search: route.search }))}
          onReviewClosed={() => navigate(buildPath({ name: 'reviews', search: route.search }))}
          onMatterSelected={(matterId) => navigate(
            buildPath({ name: 'matters', matterId }),
            { state: { returnTo: buildPath(route) } },
          )}
        />
      );
    }
    if (route.name === 'templates') return <LibraryPage onBrowseCategory={(category) => navigate(`/matters?category=${encodeURIComponent(category)}`)} />;
    if (route.name === 'agent-runs') {
      return (
        <AgentCenterPage
          runId={route.runId}
          onRunSelected={(runId) => navigate(buildPath({ name: 'agent-runs', runId, search: route.search }))}
          onRunClosed={() => navigate(buildPath({ name: 'agent-runs', search: route.search }))}
        />
      );
    }
    if (route.name === 'data-boundaries') return <SecurityPage />;
    if (route.name === 'files') return (
      <div className="page placeholder-page">
        <UnavailableState
          className="unavailable-state--files"
          title="合同与文件尚未接入"
          description={<span className="unavailable-state__details"><span>目的：集中管理合同与附件。</span><span>当前限制：文件内容尚未存储或检索。</span></span>}
          backendGap="文件存储与检索接口"
          alternative={<Button onClick={() => navigate('/matters')}>当前可在法务事项中查看已确认的事项和行动任务</Button>}
        />
      </div>
    );
    if (route.name === 'about') return (
      <div className="page placeholder-page">
        <UnavailableState
          className="unavailable-state--about"
          title="系统信息尚未接入"
          description={<span className="unavailable-state__details"><span>目的：核验本地运行环境与版本边界。</span><span>当前限制：没有可核验的版本、连接或运行状态接口。</span></span>}
          backendGap="版本、连接与运行状态接口"
          alternative={<Button onClick={() => navigate('/system/data-boundaries')}>当前可查看数据边界与已实现能力</Button>}
        />
      </div>
    );
    return (
      <div className="page placeholder-page">
        <StatePanel
          variant="unavailable"
          title="页面不存在"
          description="当前地址未映射到法务工作台页面，请返回已有工作入口。"
          action={<Button onClick={() => navigate('/today')}>返回今日工作台</Button>}
        />
      </div>
    );
  };

  const selectedPath = selectedNavigationPath(route);

  return (
    <Layout className="app-shell">
      <Sider width={228} collapsedWidth={72} collapsed={isSiderCollapsed} className="app-sider" trigger={null}>
        <div className="brand"><div className="brand-mark">律</div>{!isSiderCollapsed && <div><strong>法务工作台</strong><span>Legal Workbench</span></div>}</div>
        <nav aria-label="主导航"><Menu mode="inline" selectedKeys={[selectedPath]} items={navItems} onClick={({ key }) => selectPage(key)} /></nav>
        {!isSiderCollapsed && <div className="sider-footer">本地演示 · 不代表连接或同步状态</div>}
      </Sider>
      <Drawer
        className="mobile-nav-drawer"
        title="法务工作台"
        placement="left"
        open={mobileNavigationOpen}
        onClose={() => setMobileNavigationOpen(false)}
        width={280}
      >
        <nav aria-label="主导航">
          <Menu mode="inline" selectedKeys={[selectedPath]} items={navItems} onClick={({ key }) => selectPage(key)} />
          <Button type="primary" block onClick={openInbox}>处理待确认消息</Button>
          <p className="drawer-status">本地演示 · 不代表连接或同步状态</p>
        </nav>
      </Drawer>
      <Layout>
        <Header className="app-header">
          <Button
            type="text"
            aria-label={isMobile ? '打开导航' : isSiderCollapsed ? '展开导航' : '收起导航'}
            icon={isMobile || isSiderCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => isMobile ? setMobileNavigationOpen(true) : setCollapsed((value) => !value)}
          />
          {isMobile && <span className="mobile-page-name">{pageNames[route.name]}</span>}
          {!isMobile && (
            <Input.Search
              className="global-search"
              aria-label="搜索法务事项"
              prefix={<SearchOutlined />}
              placeholder="搜索法务事项"
              value={matterSearch}
              allowClear
              onChange={(event) => setMatterSearch(event.target.value)}
              onSearch={searchMatters}
            />
          )}
          <div className="header-actions">
            <Avatar>林</Avatar>
          </div>
        </Header>
        <Content className="app-content">
          <Suspense fallback={<div className="page"><StatePanel variant="loading" title="正在打开页面" description="正在加载当前工作区。" /></div>}>
            {renderPage()}
          </Suspense>
        </Content>
      </Layout>
    </Layout>
  );
}
