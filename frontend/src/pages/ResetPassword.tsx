import React, { useState } from 'react';
import { Form, Input, Button, Typography, message, Result } from 'antd';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { authApi } from '../services/authApi';

const { Title } = Typography;

const ResetPassword: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const codeFromUrl = searchParams.get('code') || searchParams.get('token') || '';

  const [resetting, setResetting] = useState(false);
  const [done, setDone] = useState(false);

  const handleReset = async (values: { email: string; code: string; password: string; confirm: string }) => {
    if (values.password !== values.confirm) {
      message.error('两次密码不一致');
      return;
    }

    const code = codeFromUrl || values.code;

    setResetting(true);
    try {
      const res = await authApi.resetPassword(values.email, code, values.password);
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
        {codeFromUrl ? (
          <div style={{ textAlign: 'center', marginBottom: 24, color: '#5a4a3a', fontSize: 13 }}>
            验证码已获取，请输入您的邮箱和新密码
          </div>
        ) : (
          <div style={{ textAlign: 'center', marginBottom: 24, color: '#8a7a70', fontSize: 13 }}>
            请输入邮箱、验证码和新密码
          </div>
        )}

        <Form onFinish={handleReset} size="large">
          <Form.Item
            name="email"
            rules={[
              { required: true, message: '请输入注册邮箱' },
              { type: 'email', message: '邮箱格式不正确' },
            ]}
          >
            <Input placeholder="注册邮箱" />
          </Form.Item>
          {!codeFromUrl && (
            <Form.Item
              name="code"
              rules={[
                { required: true, message: '请输入验证码' },
                { len: 6, message: '验证码为6位数字' },
              ]}
            >
              <Input
                placeholder="6位验证码"
                maxLength={6}
                style={{ letterSpacing: 4, fontSize: 18, textAlign: 'center' }}
              />
            </Form.Item>
          )}
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
