/**
 * 自然语言处理相关API
 */
import apiClient from './api';

export interface NLPRequest {
  text: string;
  cities?: string[];
  attractions?: string[];
}

export interface NLPResponse {
  city?: string;
  attraction?: string;
  budget?: number;
  transport?: string;
  depart_time?: string;
  people?: number;
  travel_days?: number;  // ✅ 新增出行天数字段
}

export const nlpApi = {
  /**
   * 从自然语言中提取旅游需求信息
   */
  extract: async (data: NLPRequest): Promise<NLPResponse> => {
    const response = await apiClient.post<NLPResponse>('/nlp/extract', data);
    return response.data;
  }
};
