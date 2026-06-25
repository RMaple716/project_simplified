/**
 * 协商可视化 API 服务（增强版）
 *
 * 【新增功能】
 * 1. ✅ WebSocket 实时事件推送
 * 2. ✅ Agent间消息收发
 * 3. ✅ 重连机制
 * 4. ✅ 事件持久化查询
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

// ==================== WebSocket 连接管理（新增） ====================

export type WSEventCallback = (event: NegotiationEvent) => void;
export type WSStatusCallback = (status: 'connected' | 'disconnected' | 'reconnecting') => void;

export class NegotiationWebSocket {
  private ws: WebSocket | null = null;
  private sessionId: string | null = null;
  private baseUrl: string;
  private eventCallbacks: WSEventCallback[] = [];
  private statusCallbacks: WSStatusCallback[] = [];
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private maxReconnectAttempts = 5;
  private reconnectAttempts = 0;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;

  constructor(baseUrl?: string) {
    // 根据当前环境自动推断 WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = baseUrl || `${protocol}//${window.location.hostname}:9092`;
    this.baseUrl = host;
  }

  /**
   * 连接到协商事件流
   */
  connect(sessionId: string): void {
    this.sessionId = sessionId;
    this.reconnectAttempts = 0;
    this._createConnection();
  }

  /**
   * 断开连接
   */
  disconnect(): void {
    this._cleanup();
  }

  /**
   * 注册事件回调
   */
  onEvent(callback: WSEventCallback): () => void {
    this.eventCallbacks.push(callback);
    return () => {
      this.eventCallbacks = this.eventCallbacks.filter(cb => cb !== callback);
    };
  }

  /**
   * 注册状态回调
   */
  onStatusChange(callback: WSStatusCallback): () => void {
    this.statusCallbacks.push(callback);
    return () => {
      this.statusCallbacks = this.statusCallbacks.filter(cb => cb !== callback);
    };
  }

  /**
   * 动态切换订阅的 session
   */
  subscribeSession(sessionId: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'subscribe',
        session_id: sessionId,
      }));
      this.sessionId = sessionId;
    }
  }

  /**
   * 发送心跳
   */
  ping(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'ping' }));
    }
  }

  // ==================== 私有方法 ====================

  private _createConnection(): void {
    if (this.ws) {
      // 先清除旧的回调再关闭，避免触发重连
      const oldWs = this.ws;
      oldWs.onclose = null;
      oldWs.onerror = null;
      oldWs.onmessage = null;
      oldWs.onopen = null;
      oldWs.close();
      this.ws = null;
    }

    const url = this.sessionId
      ? `${this.baseUrl}/api/v1/ws/negotiation?session_id=${this.sessionId}`
      : `${this.baseUrl}/api/v1/ws/negotiation`;

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        console.log(`[WebSocket] 已连接: session=${this.sessionId}`);
        this.reconnectAttempts = 0;
        this._notifyStatus('connected');
        this._startHeartbeat();
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.eventCallbacks.forEach(cb => cb(data as NegotiationEvent));
        } catch (e) {
          console.warn('[WebSocket] 消息解析失败:', e);
        }
      };

      this.ws.onclose = () => {
        console.log('[WebSocket] 连接已关闭');
        this._stopHeartbeat();
        this._notifyStatus('disconnected');
        this._attemptReconnect();
      };

      this.ws.onerror = (error) => {
        console.warn('[WebSocket] 连接错误:', error);
      };
    } catch (e) {
      console.error('[WebSocket] 创建连接失败:', e);
      this._attemptReconnect();
    }
  }

  private _attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.warn('[WebSocket] 达到最大重连次数，停止重连');
      return;
    }

    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);

    this._notifyStatus('reconnecting');
    console.log(`[WebSocket] 第${this.reconnectAttempts}次重连，${delay}ms后...`);

    this.reconnectTimer = setTimeout(() => {
      this._createConnection();
    }, delay);
  }

  private _startHeartbeat(): void {
    this._stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      this.ping();
    }, 30000); // 每30秒发送一次心跳
  }

  private _stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private _cleanup(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this._stopHeartbeat();
    if (this.ws) {
      // 在 close 之前先把 onclose 置空，避免触发重连
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.onmessage = null;
      this.ws.onopen = null;
      this.ws.close();
      this.ws = null;
    }
    this.reconnectAttempts = this.maxReconnectAttempts; // 阻止自动重连
  }

  private _notifyStatus(status: 'connected' | 'disconnected' | 'reconnecting'): void {
    this.statusCallbacks.forEach(cb => cb(status));
  }

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// ==================== 单例 WebSocket 实例 ====================

let _defaultWS: NegotiationWebSocket | null = null;

export function getDefaultWS(): NegotiationWebSocket {
  if (!_defaultWS) {
    _defaultWS = new NegotiationWebSocket();
  }
  return _defaultWS;
}

// ==================== 事件提取（增强版） ====================

/**
 * 从 itinerary 中提取协商事件
 *
 * 支持多种数据路径（向后兼容）：
 * 1. negotiation.events (标准路径)
 * 2. negotiation_events (旧版路径)
 * 3. day_plans[0].negotiation_events (持久化路径)
 */
export function extractEventsFromItinerary(itinerary: any): NegotiationEvent[] {
  try {
    if (!itinerary) return [];

    // 路径1: negotiation.events
    if (itinerary.negotiation?.events && Array.isArray(itinerary.negotiation.events)) {
      return itinerary.negotiation.events as NegotiationEvent[];
    }

    // 路径2: negotiation_events（从协商服务直接返回）
    if (itinerary.negotiation_events && Array.isArray(itinerary.negotiation_events)) {
      return itinerary.negotiation_events as NegotiationEvent[];
    }

    // 路径3: day_plans[0].negotiation_events（持久化到数据库后的路径）
    if (itinerary.day_plans && Array.isArray(itinerary.day_plans) && itinerary.day_plans.length > 0) {
      const events = itinerary.day_plans[0]?.negotiation_events;
      if (events && Array.isArray(events)) {
        return events as NegotiationEvent[];
      }
    }
  } catch (e) {
    console.warn('[协商] 提取事件失败', e);
  }
  return [];
}

// ==================== API 接口 ====================

export const negotiationApi = {
  /**
   * 获取协商事件日志
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
