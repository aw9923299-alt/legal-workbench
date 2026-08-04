import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider, App as AntApp, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import RootApp from './App';
import './styles/global.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
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
          colorBgBase: '#ffffff',
          colorBgLayout: '#edf1f5',
          colorBgContainer: '#ffffff',
          colorFillAlter: '#f7f8fa',
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
  </React.StrictMode>,
);
