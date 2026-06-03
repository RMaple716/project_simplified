import apiClient from './api';

// 智能体结果类型
export interface AgentResults {
  attraction?: {
    attractions: any[];
  };
  accommodation?: {
    hotels: any[];
  };
  food?: {
    restaurants: any[];
  };
  transport?: {
    transport_options: any[];
  };
}

// 行程整合请求
export interface CombineRequest {
  task_id: string;
  agent_results: AgentResults;
  structured_requirement: {
    city_name: string;
    travel_days: number;
    total_budget: number;
    travel_date: string;
    traveler_count: number;
    preferences?: string[];
  };
}

// 行程整合响应
export interface CombineResponse {
  task_id: string;
  day_plans: any[];
  validation: {
    valid: boolean;
    conflicts: any[];
    suggestions: string[];
  };
  total_cost: number;
}

// 路线优化请求
export interface OptimizeRouteRequest {
  attractions: Array<{
    name: string;
    location: {
      lat: number;
      lng: number;
    };
  }>;
}

// 路线优化响应
export interface OptimizeRouteResponse {
  optimized_attractions: Array<{
    name: string;
    location: {
      lat: number;
      lng: number;
    };
  }>;
}

export const integrationApi = {
  // 行程整合（核心功能）- 将各智能体的输出拼接为每日行程，并自动进行校验
  combine: (data: CombineRequest) => 
    apiClient.post('/integration/combine', data),
  
  // 路线优化 - 对给定景点列表进行路径优化，减少折返
  optimizeRoute: (data: OptimizeRouteRequest) => 
    apiClient.post('/integration/optimize-route', data),
};
