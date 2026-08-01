import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider, App as AntApp, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import RootApp from './App';
import { RealtimeProvider } from './services/RealtimeProvider';
import './styles/global.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 3_000, retry: 1, refetchOnWindowFocus: true },
    mutations: { retry: 0 },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <RealtimeProvider>
          <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#315f8f',
          colorInfo: '#315f8f',
          colorSuccess: '#31735d',
          colorWarning: '#9c672c',
          colorError: '#a84949',
          colorText: '#17243a',
          colorTextSecondary: '#657083',
          colorBorder: '#d8dee8',
          borderRadius: 6,
          fontFamily: 'Inter, PingFang SC, Microsoft YaHei, system-ui, sans-serif',
        },
        components: {
          Button: { borderRadius: 5, controlHeight: 34 },
          Card: { borderRadiusLG: 6 },
          Table: { headerBg: '#f4f6f9', headerColor: '#4c596d' },
          Menu: { itemBorderRadius: 4 },
        },
      }}
          >
            <AntApp>
              <RootApp />
            </AntApp>
          </ConfigProvider>
        </RealtimeProvider>
      </QueryClientProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
