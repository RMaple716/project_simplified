import React, { useState } from 'react';
import { Form, Input, Button, Typography, message, Tabs } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useDispatch } from 'react-redux';
import { authApi } from '../services/authApi';
import { loginSuccess } from '../store/slices/authSlice';

const { Title } = Typography;

const Login: React.FC = () => {
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('login');

  const handleLogin = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const res = await authApi.login(values.username, values.password);
      if (res.code === 200) {
        localStorage.setItem('token', res.data.access_token);
        localStorage.setItem('user_id', res.data.user_id);
        localStorage.setItem('username', res.data.username);
        localStorage.setItem('email', res.data.email || '');
        dispatch(loginSuccess({
          token: res.data.access_token,
          user_id: res.data.user_id,
          username: res.data.username,
        }));
        message.success('登录成功');
        navigate('/');
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '登录失败');
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (values: { username: string; email: string; password: string; confirm: string }) => {
    if (values.password !== values.confirm) {
      message.error('两次密码不一致');
      return;
    }
    setLoading(true);
    try {
      const res = await authApi.register(values.username, values.email, values.password);
      if (res.code === 200) {
        localStorage.setItem('token', res.data.access_token);
        localStorage.setItem('user_id', res.data.user_id);
        localStorage.setItem('username', res.data.username);
        localStorage.setItem('email', res.data.email || '');
        dispatch(loginSuccess({
          token: res.data.access_token,
          user_id: res.data.user_id,
          username: res.data.username,
        }));
        message.success('注册成功');
        navigate('/');
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '注册失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      display: 'flex', justifyContent: 'center', alignItems: 'center',
      minHeight: 'calc(100vh - 134px)', padding: 24,
      background: '#f7f3ee',
    }}>
      <div style={{
        width: 400,
        border: '1px solid #e0d8ce',
        background: '#faf7f2',
        padding: '36px 32px 28px',
      }}>
        {/* 【去AI味】标题不用"系统"二字，改为手写感衬线体 */}
        <Title level={3} style={{
          textAlign: 'center',
          marginBottom: 16,
          fontFamily: "'Cormorant Garamond', Georgia, serif",
          fontSize: '1.8rem',
          letterSpacing: '2px',
          fontWeight: 600,
        }}>
          旅途手账
        </Title>
        <div style={{ textAlign: 'center', marginBottom: 28, color: '#8a7a70', fontSize: 14 }}>
          {activeTab === 'login' ? '回来啦？' : '新朋友，欢迎'}
        </div>

        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          centered
          size="small"
          items={[
            {
              key: 'login',
              label: '登录',
              children: (
                <Form onFinish={handleLogin} size="large">
                  <Form.Item name="username" rules={[{ required: true, message: '请输入用户名或邮箱' }]}>
                    <Input placeholder="用户名或邮箱" />
                  </Form.Item>
                  <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
                    <Input.Password placeholder="密码" />
                  </Form.Item>
                  <Form.Item style={{ marginBottom: 0 }}>
                    <Button type="primary" htmlType="submit" block loading={loading}>
                      登录
                    </Button>
                  </Form.Item>
                </Form>
              ),
            },
            {
              key: 'register',
              label: '注册',
              children: (
                <Form onFinish={handleRegister} size="large">
                  <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
                    <Input placeholder="用户名" />
                  </Form.Item>
                  <Form.Item name="email" rules={[
                    { required: true, message: '请输入邮箱' },
                    { type: 'email', message: '邮箱格式不正确' },
                  ]}>
                    <Input placeholder="邮箱" />
                  </Form.Item>
                  <Form.Item name="password" rules={[
                    { required: true, message: '请输入密码' },
                    { min: 6, message: '密码至少6位' },
                  ]}>
                    <Input.Password placeholder="密码" />
                  </Form.Item>
                  <Form.Item name="confirm" rules={[
                    { required: true, message: '请确认密码' },
                    ({ getFieldValue }) => ({
                      validator(_, value) {
                        if (!value || getFieldValue('password') === value) return Promise.resolve();
                        return Promise.reject(new Error('两次密码不一致'));
                      },
                    }),
                  ]}>
                    <Input.Password placeholder="确认密码" />
                  </Form.Item>
                  <Form.Item style={{ marginBottom: 0 }}>
                    <Button type="primary" htmlType="submit" block loading={loading}>
                      注册
                    </Button>
                  </Form.Item>
                </Form>
              ),
            },
          ]}
        />
      </div>
    </div>
  );
};

export default Login;