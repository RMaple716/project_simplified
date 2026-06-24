"""
反提案机制 — Agent驱动的创造性协商

功能:
1. ✅ 当确定性策略 + 加权投票失败时，由 Agent 生成反提案
2. ✅ 每个 Agent 通过 LLM 理解冲突，生成替代方案
3. ✅ 反提案在 Agent 间流转评估，直到达成共识
4. ✅ 集成 LLM 仲裁者作为最后兜底

核心流程:
  trigger_counter_proposal(session_id, conflict, day_plans)
    ↓
  agent_message_bus.broadcast("counter_proposal_request")
    ↓  (每个Agent异步生成反提案)
  collect_counter_proposals()
    ↓
  evaluate_counter_proposals() — 加权投票 + 效用比较
    ↓
  select_best_proposal() — 选择最优反提案
    ↓
  apply_counter_proposal() — 应用到行程

使用方式:
    from src.services.negotiation_core.counter_proposal import counter_proposal_engine

    result = await counter_proposal_engine.trigger_counter_proposal(
        session_id=session_id,
        conflict=conflict,
        day_plans=current_plans,
        structured_requirement=structured_req,
    )
"""

import json
import copy
import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


# ==================== 反提案引擎 ====================

class CounterProposalEngine:
    """
    反提案引擎（单例）

    当确定性策略链 + 加权投票全部失败后，
    触发此引擎让各 Agent 通过 LLM 生成反提案。
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
        # 反提案超时（秒）
        self.proposal_timeout = 15.0
        # 最大反提案轮数
        self.max_rounds = 3
        # 通过阈值（加权投票）
        self.pass_threshold = 0.60
        logger.info("[反提案引擎] 初始化完成")

    async def trigger_counter_proposal(
        self,
        session_id: str,
        conflict: Dict[str, Any],
        day_plans: List[Dict[str, Any]],
        structured_requirement: Dict[str, Any],
        negotiation_log: Optional[List[Dict]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        触发反提案流程

        改造后（阶段B）:
        1. 收集各Agent初始反提案（同前）
        2. 【新增】对每个反提案，让其他Agent评估并提条件反提案
        3. 多轮流转直到达成一致或进入LLM兜底

        Args:
            session_id: 会话ID
            conflict: 未能解决的冲突
            day_plans: 当前行程
            structured_requirement: 结构化需求
            negotiation_log: 协商日志

        Returns:
            反提案结果:
            {
                "status": "accepted" | "rejected" | "partial",
                "proposal_author": agent_id,
                "adjustments": [...],
                "modified_plans": [...],
                "vote_result": {...},
                "rounds": int,
            }
            如果所有反提案都被拒绝，返回None
        """
        from src.services.negotiation_event_bus import agent_message_bus, AgentMessageType

        conflict_type = conflict.get("type", "")
        conflict_description = conflict.get("description", "")
        day_num = conflict.get("day", 1)

        # 将冲突信息写入共享上下文
        ctx = agent_message_bus.get_shared_context(session_id)
        ctx["active_conflict"] = {
            "type": conflict_type,
            "description": conflict_description,
            "day": day_num,
            "activities": conflict.get("activities", []),
        }

        # 多轮反提案
        for round_num in range(self.max_rounds):
            logger.info(
                f"[反提案] session={session_id}, round={round_num + 1}, "
                f"冲突类型={conflict_type}"
            )

            # 向所有 Agent 广播反提案请求
            proposals = await self._collect_proposals(
                session_id=session_id,
                conflict=conflict,
                day_plans=day_plans,
                structured_requirement=structured_requirement,
                negotiation_log=negotiation_log,
                round_num=round_num,
            )

            if not proposals:
                logger.info("[反提案] 所有Agent均未生成反提案")
                return None

            # === 【阶段B】跨Agent反提案流转 ===
            # 让非作者Agent评估反提案，并可附带条件反提案
            refined_proposals = await self._refine_proposals_via_agent_feedback(
                session_id=session_id,
                proposals=proposals,
                conflict=conflict,
                day_plans=day_plans,
                structured_requirement=structured_requirement,
                negotiation_log=negotiation_log,
                round_num=round_num,
            )

            # 评估所有反提案（加权投票 + 效用比较）
            best_proposal = await self._evaluate_proposals(
                session_id=session_id,
                proposals=refined_proposals,
                day_plans=day_plans,
                structured_requirement=structured_requirement,
                conflict=conflict,
            )

            if best_proposal is None:
                logger.info(f"[反提案] 第{round_num + 1}轮: 所有反提案被否决")
                continue

            # 应用选中的反提案
            logger.info(
                f"[反提案] 第{round_num + 1}轮: 采纳 '{best_proposal['author']}' 的反提案"
            )

            # 记录到共享上下文
            history = ctx.setdefault("negotiation_history", [])
            history.append({
                "round": round_num + 1,
                "type": "counter_proposal",
                "author": best_proposal["author"],
                "adjustments": best_proposal.get("adjustments", []),
                "vote_result": best_proposal.get("vote_result", {}),
            })

            return best_proposal

        # 所有反提案失败 → 尝试 LLM 仲裁（兜底）
        logger.info("[反提案] 所有反提案被否决，尝试LLM仲裁兜底")
        return await self._fallback_to_llm_arbitration(
            session_id=session_id,
            conflict=conflict,
            day_plans=day_plans,
            structured_requirement=structured_requirement,
            negotiation_log=negotiation_log,
        )

    async def _collect_proposals(
        self,
        session_id: str,
        conflict: Dict[str, Any],
        day_plans: List[Dict[str, Any]],
        structured_requirement: Dict[str, Any],
        negotiation_log: Optional[List[Dict]],
        round_num: int,
    ) -> List[Dict[str, Any]]:
        """
        收集各Agent的反提案

        每个Agent通过LLM理解冲突后生成替代方案。
        """
        from src.services.negotiation_event_bus import agent_message_bus, AgentMessageType
        from src.services.negotiation_llm_arbiter import llm_arbiter

        conflict_description = json.dumps(
            {
                "type": conflict.get("type", ""),
                "description": conflict.get("description", ""),
                "day": conflict.get("day", 1),
                "activities": conflict.get("activities", []),
            },
            ensure_ascii=False,
        )

        # 构建每日摘要
        day_summaries = []
        for d_idx, plan in enumerate(day_plans):
            attrs = [
                f"{a.get('name', '?')}({a.get('start_time', '?')}-{a.get('end_time', '?')})"
                for a in plan.get("attractions", []) if isinstance(a, dict)
            ]
            meals = [
                f"{m.get('name', '?')}({m.get('start_time', m.get('time', '?'))})"
                for m in plan.get("meals", []) if isinstance(m, dict)
            ]
            day_summaries.append({
                "day": d_idx + 1,
                "attractions": attrs,
                "meals": meals,
            })

        # 向各 Agent 广播反提案请求
        payload = {
            "action": "counter_proposal",
            "conflict": conflict,
            "conflict_description": conflict_description,
            "day_plans_summary": day_summaries,
            "structured_requirement_summary": {
                "city": structured_requirement.get("city_name", ""),
                "days": structured_requirement.get("travel_days", 1),
                "preferences": structured_requirement.get("preferences", []),
            },
            "round_num": round_num,
        }

        responses = await agent_message_bus.broadcast(
            from_agent="dispatcher",
            message={
                "type": AgentMessageType.COORDINATE_REQUEST,
                "payload": payload,
            },
            session_id=session_id,
        )

        # 处理每个Agent的响应，通过LLM生成反提案
        proposals = []
        for agent_id, response in responses.items():
            if not isinstance(response, dict):
                continue

            # Agent 表示愿意生成反提案
            if response.get("status") != "ok" and response.get("can_propose") is not True:
                continue

            # 使用 LLM 生成反提案
            llm_proposal = await llm_arbiter.generate_counter_proposal(
                agent_id=agent_id,
                current_plan=day_plans[conflict.get("day", 1) - 1] if day_plans else {},
                conflict_description=conflict_description,
                preferences=structured_requirement.get("preferences", []),
                session_id=session_id,
            )

            if llm_proposal and llm_proposal.get("proposed_changes"):
                proposals.append({
                    "author": agent_id,
                    "adjustments": llm_proposal.get("proposed_changes", []),
                    "analysis": llm_proposal.get("analysis", ""),
                    "expected_outcome": llm_proposal.get("expected_outcome", ""),
                })
                logger.info(
                    f"[反提案] {agent_id} 生成了反提案: "
                    f"{len(llm_proposal.get('proposed_changes', []))} 项调整"
                )

        return proposals

    async def _refine_proposals_via_agent_feedback(
        self,
        session_id: str,
        proposals: List[Dict[str, Any]],
        conflict: Dict[str, Any],
        day_plans: List[Dict[str, Any]],
        structured_requirement: Dict[str, Any],
        negotiation_log: Optional[List[Dict]],
        round_num: int,
    ) -> List[Dict[str, Any]]:
        """
        【阶段B】让非作者Agent评估反提案，并提条件反提案。

        对每个反提案:
        1. 让其他Agent评估（附带条件否决/附议修改）
        2. 收集条件反馈
        3. 如果有条件反馈，转发给原提案Agent回应
        4. 最多流转2轮

        Args:
            proposals: 初始反提案列表
            session_id: 会话ID
            conflict: 原冲突

        Returns:
            精炼后的反提案列表（附带了cross_agent_info）
        """
        from src.services.negotiation_event_bus import agent_message_bus, AgentMessageType

        refined_proposals = []
        max_cross_rounds = 2

        for proposal in proposals:
            author = proposal["author"]
            current_adjustments = list(proposal.get("adjustments", []))

            cross_agent_round = 0
            while cross_agent_round < max_cross_rounds:
                # 让其他Agent评估当前版反提案并提条件
                feedbacks = await self._collect_agent_feedback_on_proposal(
                    session_id=session_id,
                    proposal=proposal,
                    adjustments=current_adjustments,
                    conflict=conflict,
                    day_plans=day_plans,
                )

                # 提取条件反提案（否决但附带修改方案）
                conditional_feedbacks = [
                    f for f in feedbacks
                    if f.get("vote") == "veto" and f.get("conditional_adjustments")
                ]

                if not conditional_feedbacks:
                    # 没有条件反馈，流转结束
                    break

                # 将条件反馈转发给原提案Agent，让TA回应
                for cf in conditional_feedbacks:
                    from_agent = cf["agent_id"]
                    response = await agent_message_bus.send(
                        from_agent="dispatcher",
                        to_agent=author,
                        message={
                            "type": AgentMessageType.COORDINATE_REQUEST,
                            "payload": {
                                "action": "respond_to_condition",
                                "proposal_author": author,
                                "condition_from": from_agent,
                                "original_adjustments": current_adjustments,
                                "conditional_adjustments": cf["conditional_adjustments"],
                                "condition_reason": cf.get("reason", ""),
                            }
                        },
                        session_id=session_id,
                    )

                    if response and isinstance(response, dict):
                        if response.get("accept_condition"):
                            # Agent 接受条件，合并调整
                            current_adjustments = self._merge_adjustments(
                                current_adjustments,
                                cf["conditional_adjustments"],
                            )
                            logger.info(
                                f"[反提案流转] {author} 接受了 {from_agent} 的条件: "
                                f"{cf.get('reason', '')[:80]}"
                            )
                        elif response.get("modified_adjustments"):
                            # Agent 提出修改版，继续流转
                            current_adjustments = response["modified_adjustments"]
                            logger.info(
                                f"[反提案流转] {author} 修改了方案回应 {from_agent}"
                            )

                cross_agent_round += 1

            # 将精炼后的反提案加入结果集
            refined_proposals.append({
                **proposal,
                "adjustments": current_adjustments,
                "cross_agent_rounds": cross_agent_round,
            })

        return refined_proposals

    async def _collect_agent_feedback_on_proposal(
        self,
        session_id: str,
        proposal: Dict[str, Any],
        adjustments: List[Dict[str, Any]],
        conflict: Dict[str, Any],
        day_plans: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        【阶段B】让非作者Agent评估反提案，返回投票+可选条件反提案。

        返回格式:
        [
            {
                "agent_id": "food_agent_001",
                "vote": "approve" | "veto",
                "reason": "...",
                "conditional_adjustments": [...] (可选，否决时附带)
            }
        ]
        """
        from src.services.negotiation_event_bus import agent_message_bus, AgentMessageType

        author = proposal["author"]
        day_num = conflict.get("day", 1)
        day_idx = day_num - 1

        # 构建当前版的调整描述
        changes_desc = []
        for adj in adjustments:
            changes_desc.append(
                f"  {adj.get('item', '?')}: {adj.get('current', '?')} → {adj.get('proposed', '?')}"
            )
        changes_text = "\n".join(changes_desc) if changes_desc else "(无具体调整)"

        # 构建当天的行程摘要（调整后）
        current_plan = day_plans[day_idx] if day_idx < len(day_plans) else {}
        attrs_text = "; ".join([
            f"{a.get('name', '?')}({a.get('start_time', '?')}-{a.get('end_time', '?')})"
            for a in current_plan.get("attractions", []) if isinstance(a, dict)
        ])

        payload = {
            "action": "evaluate_counter_proposal",
            "proposal_author": author,
            "conflict_type": conflict.get("type", ""),
            "conflict_description": conflict.get("description", ""),
            "day_num": day_num,
            "changes": changes_text,
            "day_attractions": attrs_text,
        }

        responses = await agent_message_bus.broadcast(
            from_agent="dispatcher",
            message={
                "type": AgentMessageType.COORDINATE_REQUEST,
                "payload": payload,
            },
            session_id=session_id,
        )

        feedbacks = []
        for agent_id, response in responses.items():
            if not isinstance(response, dict):
                continue
            if agent_id == author:
                continue  # 提案作者不评估自己的提案

            vote = response.get("vote", "approve")
            feedback = {
                "agent_id": agent_id,
                "vote": vote,
                "reason": response.get("reason", ""),
            }

            # 如果否决并附带条件反提案
            if vote == "veto" or response.get("veto"):
                conditional = response.get("conditional_adjustments") or response.get("counter_proposal")
                if conditional and isinstance(conditional, list):
                    feedback["conditional_adjustments"] = conditional
                elif conditional and isinstance(conditional, dict):
                    feedback["conditional_adjustments"] = conditional.get("adjustments", [conditional])

            feedbacks.append(feedback)
            logger.info(
                f"[反提案评估] {agent_id} 对 {author} 的反提案: {vote}"
                f"{' (附带条件)' if feedback.get('conditional_adjustments') else ''}"
            )

        return feedbacks

    def _merge_adjustments(
        self,
        base_adjustments: List[Dict[str, Any]],
        new_adjustments: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """合并两套调整方案，以新覆盖旧"""
        merged = list(base_adjustments)
        existing_items = {a.get("item", ""): i for i, a in enumerate(merged)}

        for new_adj in new_adjustments:
            item_name = new_adj.get("item", "")
            if item_name in existing_items:
                # 覆盖已有项
                merged[existing_items[item_name]] = new_adj
            else:
                # 新增项
                merged.append(new_adj)

        return merged

    async def _evaluate_proposals(
        self,
        session_id: str,
        proposals: List[Dict[str, Any]],
        day_plans: List[Dict[str, Any]],
        structured_requirement: Dict[str, Any],
        conflict: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        评估所有反提案 — 加权投票 + 效用比较

        Args:
            session_id: 会话ID
            proposals: 反提案列表
            day_plans: 当前行程
            structured_requirement: 结构化需求
            conflict: 原冲突

        Returns:
            选中的反提案（含投票结果），None表示全部否决
        """
        from src.services.negotiation_event_bus import agent_message_bus
        from src.services.negotiation_utility import utility_evaluator

        # 默认权重
        default_weights = {
            "attractions_agent_001": 0.30,
            "food_agent_001": 0.15,
            "transport_agent_001": 0.25,
            "hotel_agent_001": 0.10,
            "dispatcher": 0.20,
        }

        ctx = agent_message_bus.get_shared_context(session_id)
        weights = ctx.get("voting_weights", default_weights)

        evaluated_proposals = []

        for proposal in proposals:
            author = proposal["author"]

            # 模拟应用调整后的方案
            modified_plans = self._simulate_apply_adjustments(
                copy.deepcopy(day_plans),
                proposal["adjustments"],
                conflict.get("day", 1),
            )

            # 计算效用
            utility = utility_evaluator.evaluate(modified_plans, structured_requirement)

            # 收集其他Agent对当前反提案的投票
            vote_result = await self._collect_votes_for_proposal(
                session_id=session_id,
                proposal=proposal,
                modified_plans=modified_plans,
                weights=weights,
                conflict=conflict,
            )

            evaluated_proposals.append({
                **proposal,
                "modified_plans": modified_plans,
                "utility": utility.overall,
                "vote_result": vote_result,
            })

            logger.info(
                f"[反提案评估] {author}: 效用={utility.overall:.4f}, "
                f"赞成权重={vote_result.get('approve_weight', 0):.2f}, "
                f"通过={vote_result.get('passed', False)}"
            )

        # 过滤通过投票的反提案
        passed = [p for p in evaluated_proposals if p.get("vote_result", {}).get("passed")]
        if not passed:
            return None

        # 按效用排序，选最优
        passed.sort(key=lambda p: p["utility"], reverse=True)
        return passed[0]

    async def _collect_votes_for_proposal(
        self,
        session_id: str,
        proposal: Dict[str, Any],
        modified_plans: List[Dict[str, Any]],
        weights: Dict[str, float],
        conflict: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        收集其他Agent对某个反提案的投票（加权）
        """
        from src.services.negotiation_event_bus import agent_message_bus, AgentMessageType

        author = proposal["author"]

        payload = {
            "action": "consensus_vote",
            "conflict_type": conflict.get("type", ""),
            "conflict_description": conflict.get("description", ""),
            "strategy_applied": f"counter_proposal_by_{author}",
            "day_num": conflict.get("day", 1),
            "changes": [
                {"item": a.get("item", ""), "current": a.get("current", ""),
                 "proposed": a.get("proposed", ""), "reason": a.get("reason", "")}
                for a in proposal.get("adjustments", [])
            ],
            "proposed_day_summary": {
                "attractions": [
                    f"{a.get('name', '?')}({a.get('start_time', '?')}-{a.get('end_time', '?')})"
                    for a in modified_plans[conflict.get("day", 1) - 1].get("attractions", [])
                    if isinstance(a, dict)
                ],
                "meals": [
                    f"{m.get('name', '?')}({m.get('start_time', m.get('time', '?'))})"
                    for m in modified_plans[conflict.get("day", 1) - 1].get("meals", [])
                    if isinstance(m, dict)
                ],
            },
        }

        responses = await agent_message_bus.broadcast(
            from_agent="dispatcher",
            message={
                "type": AgentMessageType.COORDINATE_REQUEST,
                "payload": payload,
            },
            session_id=session_id,
        )

        approve_weight = 0.0
        veto_weight = 0.0
        details = []

        for agent_id, response in responses.items():
            if not isinstance(response, dict):
                continue

            # 提案作者不参与对自己提案的投票
            if agent_id == author:
                continue

            agent_weight = weights.get(agent_id, 0.05)
            vote = response.get("vote", "approve")

            if vote == "veto" or response.get("veto"):
                veto_weight += agent_weight
                details.append(f"{agent_id}(反对,{agent_weight:.2f})")
            else:
                approve_weight += agent_weight
                details.append(f"{agent_id}(赞成,{agent_weight:.2f})")

            # Dispatcher 硬否决 — 【阶段C】先尝试LLM仲裁兜底
            if agent_id == "dispatcher" and (vote == "veto" or response.get("veto")):
                # 尝试用 LLM 仲裁
                llm_override = await self._try_llm_override_veto(
                    session_id=session_id,
                    conflict=conflict,
                    modified_plans=modified_plans,
                    proposal=proposal,
                    veto_reason=response.get("reason", ""),
                )
                if llm_override:
                    logger.info(
                        f"[反提案投票] Dispatcher否决被LLM仲裁推翻，"
                        f"采纳调整: {len(llm_override.get('adjustments', []))}项"
                    )
                    # LLM 仲裁通过，Dispatcher 改为赞成
                    approve_weight += agent_weight
                    details.append(f"{agent_id}(LLM仲裁→赞成,{agent_weight:.2f})")
                    continue  # 不执行硬否决
                return {"passed": False, "approve_weight": 0, "veto_weight": 1.0, "hard_veto": True}

        total_voted = approve_weight + veto_weight
        pass_ratio = approve_weight / total_voted if total_voted > 0 else 0.0
        passed = pass_ratio >= self.pass_threshold

        return {
            "passed": passed,
            "approve_weight": approve_weight,
            "veto_weight": veto_weight,
            "pass_ratio": pass_ratio,
            "threshold": self.pass_threshold,
            "details": details,
            "hard_veto": False,
        }

    async def _try_llm_override_veto(
        self,
        session_id: str,
        conflict: Dict[str, Any],
        modified_plans: List[Dict[str, Any]],
        proposal: Dict[str, Any],
        veto_reason: str,
    ) -> Optional[Dict[str, Any]]:
        """
        【阶段C】Dispatcher硬否决时，先尝试LLM仲裁兜底。

        让 LLM 分析冲突和调整方案，判断是否可挽救。
        如果 LLM 认为可行或给出调整方案，返回方案；否则返回 None。

        Args:
            session_id: 会话ID
            conflict: 原冲突信息
            modified_plans: 调整后的行程
            proposal: 当前反提案
            veto_reason: Dispatcher的否决理由

        Returns:
            {"adjustments": [...], "day_plans": [...]} 或 None
        """
        try:
            from src.services.negotiation_llm_arbiter import llm_arbiter

            negotiation_log = [
                {
                    "round": "counter_proposal_vote",
                    "proposal_author": proposal.get("author", "unknown"),
                    "conflict_type": conflict.get("type", ""),
                    "dispatcher_veto": True,
                    "veto_reason": veto_reason,
                }
            ]

            llm_result = await llm_arbiter.arbitrate(
                day_plans=modified_plans,
                structured_requirement={},
                conflicts=[conflict],
                negotiation_log=negotiation_log,
                session_id=session_id,
            )

            if llm_result and llm_result.get("adjustments"):
                logger.info(
                    f"[LLM仲裁兜底] 反提案被否决后LLM生成替代方案: "
                    f"{len(llm_result['adjustments'])}项调整"
                )
                return llm_result

            return None

        except Exception as e:
            logger.warning(f"[LLM仲裁兜底(反提案)] 异常: {e}")
            return None

    def _simulate_apply_adjustments(
        self,
        day_plans: List[Dict[str, Any]],
        adjustments: List[Dict[str, Any]],
        target_day: int,
    ) -> List[Dict[str, Any]]:
        """模拟将反提案的调整应用到行程中"""
        for adj in adjustments:
            try:
                item = adj.get("item", "")
                proposed_value = adj.get("proposed", "")

                # 遍历所有天的景点查找匹配项
                for plan in day_plans:
                    for attr in plan.get("attractions", []):
                        if not isinstance(attr, dict):
                            continue
                        if attr.get("name", "") == item or item in attr.get("name", ""):
                            if "->" in str(proposed_value) or "-" in str(proposed_value):
                                parts = str(proposed_value).replace("->", "-").split("-")
                                if len(parts) >= 2:
                                    attr["start_time"] = parts[0].strip()
                                    attr["end_time"] = parts[1].strip()
                            elif proposed_value:
                                attr["start_time"] = proposed_value
                            break
            except Exception as e:
                logger.warning(f"[反提案] 模拟应用调整失败: {e}")
                continue

        return day_plans

    async def _fallback_to_llm_arbitration(
        self,
        session_id: str,
        conflict: Dict[str, Any],
        day_plans: List[Dict[str, Any]],
        structured_requirement: Dict[str, Any],
        negotiation_log: Optional[List[Dict]],
    ) -> Optional[Dict[str, Any]]:
        """反提案全部失败后的LLM仲裁兜底"""
        from src.services.negotiation_llm_arbiter import llm_arbiter

        try:
            llm_result = await llm_arbiter.arbitrate(
                day_plans=day_plans,
                structured_requirement=structured_requirement,
                conflicts=[conflict],
                negotiation_log=negotiation_log or [],
                session_id=session_id,
            )

            if llm_result and llm_result.get("adjustments"):
                return {
                    "status": "accepted",
                    "proposal_author": "llm_arbiter",
                    "adjustments": llm_result.get("adjustments", []),
                    "modified_plans": llm_result.get("day_plans", day_plans),
                    "analysis": llm_result.get("analysis", ""),
                    "solution_type": llm_result.get("solution_type", ""),
                    "vote_result": {"passed": True, "method": "llm_fallback"},
                    "rounds": 0,
                }

            return None

        except Exception as e:
            logger.warning(f"[反提案] LLM仲裁兜底失败: {e}")
            return None


# ==================== 全局单例 ====================

counter_proposal_engine = CounterProposalEngine()
