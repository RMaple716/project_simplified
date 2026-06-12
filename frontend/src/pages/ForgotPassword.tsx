import React, { useState } from 'react';
import { Form, Input, Button, Typography, message, Result } from 'antd';
import { useNavigate, Link } from 'react-router-dom';
import { authApi } from '../services/authApi';

const { Title } = Typography;

const ForgotPassword: React.FC = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState<'email' | 'reset' | 'done'>('email');
  const [loading, setLoading] = useState(false);
  const [submittedEmail, setSubmittedEmail] = useState('');
  const [resetForm] = Form.useForm();

  // 第一步：发送验证码
  const handleSendCode = async (values: { email: string }) => {
    setLoading(true);
    try {
      const res = await authApi.forgotPassword(values.email);
      if (res.code === 200) {
        setSubmittedEmail(values.email);
        setStep('reset');
        message.success('验证码已发送，请查收邮件');
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '请求失败');
    } finally {
      setLoading(false);
    }
  };

  // 第二步：验证码 + 新密码
  const handleReset = async (values: { code: string; password: string; confirm: string }) => {
    if (values.password !== values.confirm) {
      message.error('两次密码不一致');
      return;
    }

    setLoading(true);
    try {
      const res = await authApi.resetPassword(submittedEmail, values.code, values.password);
      if (res.code === 200) {
        setStep('done');
        message.success('密码重置成功');
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '重置失败');
    } finally {
      setLoading(false);
    }
  };

  // 重新发送验证码
  const handleResendCode = async () => {
    setLoading(true);
    try {
      await authApi.forgotPassword(submittedEmail);
      message.success('验证码已重新发送');
    } catch (error: any) {
      message.error(error.response?.data?.detail || '请求失败');
    } finally {
      setLoading(false);
    }
  };

  // 第三步：完成
  if (step === 'done') {
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

  // 第二步：输入验证码和新密码
  if (step === 'reset') {
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
            重置密码
          </div>
          <div style={{ textAlign: 'center', marginBottom: 24, color: '#5a4a3a', fontSize: 13 }}>
            验证码已发送至 <strong>{submittedEmail}</strong>
          </div>

          <Form form={resetForm} onFinish={handleReset} size="large">
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
                loading={loading}
                style={{ background: '#8a7a70', borderColor: '#8a7a70' }}
              >
                重置密码
              </Button>
            </Form.Item>
            <div style={{ textAlign: 'center', marginBottom: 4 }}>
              <Button
                type="link"
                onClick={handleResendCode}
                disabled={loading}
                style={{ color: '#8a7a70', fontSize: 13, padding: 0 }}
              >
                没收到？重新发送验证码
              </Button>
            </div>
            <div style={{ textAlign: 'center' }}>
              <Button
                type="link"
                onClick={() => { setStep('email'); resetForm.resetFields(); }}
                style={{ color: '#8a7a70', fontSize: 13, padding: 0 }}
              >
                更换邮箱
              </Button>
            </div>
          </Form>
        </div>
      </div>
    );
  }

  // 第一步：输入邮箱
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
        <div style={{ textAlign: 'center', marginBottom: 28, color: '#8a7a70', fontSize: 14 }}>
          忘记密码了？
        </div>

        <Form onFinish={handleSendCode} size="large">
          <Form.Item
            name="email"
            rules={[
              { required: true, message: '请输入注册邮箱' },
              { type: 'email', message: '邮箱格式不正确' },
            ]}
          >
            <Input placeholder="注册邮箱" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 12 }}>
            <Button
              type="primary"
              htmlType="submit"
              block
              loading={loading}
              style={{ background: '#8a7a70', borderColor: '#8a7a70' }}
            >
              发送验证码
            </Button>
          </Form.Item>
          <div style={{ textAlign: 'center' }}>
            <Link to="/login" style={{ color: '#8a7a70', fontSize: 13 }}>
              想起了密码？返回登录
            </Link>
          </div>
        </Form>
      </div>
    </div>
  );
};

export default ForgotPassword;
