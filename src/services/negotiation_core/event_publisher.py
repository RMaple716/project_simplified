"""
事件发布封装模块

将 event_bus.publish() 的调用抽离为独立模块。
提供高层 API，统一事件发布格式，不再在主协调器中混入事件构建逻辑。
"""

import logging
from typing import Dict, Any, List, Optional

from src.services.negotiation_event_bus import (
    event_bus,
    create_negotiation_event,
    NegotiationEventType,
    NegotiationPhase,
    build_route_preview,
)

logger = logging.getLogger(__name__)


class NegotiationEventPublisher:
    """
    协商事件发布器（单例）

    封装所有事件发布逻辑，确保格式统一。
    主协调器只需调用 publish_xxx() 方法，无需关心事件结构细节。
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        # 是否启用 fire-and-forget（异步非阻塞）
        self.fire_and_forget = False
        logger.info("[事件发布器] 初始化完成")

    async def publish_cfp(
        self,
        session_id: str,
        max_iterations: int,
        total_days: int,
        total_attractions: int,
    ) -> None:
        """发布协商开始 (CFP) 事件"""
        event = create_negotiation_event(
            event_type=NegotiationEventType.CFP,
            session_id=session_id,
            from_agent="dispatcher",
            to_agent="all_vehicles",
            phase=NegotiationPhase.CFP,
            proposal={
                "description": f"开始协商修复行程冲突（共{max_iterations}轮）",
                "total_days": total_days,
                "total_attractions": total_attractions,
            },
            utility={"dispatcher": 1.0, "vehicle": 1.0},
        )
        await self._publish(session_id, event)

    async def publish_propose(
        self,
        session_id: str,
        day_num: int,
        iteration: int,
        conflict_type: str,
        conflict_description: str,
    ) -> None:
        """发布尝试修复 (PROPOSE) 事件"""
        event = create_negotiation_event(
            event_type=NegotiationEventType.PROPOSE,
            session_id=session_id,
            from_agent="dispatcher",
            to_agent=f"day_{day_num}",
            phase=NegotiationPhase.NEGOTIATE,
            proposal={
                "conflict_type": conflict_type,
                "conflict_description": conflict_description,
                "iteration": iteration,
                "day": day_num,
            },
            utility={"dispatcher": max(0.8 - iteration * 0.1, 0.3)},
            route_preview=build_route_preview(
                vehicle_id=f"day{day_num}",
                coordinates=[],
            ),
        )
        await self._publish(session_id, event)

    async def publish_counter(
        self,
        session_id: str,
        strategy_name: str,
        conflict_activities: List[str],
        adjustments: List[dict],
        target_agent: str = "all_vehicles",
        day_num: Optional[int] = None,
    ) -> None:
        """发布策略执行成功 (COUNTER) 事件"""
        event = create_negotiation_event(
            event_type=NegotiationEventType.COUNTER,
            session_id=session_id,
            from_agent="dispatcher",
            to_agent=target_agent,
            phase=NegotiationPhase.NEGOTIATE,
            proposal={
                "action": strategy_name,
                "target": conflict_activities,
                "adjustments": adjustments,
            },
            utility={"dispatcher": 0.6, "vehicle": 0.5},
            route_preview=build_route_preview(
                vehicle_id=f"day{day_num}" if day_num else "all",
                coordinates=[],
            ),
        )
        await self._publish(session_id, event)

    async def publish_accept(
        self,
        session_id: str,
        final_conflicts: int,
    ) -> None:
        """发布接受 (ACCEPT) 事件"""
        event = create_negotiation_event(
            event_type=NegotiationEventType.ACCEPT,
            session_id=session_id,
            from_agent="dispatcher",
            to_agent="all_vehicles",
            phase=NegotiationPhase.FINALIZING,
            proposal={"final_conflicts": final_conflicts},
            utility={"dispatcher": 0.95, "vehicle": 0.95},
        )
        await self._publish(session_id, event)

    async def publish_finalized(
        self,
        session_id: str,
        iteration_count: int,
        fully_resolved: bool,
        final_conflicts: int,
        long_distance_warnings: Optional[List[dict]] = None,
        utility: Optional[Dict[str, float]] = None,
    ) -> None:
        """发布最终确定 (FINALIZED) 事件"""
        extra = {}
        if long_distance_warnings:
            extra["longDistanceWarning"] = True
        
        event = create_negotiation_event(
            event_type=NegotiationEventType.FINALIZED,
            session_id=session_id,
            from_agent="dispatcher",
            to_agent="all_vehicles",
            phase=NegotiationPhase.FINALIZED,
            proposal={
                "iteration_count": iteration_count,
                "fully_resolved": fully_resolved,
                "final_conflicts": final_conflicts,
                "long_distance_warnings": long_distance_warnings or [],
            },
            utility=utility or {"dispatcher": 1.0, "vehicle": 1.0},
            extra=extra,
        )
        await self._publish(session_id, event)

    async def publish_reject(
        self,
        session_id: str,
        reason: str,
    ) -> None:
        """发布拒绝 (REJECT) 事件"""
        event = create_negotiation_event(
            event_type=NegotiationEventType.REJECT,
            session_id=session_id,
            from_agent="dispatcher",
            to_agent="all_vehicles",
            phase=NegotiationPhase.FINALIZING,
            proposal={"reason": reason},
            utility={"dispatcher": 0.3, "vehicle": 0.3},
        )
        await self._publish(session_id, event)

    async def publish_global_reshuffle(
        self,
        session_id: str,
    ) -> None:
        """发布全局重排事件"""
        event = create_negotiation_event(
            event_type=NegotiationEventType.COUNTER,
            session_id=session_id,
            from_agent="dispatcher",
            to_agent="all_vehicles",
            phase=NegotiationPhase.NEGOTIATE,
            proposal={"action": "全局重排（按地理聚类重新分配）"},
            utility={"dispatcher": 0.35, "vehicle": 0.35},
        )
        await self._publish(session_id, event)

    # ==================== 【第四阶段】新增：发布单轮协商进度 ====================

    async def publish_round_progress(
        self,
        session_id: str,
        iteration: int,
        max_iterations: int,
        current_utility: float,
        remaining_conflicts: int,
        fixes_this_round: int,
    ) -> None:
        """
        发布单轮协商进度事件

        【第四阶段】新增方法，用于 WebSocket 实时推送每轮协商的进度。

        Args:
            session_id: 会话ID
            iteration: 当前轮次（0-based）
            max_iterations: 最大迭代轮数
            current_utility: 当前效用值
            remaining_conflicts: 剩余冲突数
            fixes_this_round: 本轮修复数
        """
        event = create_negotiation_event(
            event_type=NegotiationEventType.PROPOSE,
            session_id=session_id,
            from_agent="dispatcher",
            to_agent="frontend",
            phase=NegotiationPhase.NEGOTIATE,
            proposal={
                "iteration": iteration,
                "max_iterations": max_iterations,
                "progress_pct": round((iteration + 1) / max_iterations * 100),
                "current_utility": round(current_utility, 4),
                "remaining_conflicts": remaining_conflicts,
                "fixes_this_round": fixes_this_round,
            },
            extra={"round_progress": True},
        )
        await self._publish(session_id, event)

    async def publish_agent_consultation(
        self,
        session_id: str,
        conflict_type: str,
        agent_suggestions: List[dict],
    ) -> None:
        """发布 Agent 征询事件"""
        event = create_negotiation_event(
            event_type=NegotiationEventType.AGENT_MSG,
            session_id=session_id,
            from_agent="dispatcher",
            to_agent="all_agents",
            phase=NegotiationPhase.NEGOTIATE,
            proposal={
                "action": "Agent征询",
                "conflict_type": conflict_type,
                "responses": agent_suggestions,
            },
            extra={"agentConsultation": True, "agentResponses": agent_suggestions},
        )
        await self._publish(session_id, event)

    async def publish_route_optimization(
        self,
        session_id: str,
        long_distance_warnings: List[dict],
    ) -> None:
        """发布路线优化完成事件"""
        route_preview = build_route_preview(vehicle_id="route_opt", coordinates=[])
        route_preview["long_distance_warnings"] = long_distance_warnings
        
        event = create_negotiation_event(
            event_type=NegotiationEventType.COUNTER,
            session_id=session_id,
            from_agent="optimizer",
            to_agent="dispatcher",
            phase=NegotiationPhase.NEGOTIATE,
            proposal={
                "action": "路线优化完成",
                "long_distance_warnings": long_distance_warnings,
            },
            extra={"longDistanceWarning": True, "longDistanceSegments": long_distance_warnings},
            utility={"dispatcher": 0.85, "vehicle": 0.8},
            route_preview=route_preview,
        )
        await self._publish(session_id, event)

    async def publish_bid(
        self,
        session_id: str,
        conflict_type: str,
        bids: List[dict],
        day_num: int,
    ) -> None:
        """发布冲突招标事件（改造方案 4.2.5）"""
        event = create_negotiation_event(
            event_type=NegotiationEventType.PROPOSE,
            session_id=session_id,
            from_agent="dispatcher",
            to_agent="all_agents",
            phase=NegotiationPhase.NEGOTIATE,
            proposal={
                "action": "冲突招标",
                "conflict_type": conflict_type,
                "num_bids": len(bids),
                "bids_summary": [
                    {"agent_id": b["agent_id"], "strategy": b["strategy"]}
                    for b in bids
                ],
                "day": day_num,
            },
            extra={"conflictBidding": True},
        )
        await self._publish(session_id, event)

    async def publish_bid_result(
        self,
        session_id: str,
        winner_agent: str,
        winning_strategy: str,
        day_num: int,
    ) -> None:
        """发布招标结果事件（改造方案 4.2.5）"""
        event = create_negotiation_event(
            event_type=NegotiationEventType.AGENT_MSG,
            session_id=session_id,
            from_agent="dispatcher",
            to_agent="all_agents",
            phase=NegotiationPhase.NEGOTIATE,
            proposal={
                "action": "招标授标",
                "winner_agent": winner_agent,
                "winning_strategy": winning_strategy,
                "day": day_num,
            },
            extra={"conflictBiddingResult": True},
        )
        await self._publish(session_id, event)

    async def publish_llm_arbitration(
        self,
        session_id: str,
        analysis: str,
        adjustments: List[dict],
        solution_type: str,
    ) -> None:
        """发布 LLM 仲裁事件"""
        event = create_negotiation_event(
            event_type=NegotiationEventType.COUNTER,
            session_id=session_id,
            from_agent="llm_arbiter",
            to_agent="dispatcher",
            phase=NegotiationPhase.NEGOTIATE,
            proposal={
                "action": f"LLM仲裁({solution_type})",
                "analysis": analysis,
                "adjustments": adjustments,
            },
            utility={"dispatcher": 0.4, "vehicle": 0.4},
        )
        await self._publish(session_id, event)

    async def _publish(self, session_id: str, event: Dict[str, Any]) -> None:
        """内部发布方法（支持 fire-and-forget 模式）"""
        if self.fire_and_forget:
            import asyncio
            asyncio.ensure_future(event_bus.publish(session_id, event))
        else:
            try:
                await event_bus.publish(session_id, event)
            except Exception as e:
                logger.warning(f"[事件发布器] 发布事件失败（已内部捕获）: {e}")


# 全局单例
event_publisher = NegotiationEventPublisher()
