import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Button, Dropdown } from 'antd';
import {
  HomeOutlined,
  PlusOutlined,
  CalendarOutlined,
  CompassOutlined,
  UserOutlined,
  LogoutOutlined,
  LoginOutlined
} from '@ant-design/icons';
import { routes } from './routes';
import { useSelector, useDispatch } from 'react-redux';
import { RootState } from './store';
import { logout } from './store/slices/authSlice';

// 【去AI味】全页手工质感纹理覆盖
import TextureOverlay from './components/TextureOverlay';

// 【去AI味】手工感主题样式（覆盖 Ant Design 默认主题）
import './styles/travel-theme.css';

const { Header, Content, Footer } = Layout;

// 简单的 JWT 解码函数
function parseJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = parts[1];
    const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    return JSON.parse(decoded);
  } catch { return null; }
}

function isTokenExpired(token: string): boolean {
  const payload = parseJwtPayload(token);
  if (!payload || !payload.exp) return true;
  return (payload.exp as number) * 1000 < Date.now();
}

// 内部组件，可以使用useNavigate和useLocation
const AppContent: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const dispatch = useDispatch();
  const { isLoggedIn, user } = useSelector((state: RootState) => state.auth);

  // 页面加载时检查 token 是否过期
  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    if (storedToken && isTokenExpired(storedToken)) {
      dispatch(logout());
      if (location.pathname !== '/login') {
        navigate('/login', { replace: true });
      }
    }
  }, []);

  const menuItems = [
    { key: '/', icon: <HomeOutlined />, label: '首页' },
    { key: '/requirement', icon: <PlusOutlined />, label: '新建行程' },
    { key: '/itineraries', icon: <CalendarOutlined />, label: '我的行程' },
  ];

  const handleMenuClick = ({ key }: { key: string }) => navigate(key);

  const handleLogout = () => {
    dispatch(logout());
    navigate('/');
  };

  const userMenuItems = isLoggedIn
    ? [
        { key: 'profile', icon: <UserOutlined />, label: '个人中心', onClick: () => navigate('/profile') },
        { type: 'divider' as const },
        { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: handleLogout },
      ]
    : [
        { key: 'login', icon: <LoginOutlined />, label: '登录', onClick: () => navigate('/login') },
      ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* 【去AI味】全页覆盖噪点纹理，模拟旧纸张印刷质感 */}
      <TextureOverlay />

      <Header style={{ display: 'flex', alignItems: 'center', padding: '0 24px', position: 'relative', zIndex: 1000 }}>
        {/* 【去AI味】品牌名：衬线体 + 旅程叙事感，而非功能陈述 */}
        <div
          style={{
            fontSize: '22px',
            fontFamily: "'Cormorant Garamond', Georgia, serif",
            letterSpacing: '2px',
            fontWeight: 600,
            marginRight: '48px',
            cursor: 'pointer',
            color: '#f0e8da',
          }}
          onClick={() => navigate('/')}
        >
          <CompassOutlined style={{ marginRight: 4, opacity: 0.7 }} />
          旅途手账
        </div>
        <Menu theme="dark" mode="horizontal" selectedKeys={[location.pathname]} items={menuItems} onClick={handleMenuClick}
          style={{ flex: 1, minWidth: 0 }} />
        <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
          <Button type="text" style={{ color: '#e0d8ce' }}>
            <UserOutlined />
            {isLoggedIn ? (user?.username || '用户') : '登录'}
          </Button>
        </Dropdown>
      </Header>

      <Content style={{ padding: '0', position: 'relative', zIndex: 1 }}>
        <div style={{ minHeight: 280 }}>
          <Routes>
            {routes.map((route, index) => (
              <Route key={index} path={route.path} element={route.element} />
            ))}
          </Routes>
        </div>
      </Content>

      {/* 【去AI味】页脚：手写感短句，而非标准版权模板 */}
      <Footer style={{ textAlign: 'center', position: 'relative', zIndex: 1, padding: '16px 50px' }}>
        <span style={{ fontFamily: "'Cormorant Garamond', Georgia, serif", fontSize: 14, letterSpacing: 1 }}>
          旅途手账 · 把路上的日子写成书
        </span>
      </Footer>
    </Layout>
  );
};

// 主应用组件
const App: React.FC = () => (
  <BrowserRouter>
    <AppContent />
  </BrowserRouter>
);

export default App;

