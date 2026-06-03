import apiClient from './api';

export interface HealthStatus {
  status: string;
  timestamp: string;
}

export const healthApi = {
  // 检查服务健康状态
  checkHealth: () => 
    apiClient.get('/health'),
};
