/**
 * 协商可视化相关类型定义（增强版）
 *
 * 【新增内容】
 * - AGENT_MSG 事件类型（Agent间通信）
 * - AgentMessage 类型定义
 * - WebSocket 连接状态
 * - 消息类型枚举
 */

// ==================== 事件类型 ====================

/** 协商事件类型 */
export type NegotiationEventType =
  | 'CFP'             // 招标
  | 'PROPOSE'         // 投标/提案
  | 'COUNTER'         // 反提案
  | 'ACCEPT'          // 接受
  | 'REJECT'          // 拒绝
  | 'ROLLBACK'        // 回退到上一步（策略失败后回滚）
  | 'FINALIZED'       // 最终确定
  | 'AGENT_MSG'       // Agent间消息
  // === 任务执行进度事件（WebSocket实时推送） ===
  | 'TASK_STARTED'                // 批次任务开始
  | 'SUB_TASK_STARTED'            // 子任务开始执行
  | 'SUB_TASK_COMPLETED'          // 子任务完成
  | 'SUB_TASK_FAILED'             // 子任务失败
  | 'NEGOTIATION_STARTED'         // 协商开始
  | 'ITINERARY_CREATED';          // 行程已创建

/** 协商阶段 */
export type NegotiationPhase =
  | 'INIT'
  | 'CFP'
  | 'BIDDING'
  | 'NEGOTIATE'
  | 'FINALIZING'
  | 'FINALIZED'
  | 'EXECUTING';     // 子任务执行中（新增）

// ==================== Agent间消息类型（新增） ====================

/** Agent消息类型枚举 */
export const AgentMessageType = {
  COORDINATE_REQUEST: 'coordinate_request',
  COORDINATE_RESPONSE: 'coordinate_response',
  SCHEDULE_PROPOSAL: 'schedule_proposal',
  SCHEDULE_FEEDBACK: 'schedule_feedback',
  LOCATION_SHARE: 'location_share',
  CONSTRAINT_NOTIFY: 'constraint_notify',
  PREFERENCE_QUERY: 'preference_query',
  PREFERENCE_RESPONSE: 'preference_response',
} as const;

export type AgentMessageTypeEnum = typeof AgentMessageType[keyof typeof AgentMessageType];

/** Agent间消息结构 */
export interface AgentMessage {
  messageId: string;
  sessionId: string;
  timestamp: number;
  fromAgent: string;
  toAgent: string;
  type: AgentMessageTypeEnum;
  payload: any;
  metadata: Record<string, any>;
}

// ==================== WebSocket 状态（新增） ====================

/** WebSocket 连接状态 */
export type WSConnectionStatus = 'connected' | 'disconnected' | 'reconnecting';

/** WebSocket 事件回调类型 */
export type WSEventHandler = (event: NegotiationEvent) => void;
export type WSStatusHandler = (status: WSConnectionStatus) => void;

// ==================== 数据结构 ====================

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
  /** 【新增】如果是AGENT_MSG类型，携带消息类型 */
  agentMsgType?: AgentMessageTypeEnum;
  [key: string]: any;
}

/** 当前进度状态（用于UI展示） */
export interface NegotiationProgress {
  overallPercent: number;
  currentPhase: NegotiationPhase;
  activeAgents: string[];
  latestSummary: string;
}

// ==================== 中文映射 ====================

/** 协商阶段到中文描述的映射 */
export const PHASE_MAP_CN: Record<NegotiationPhase, string> = {
  INIT: '初始化',
  CFP: '任务招标',
  BIDDING: '接收投标',
  NEGOTIATE: '协商中',
  FINALIZING: '确认路线',
  FINALIZED: '规划完成',
  EXECUTING: '子任务执行中',
};

/** 协商事件类型到中文描述的映射 */
export const EVENT_TYPE_CN: Record<NegotiationEventType, string> = {
  CFP: '发布招标',
  PROPOSE: '提交提案',
  COUNTER: '反提案',
  ACCEPT: '接受协议',
  REJECT: '拒绝',
  ROLLBACK: '回退',
  FINALIZED: '最终确定',
  AGENT_MSG: 'Agent通信',
  TASK_STARTED: '任务开始',
  SUB_TASK_STARTED: '子任务开始',
  SUB_TASK_COMPLETED: '子任务完成',
  SUB_TASK_FAILED: '子任务失败',
  NEGOTIATION_STARTED: '协商开始',
  ITINERARY_CREATED: '行程已创建',
};

/** Agent消息类型到中文描述的映射 */
export const AGENT_MSG_TYPE_CN: Record<string, string> = {
  coordinate_request: '协调请求',
  coordinate_response: '协调响应',
  schedule_proposal: '时间建议',
  schedule_feedback: '时间反馈',
  location_share: '位置共享',
  constraint_notify: '约束通知',
  preference_query: '偏好查询',
  preference_response: '偏好响应',
};

/** 阶段对应进度百分比范围 */
export const PHASE_PROGRESS_RANGE: Record<NegotiationPhase, [number, number]> = {
  INIT: [0, 0],
  CFP: [0, 20],
  BIDDING: [20, 40],
  NEGOTIATE: [40, 80],
  FINALIZING: [80, 98],
  FINALIZED: [100, 100],
  EXECUTING: [0, 80],
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

