import apiClient from './api';

export interface Task {
  task_id: string;
  requirement_id: string;
  task_type: string;
  status: string;
  progress: number;
  result?: any;
  created_at?: string;
  updated_at?: string;
}

export interface SubTask {
  sub_task_id: string;
  parent_task_id: string;
  agent_type: string;
  status: string;
  result?: any;
}

// 定义后端统一响应结构
export interface ApiResponse<T = any> {
  code: number;
  msg: string;
  data: T;
}

// 任务状态查询返回的 data 结构
export interface TaskStatusData {
  task_id: string;
  status: string;
  progress: number;
  completed: number;
  failed: number;
  total: number;
  message: string;
  itinerary_id?: string;
  /** 后端运行时动态返回的协商事件集合 */
  negotiation_events?: any[];
  /** 后端运行时动态返回的协商信息 */
  negotiation?: {
    events: any[];
    [key: string]: any;
  };
  [key: string]: any; // 允许其他动态字段
}

export const taskApi = {
  // 任务分解
  decompose: (requirementId: string, structuredRequirement: any) => 
    apiClient.post('/task/decompose', {
      requirement_id: requirementId,
      structured_requirement: structuredRequirement,
    }),
  
  // 获取任务状态 — 显式声明返回类型为 ApiResponse<TaskStatusData>
  getById: (taskId: string): Promise<ApiResponse<TaskStatusData>> => 
    apiClient.get(`/task/${taskId}`) as any,
  
  // 更新任务结果
  update: (taskId: string, data: any) => 
    apiClient.post(`/task/update/${taskId}`, data),
};