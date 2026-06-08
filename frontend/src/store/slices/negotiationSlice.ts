/**
 * 协商可视化状态管理
 */
import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type {
  NegotiationEvent,
  NegotiationPhase,
  NegotiationProgress,
} from '../../types/negotiation';
import { PHASE_PROGRESS_RANGE } from '../../types/negotiation';

export interface NegotiationState {
  /** 当前进度 */
  progress: NegotiationProgress;
  /** 事件历史 */
  events: NegotiationEvent[];
  /** 是否正在回放 */
  isReplaying: boolean;
  /** 回放当前索引 */
  replayIndex: number;
  /** 回放速度倍率 */
  replaySpeed: number;
}

const initialState: NegotiationState = {
  progress: {
    overallPercent: 0,
    currentPhase: 'INIT',
    activeAgents: [],
    latestSummary: '初始化...',
  },
  events: [],
  isReplaying: false,
  replayIndex: -1,
  replaySpeed: 1,
};

const negotiationSlice = createSlice({
  name: 'negotiation',
  initialState,
  reducers: {
    /** 收到新的事件 */
    addEvent(state, action: PayloadAction<NegotiationEvent>) {
      const event = action.payload;
      state.events.push(event);

      // 更新进度状态
      const phase = event.phase;
      state.progress.currentPhase = phase;
      const [minP, maxP] = PHASE_PROGRESS_RANGE[phase] || [0, 100];
      // 根据事件在阶段内的序号估算百分比
      const phaseEvents = state.events.filter(e => e.phase === phase);
      const idx = phaseEvents.length;
      const totalEstimate = Math.max(phaseEvents.length + 2, 5);
      const phasePercent = minP + (maxP - minP) * Math.min(idx / totalEstimate, 1);
      state.progress.overallPercent = Math.round(phasePercent);

      // 更新活跃参与方
      const agents = new Set<string>();
      agents.add(event.fromAgent);
      agents.add(event.toAgent);
      if (event.toAgent !== 'all_vehicles') {
        agents.add(event.toAgent);
      }
      state.progress.activeAgents = Array.from(agents);

      // 更新摘要
      const summary = generateSummary(event);
      state.progress.latestSummary = summary;
    },

    /** 批量设置事件（从加载的数据恢复） */
    setEvents(state, action: PayloadAction<NegotiationEvent[]>) {
      state.events = action.payload;
      if (action.payload.length > 0) {
        const last = action.payload[action.payload.length - 1];
        // 根据最后一个事件推断当前阶段
        const phase = last.phase || last.eventType as NegotiationPhase;
        state.progress.currentPhase = phase;

        // 根据阶段计算进度百分比范围
        const [minP, maxP] = PHASE_PROGRESS_RANGE[phase] || [0, 100];
        const phaseEvents = action.payload.filter(e => (e.phase || e.eventType) === phase);
        const phaseIndex = phaseEvents.length;
        const phasePercent = minP + (maxP - minP) * Math.min(phaseIndex / Math.max(phaseEvents.length, 5), 1);
        state.progress.overallPercent = Math.min(Math.round(phasePercent), 100);

        // 用最后一个事件生成摘要
        state.progress.latestSummary = generateSummary(last);

        // 收集所有参与方
        const agents = new Set<string>();
        action.payload.forEach(e => {
          if (e.fromAgent) agents.add(e.fromAgent);
          if (e.toAgent) agents.add(e.toAgent);
        });
        state.progress.activeAgents = Array.from(agents);
      }
    },

    /** 重置状态 */
    resetNegotiation(state) {
      state.events = [];
      state.progress = initialState.progress;
      state.isReplaying = false;
      state.replayIndex = -1;
    },

    /** 开始回放 */
    startReplay(state) {
      state.isReplaying = true;
      state.replayIndex = 0;
    },

    /** 停止回放 */
    stopReplay(state) {
      state.isReplaying = false;
      state.replayIndex = -1;
    },

    /** 回放跳转到指定索引 */
    seekReplay(state, action: PayloadAction<number>) {
      state.replayIndex = Math.max(0, Math.min(action.payload, state.events.length - 1));
    },

    /** 回放前进一个事件 */
    nextReplayEvent(state) {
      if (state.replayIndex < state.events.length - 1) {
        state.replayIndex += 1;
      } else {
        state.isReplaying = false;
      }
    },

    /** 设置回放速度 */
    setReplaySpeed(state, action: PayloadAction<number>) {
      state.replaySpeed = action.payload;
    },

    /** 设置进度百分比（外部驱动时使用） */
    setProgressPercent(state, action: PayloadAction<number>) {
      state.progress.overallPercent = action.payload;
    },

    /** 设置阶段 */
    setPhase(state, action: PayloadAction<NegotiationPhase>) {
      state.progress.currentPhase = action.payload;
    },
  },
});

/** 根据事件类型生成中文摘要 */
function generateSummary(event: NegotiationEvent): string {
  const type = event.eventType;
  const from = event.fromAgent;
  const to = event.toAgent;
  const proposal = event.proposal || {};

  switch (type) {
    case 'CFP':
      return `正在生成任务招标...`;
    case 'PROPOSE':
      if (proposal.action) {
        return `尝试${proposal.action}方案...`;
      }
      return `${from} 向 ${to} 提交提案`;
    case 'COUNTER':
      if (proposal.action) {
        return `执行${proposal.action}修复...`;
      }
      return `${from} 向 ${to} 提出反提案`;
    case 'ACCEPT':
      return '达成协议，路线确认中...';
    case 'REJECT':
      return '协商未能达成一致';
    case 'FINALIZED':
      return '规划完成！';
    default:
      return '处理中...';
  }
}

export const {
  addEvent,
  setEvents,
  resetNegotiation,
  startReplay,
  stopReplay,
  seekReplay,
  nextReplayEvent,
  setReplaySpeed,
  setProgressPercent,
  setPhase,
} = negotiationSlice.actions;

export default negotiationSlice.reducer;
