import apiClient from './api';

export interface UserRequirement {
  city_name: string;
  travel_days: number;
  total_budget?: number;
  travel_type?: string;
  travel_date?: string;
  preferences?: string[];
}

export interface RequirementSubmitRequest {
  user_id: string;
  requirement: UserRequirement;
}

export interface Requirement {
  requirement_id?: string;
  city_name: string;
  travel_days: number;
  total_budget: number;
  travel_date: string;
  traveler_count: number;
  preferences: string[];
  travel_type?: string;
  special_needs?: string;
}

export interface StructuredRequirement {
  city_name: string;
  travel_days: number;
  total_budget: number;
  travel_date: string;
  traveler_count: number;
  preferences: string[];
}

// ===== API 通用响应结构，与 api.ts 拦截器 return data 一致 =====
export interface ApiResponse<T = any> {
  code: number;
  msg: string;
  data: T;
}

// ===== submit 接口返回的具体 data 类型 =====
export interface RequirementSubmitData {
  requirement_id: string;
}



export const requirementApi = {
  // 提交需求 — 显式标注返回类型，绕过 Axios 泛型推断
  submit: (data: RequirementSubmitRequest): Promise<ApiResponse<RequirementSubmitData>> =>
    apiClient.post('/requirement/submit', data) as Promise<ApiResponse<RequirementSubmitData>>,

  // 解析需求
  parse: (requirementId: string): Promise<ApiResponse> =>
    apiClient.post('/requirement/parse', { requirement_id: requirementId }) as Promise<ApiResponse>,

  // 获取需求详情
  getById: (id: string): Promise<ApiResponse<Requirement>> =>
    apiClient.get(`/requirement/${id}`) as Promise<ApiResponse<Requirement>>,
};
