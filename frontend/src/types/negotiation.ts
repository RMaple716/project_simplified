/**
 * 协商可视化相关类型定义
 *
 * 对应后端 NegotiationEventBus 的事件结构
 */

/** 协商事件类型 */
export type NegotiationEventType =
  | 'CFP'          // 招标
  | 'PROPOSE'      // 投标/提案
  | 'COUNTER'      // 反提案
  | 'ACCEPT'       // 接受
  | 'REJECT'       // 拒绝
  | 'FINALIZED';   // 最终确定

/** 协商阶段 */
export type NegotiationPhase =
  | 'INIT'
  | 'CFP'
  | 'BIDDING'
  | 'NEGOTIATE'
  | 'FINALIZING'
  | 'FINALIZED';

/** 路线预览 */
export interface RoutePreview {
  vehicleId: string;
  coordinates: [number, number][]; // [lng, lat][]
  color?: string;
  opacity?: number;
  dashArray?: string;
}

/** 提案内容 */
export interface Proposal {
  price?: number;
  eta?: string;
  extraStops?: number;
  [key: string]: any;
}

/** 效用值 */
export interface Utility {
  dispatcher?: number;
  vehicle?: number;
  [key: string]: number | undefined;
}

/** 单个协商事件 */
export interface NegotiationEvent {
  eventId: string;
  sessionId: string;
  timestamp: number;          // Unix milliseconds
  eventType: NegotiationEventType;
  fromAgent: string;
  toAgent: string;
  phase: NegotiationPhase;
  proposal: Proposal;
  utility: Utility;
  routePreview: RoutePreview;
  adjustments?: AdjustmentDetail[]; 
  [key: string]: any;
}

/** 当前进度状态（用于UI展示） */
export interface NegotiationProgress {
  overallPercent: number;
  currentPhase: NegotiationPhase;
  activeAgents: string[];
  latestSummary: string;
}

/** 协商阶段到中文描述的映射 */
export const PHASE_MAP_CN: Record<NegotiationPhase, string> = {
  INIT: '初始化',
  CFP: '任务招标',
  BIDDING: '接收投标',
  NEGOTIATE: '协商中',
  FINALIZING: '确认路线',
  FINALIZED: '规划完成',
};

/** 协商事件类型到中文描述的映射 */
export const EVENT_TYPE_CN: Record<NegotiationEventType, string> = {
  CFP: '发布招标',
  PROPOSE: '提交提案',
  COUNTER: '反提案',
  ACCEPT: '接受协议',
  REJECT: '拒绝',
  FINALIZED: '最终确定',
};

/** 阶段对应进度百分比范围 */
export const PHASE_PROGRESS_RANGE: Record<NegotiationPhase, [number, number]> = {
  INIT: [0, 0],
  CFP: [0, 20],
  BIDDING: [20, 40],
  NEGOTIATE: [40, 80],
  FINALIZING: [80, 95],
  FINALIZED: [95, 100],
};

/** 单次调整详情（字段级变化） */
export interface AdjustmentDetail {
  /** 被调整的字段名称，如"游览时间"、"游览时长"、"用餐时间" */
  field: string;
  /** 被调整的项目名称，如"故宫博物院" */
  item_name: string;
  /** 调整前的值 */
  before: string;
  /** 调整后的值 */
  after: string;
  /** 采用的策略名称，如"时间平移"、"时段交换" */
  strategy: string;
}
