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
};