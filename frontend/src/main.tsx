import React from 'react';
import ReactDOM from 'react-dom/client';
import { Provider } from 'react-redux';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import App from './App';
import store from './store';
import './index.css';

// 设置dayjs中文
dayjs.locale('zh-cn');

// 【去AI味】全局禁用 Ant Design 默认的平滑渐变主题色，
// 改用 travel-theme.css 中的低明度旧纸张色调
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Provider store={store}>
      <ConfigProvider locale={zhCN}
        theme={{
          token: {
            colorPrimary: '#2c2420',       // 深棕黑替代默认蓝
            colorLink: '#4a7a8c',           // 褪色蓝替代亮蓝
            colorSuccess: '#6a8f6a',        // 军绿替代亮绿
            colorWarning: '#c45a4a',        // 邮戳红替代亮橙
            colorError: '#c45a4a',
            colorBorder: '#e0d8ce',
            colorBgContainer: '#faf7f2',
            colorBgLayout: '#f7f3ee',
            borderRadius: 0,                // 禁用所有默认圆角
            fontFamily: "'Inter', -apple-system, 'Segoe UI', sans-serif",
          },
        }}
      >
        <App />
      </ConfigProvider>
    </Provider>
  </React.StrictMode>,
);
