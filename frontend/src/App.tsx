import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, theme, Button ,Dropdown} from 'antd';
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


const { Header, Content, Footer } = Layout;

// 简单的 JWT 解码函数（不需要额外库）
function parseJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = parts[1];
    // Base64 URL-safe decode
    const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    return JSON.parse(decoded);
  } catch {
    return null;
  }
}

function isTokenExpired(token: string): boolean {
  const payload = parseJwtPayload(token);
  if (!payload || !payload.exp) return true;
  // exp 是秒级时间戳，转为毫秒比较
  return (payload.exp as number) * 1000 < Date.now();
}

// 内部组件，可以使用useNavigate和useLocation
const AppContent: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const dispatch = useDispatch();
  const { isLoggedIn, user } = useSelector((state: RootState) => state.auth);
  const { token: { colorBgContainer, borderRadiusLG } } = theme.useToken();

  // 页面加载时检查 token 是否过期
  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    if (storedToken && isTokenExpired(storedToken)) {
    dispatch(logout());
      // 如果当前不在登录页，跳转到登录页
      if (location.pathname !== '/login') {
        navigate('/login', { replace: true });
      }
    }
  }, []);

  const menuItems = [
        {
      key: '/',
      icon: <HomeOutlined />,
      label: '首页',
        },
        {
      key: '/requirement',
      icon: <PlusOutlined />,
      label: '新建行程',
        },
    {
      key: '/itineraries',
      icon: <CalendarOutlined />,
      label: '我的行程',
    },
      ];

  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(key);
};

  const handleLogout = () => {
    dispatch(logout());
    navigate('/');
};

    const userMenuItems = isLoggedIn
    ? [
        {
          key: 'profile',
          icon: <UserOutlined />,
          label: '个人中心',
          onClick: () => navigate('/profile'),
        },
        { type: 'divider' as const },
        {
          key: 'logout',
          icon: <LogoutOutlined />,
          label: '退出登录',
          onClick: handleLogout,
        },
      ]
    : [
        {
          key: 'login',
          icon: <LoginOutlined />,
          label: '登录',
          onClick: () => navigate('/login'),
        },
      ];
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center', padding: '0 24px' }}>
        <div style={{
          color: 'white',
          fontSize: '20px',
          fontWeight: 'bold',
          marginRight: '48px',
          cursor: 'pointer',
        }} onClick={() => navigate('/')}>
          <CompassOutlined /> 旅游行程规划
        </div>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={handleMenuClick}
          style={{ flex: 1, minWidth: 0 }}
        />
        {/* 🔥 新增：用户登录按钮 */}
        <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
          <Button type="text" style={{ color: 'white' }}>
            <UserOutlined />
            {isLoggedIn ? (user?.username || '用户') : '登录'}
          </Button>
        </Dropdown>
      </Header>

      <Content style={{ padding: '0' }}>
        <div
          style={{
            background: colorBgContainer,
            minHeight: 280,
            borderRadius: borderRadiusLG,
          }}
        >
          <Routes>
            {routes.map((route, index) => (
              <Route
                key={index}
                path={route.path}
                element={route.element}
              />
            ))}
          </Routes>
        </div>
      </Content>

      <Footer style={{ textAlign: 'center' }}>
        旅游行程规划系统 ©2026 Created with React + TypeScript
      </Footer>
    </Layout>
  );
};
// 主应用组件，提供BrowserRouter上下文
const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
};

export default App;

