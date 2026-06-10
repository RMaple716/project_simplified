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

/**
 * 智能体提取的响应，比传统正则提取多了preferences和travel_type字段
 */
export interface NLPAgentResponse extends NLPResponse {
  preferences?: string[];
  travel_type?: string;
}

export const nlpApi = {
  /**
   * 从自然语言中提取旅游需求信息（传统正则方式）
   */
  extract: async (data: NLPRequest): Promise<NLPResponse> => {
    const response = await apiClient.post<NLPResponse>('/nlp/extract', data);
    return response.data;
  },

  /**
   * 使用AI智能体从自然语言中提取旅游需求信息（大模型方式）
   *
   * 相比传统正则提取，智能体方式能更好地理解复杂、模糊的自然语言表达，
   * 提取更准确的字段信息。
   *
   * @param text 用户输入的自然语言描述
   * @returns 提取的结构化信息，包含preferences和travel_type等更多字段
   */
  extractByAgent: async (text: string): Promise<NLPAgentResponse> => {
    const response = await apiClient.post<NLPAgentResponse>('/nlp/extract-agent', { text });
    return response.data;
  }
};

