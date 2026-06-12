import apiClient from './api';

export interface LoginResponse {
  code: number;
  msg: string;
  data: {
    access_token: string;
    token_type: string;
    user_id: string;
    username: string;
    email?: string;
  };
}

export interface UserInfoResponse {
  code: number;
  msg: string;
  data: {
    user_id: string;
    username: string;
    email: string;
    avatar: string | null;
    created_at: string;
  };
}

export interface ForgotPasswordResponse {
  code: number;
  msg: string;
  data: null;
}

export interface ResetPasswordResponse {
  code: number;
  msg: string;
  data: null;
}

export const authApi = {
  /** 用户登录 */
  login: async (username: string, password: string): Promise<LoginResponse> => {
    return apiClient.post('/auth/login', { username, password });
  },

  /** 用户注册 */
  register: async (username: string, email: string, password: string): Promise<LoginResponse> => {
    return apiClient.post('/auth/register', { username, email, password });
  },

  /** 获取当前用户信息 */
  getCurrentUser: async (): Promise<UserInfoResponse> => {
    return apiClient.get('/auth/me');
  },

  /** 请求密码重置（发送验证码邮件） */
  forgotPassword: async (email: string): Promise<ForgotPasswordResponse> => {
    return apiClient.post('/auth/forgot-password', { email });
  },

  /** 使用验证码重置密码 */
  resetPassword: async (email: string, code: string, newPassword: string): Promise<ResetPasswordResponse> => {
    return apiClient.post('/auth/reset-password', { email, code, new_password: newPassword });
  },
};