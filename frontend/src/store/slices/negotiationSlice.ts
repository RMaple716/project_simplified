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

      // 将事件类型映射到协商阶段
      const eventTypeToPhase: Record<string, NegotiationPhase> = {
        'CFP': 'CFP',
        'PROPOSE': 'BIDDING',
        'COUNTER': 'NEGOTIATE',
        'ACCEPT': 'FINALIZING',
        'REJECT': 'NEGOTIATE',
        'ROLLBACK': 'NEGOTIATE',
        'FINALIZED': 'FINALIZED',
        'AGENT_MSG': 'NEGOTIATE',
        'NEGOTIATION_STARTED': 'NEGOTIATE',
      };
      const phase = event.phase || eventTypeToPhase[event.eventType] || 'NEGOTIATE';
      state.progress.currentPhase = phase;

      // 如果是 FINALIZED 阶段，直接设为 100%
      if (phase === 'FINALIZED') {
        state.progress.overallPercent = 100;
      } else {
        const [minP, maxP] = PHASE_PROGRESS_RANGE[phase] || [40, 80];
        const counterCount = state.events.filter(e => e.eventType === 'COUNTER').length;
        const proposeCount = state.events.filter(e => e.eventType === 'PROPOSE').length;
        const acceptCount = state.events.filter(e => e.eventType === 'ACCEPT').length;
        //const totalEvents = state.events.length;

        // 协商前期（CFP/BIDDING）：基于 PROPOSE 数量
        if (phase === 'CFP' || phase === 'BIDDING') {
          const biddingProgress = Math.min(proposeCount / 5, 1);
          state.progress.overallPercent = Math.round(minP + (maxP - minP) * biddingProgress);
        } else {
          // 协商中（NEGOTIATE/FINALIZING）：基于 COUNTER 次数
          const maxIterations = 5;
          const counterProgress = Math.min(counterCount / maxIterations, 1);
          const acceptBonus = acceptCount > 0 ? 0.3 : 0;
          const progressRatio = Math.min(counterProgress + acceptBonus, 1);
          state.progress.overallPercent = Math.min(Math.round(minP + (maxP - minP) * progressRatio), 99);
        }
      }

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
        // 将事件类型映射到协商阶段 eventType → phase
        const eventTypeToPhase: Record<string, NegotiationPhase> = {
          'CFP': 'CFP',
          'PROPOSE': 'BIDDING',
          'COUNTER': 'NEGOTIATE',
          'ACCEPT': 'FINALIZING',
          'REJECT': 'NEGOTIATE',
          'ROLLBACK': 'NEGOTIATE',
          'FINALIZED': 'FINALIZED',
          'AGENT_MSG': 'NEGOTIATE',
          'NEGOTIATION_STARTED': 'NEGOTIATE',
        };
        const phase = last.phase || eventTypeToPhase[last.eventType] || 'NEGOTIATE';
        state.progress.currentPhase = phase;

        if (phase === 'FINALIZED') {
          state.progress.overallPercent = 100;
        } else {
          const [minP, maxP] = PHASE_PROGRESS_RANGE[phase] || [40, 80];
          // 改进：根据事件类型分布估算进度
          //const totalEvents = action.payload.length;
          const counterCount = action.payload.filter(e => e.eventType === 'COUNTER').length;
          const proposeCount = action.payload.filter(e => e.eventType === 'PROPOSE').length;
          const acceptCount = action.payload.filter(e => e.eventType === 'ACCEPT').length;
          
          // 基于 COUNTER 次数估算迭代进度（0~1）
          const maxIterations = 5;
          const counterProgress = Math.min(counterCount / maxIterations, 1);
          
          // 如果已经有 ACCEPT 事件，说明接近完成
          const acceptBonus = acceptCount > 0 ? 0.3 : 0;
          
          // 如果 PROPOSE 很多但 COUNTER 很少，说明还在 BIDDING 阶段
          const phaseRatio = proposeCount > counterCount * 2 ? 0.3 : counterProgress;
          
          const progressRatio = Math.min(Math.max(phaseRatio, counterProgress) + acceptBonus, 1);
          const phasePercent = minP + (maxP - minP) * progressRatio;
          state.progress.overallPercent = Math.min(Math.round(phasePercent), 99);
        }

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
    case 'ROLLBACK':
      return `策略失败，回退到上一步（${from} → ${to}）`;
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
