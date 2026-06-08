/**
 * 协商可视化 API 服务
 */
import apiClient from './api';
import type { NegotiationEvent } from '../types/negotiation';

export interface NegotiationLogEntry {
  iteration: number;
  day?: number;
  action: string;
  target?: string[];
  type?: string;
  all_resolved?: boolean;
  remaining_conflicts?: number;
}

export interface NegotiationResult {
  applied: boolean;
  iteration_count: number;
  fully_resolved: boolean;
  log: NegotiationLogEntry[];
  events: NegotiationEvent[];
}

/**
 * 从 itinerary day_plans 的 negotiation 字段中提取事件
 */
export function extractEventsFromItinerary(itinerary: any): NegotiationEvent[] {
  try {
    const negotiation = itinerary?.negotiation;
    if (negotiation?.events && Array.isArray(negotiation.events)) {
      return negotiation.events as NegotiationEvent[];
    }
    // 兼容：可能直接放在 day_plans 的元数据中
    if (itinerary?.negotiation_events && Array.isArray(itinerary.negotiation_events)) {
      return itinerary.negotiation_events as NegotiationEvent[];
    }
  } catch (e) {
    console.warn('[协商] 提取事件失败', e);
  }
  return [];
}

export const negotiationApi = {
  /**
   * 获取协商事件日志（通过整合接口）
   */
  getNegotiationEvents: (itineraryId: string): Promise<{ code: number; data: { negotiation_events: NegotiationEvent[] } }> =>
    apiClient.get(`/itinerary/${itineraryId}/negotiation-events`),

  /**
   * 保存协商日志到行程
   */
  saveNegotiationLog: (itineraryId: string, events: NegotiationEvent[]): Promise<{ code: number; msg: string }> =>
    apiClient.post(`/itinerary/${itineraryId}/save-negotiation`, { events }),
};

export default negotiationApi;
