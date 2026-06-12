import React, { useState, useEffect } from 'react';
import { Form, Input, Button, Typography, message, Result, Spin } from 'antd';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { authApi } from '../services/authApi';

const { Title } = Typography;

const ResetPassword: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';

  const [verifying, setVerifying] = useState(true);
  const [tokenValid, setTokenValid] = useState(false);
  const [username, setUsername] = useState('');
  const [resetting, setResetting] = useState(false);
  const [done, setDone] = useState(false);

  // 页面加载时验证令牌
  useEffect(() => {
    if (!token) {
      setVerifying(false);
      setTokenValid(false);
      return;
    }

    authApi.verifyResetToken(token)
      .then((res) => {
        if (res.code === 200 && res.data?.valid) {
          setTokenValid(true);
          setUsername(res.data.username || '');
        } else {
          setTokenValid(false);
        }
      })
      .catch(() => {
        setTokenValid(false);
      })
      .finally(() => {
        setVerifying(false);
      });
  }, [token]);

  const handleReset = async (values: { password: string; confirm: string }) => {
    if (values.password !== values.confirm) {
      message.error('两次密码不一致');
      return;
    }

    setResetting(true);
    try {
      const res = await authApi.resetPassword(token, values.password);
      if (res.code === 200) {
        setDone(true);
        message.success('密码重置成功');
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '重置失败');
    } finally {
      setResetting(false);
    }
  };

  // 验证中
  if (verifying) {
    return (
      <div style={{
        display: 'flex', justifyContent: 'center', alignItems: 'center',
        minHeight: 'calc(100vh - 134px)', background: '#f7f3ee',
      }}>
        <Spin size="large" tip="验证中..." />
      </div>
    );
  }

  // 令牌无效
  if (!tokenValid) {
    return (
      <div style={{
        display: 'flex', justifyContent: 'center', alignItems: 'center',
        minHeight: 'calc(100vh - 134px)', padding: 24,
        background: '#f7f3ee',
      }}>
        <div style={{
          width: 420,
          border: '1px solid #e0d8ce',
          background: '#faf7f2',
          padding: '36px 32px 28px',
          textAlign: 'center',
        }}>
          <Title level={3} style={{
            fontFamily: "'Cormorant Garamond', Georgia, serif",
            fontSize: '1.8rem', letterSpacing: '2px', fontWeight: 600,
            marginBottom: 20,
          }}>
            旅途手账
          </Title>
          <Result
            status="warning"
            title="链接无效或已过期"
            subTitle={
              <div style={{ color: '#5a4a3a', fontSize: 14, lineHeight: 1.8 }}>
                <p>该重置链接可能已使用、已过期，或不正确。</p>
                <p style={{ fontSize: 13, color: '#8a7a70', marginTop: 8 }}>
                  请重新请求密码重置。
                </p>
              </div>
            }
          />
          <div style={{ marginTop: 16 }}>
            <Button
              type="primary"
              style={{ background: '#8a7a70', borderColor: '#8a7a70' }}
              onClick={() => navigate('/forgot-password')}
            >
              重新请求
            </Button>
            <Button
              style={{ marginLeft: 12, color: '#8a7a70', borderColor: '#d0c8be' }}
              onClick={() => navigate('/login')}
            >
              返回登录
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // 重置成功
  if (done) {
    return (
      <div style={{
        display: 'flex', justifyContent: 'center', alignItems: 'center',
        minHeight: 'calc(100vh - 134px)', padding: 24,
        background: '#f7f3ee',
      }}>
        <div style={{
          width: 420,
          border: '1px solid #e0d8ce',
          background: '#faf7f2',
          padding: '36px 32px 28px',
          textAlign: 'center',
        }}>
          <Title level={3} style={{
            fontFamily: "'Cormorant Garamond', Georgia, serif",
            fontSize: '1.8rem', letterSpacing: '2px', fontWeight: 600,
            marginBottom: 20,
          }}>
            旅途手账
          </Title>
          <Result
            status="success"
            title="密码重置成功"
            subTitle={
              <div style={{ color: '#5a4a3a', fontSize: 14 }}>
                请使用新密码登录。
              </div>
            }
          />
          <div style={{ marginTop: 16 }}>
            <Button
              type="primary"
              style={{ background: '#8a7a70', borderColor: '#8a7a70' }}
              onClick={() => navigate('/login')}
            >
              前往登录
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // 正常重置表单
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
        <Title level={3} style={{
          textAlign: 'center', marginBottom: 8,
          fontFamily: "'Cormorant Garamond', Georgia, serif",
          fontSize: '1.8rem', letterSpacing: '2px', fontWeight: 600,
        }}>
          旅途手账
        </Title>
        <div style={{ textAlign: 'center', marginBottom: 8, color: '#8a7a70', fontSize: 14 }}>
          设置新密码
        </div>
        {username && (
          <div style={{ textAlign: 'center', marginBottom: 24, color: '#5a4a3a', fontSize: 13 }}>
            用户：{username}
          </div>
        )}

        <Form onFinish={handleReset} size="large">
          <Form.Item
            name="password"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 6, message: '密码至少 6 位' },
            ]}
          >
            <Input.Password placeholder="新密码" />
          </Form.Item>
          <Form.Item
            name="confirm"
            rules={[
              { required: true, message: '请确认新密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) return Promise.resolve();
                  return Promise.reject(new Error('两次密码不一致'));
                },
              }),
            ]}
          >
            <Input.Password placeholder="确认新密码" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 12 }}>
            <Button
              type="primary"
              htmlType="submit"
              block
              loading={resetting}
              style={{ background: '#8a7a70', borderColor: '#8a7a70' }}
            >
              重置密码
            </Button>
          </Form.Item>
        </Form>
      </div>
    </div>
  );
};

export default ResetPassword;
