"""
修复验证器（增强版）

负责:
1. 验证策略修复后的结果（调用冲突检测检查是否仍有 error）
2. 收集 Agent 对修复方案的投票（加权投票制）
3. 【P2】投票失败后触发反提案机制
4. 生成调整详情 (adjustment details)

将验证逻辑从 negotiate_and_fix() 主循环中抽离。
"""

import logging
import copy
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


class RepairValidator:
    """
    修复验证器（单例）

    所有验证相关的辅助函数集中在此。
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
        logger.info("[修复验证器] 初始化完成")

    def verify_repair(
        self,
        proposed_plans: List[dict],
        structured_requirement: dict,
        day_num: int,
    ) -> Tuple[bool, List[dict]]:
        """
        验证修复结果

        检查修复后的方案在当天是否仍有 error 级别的冲突。
        使用独立的 detect_conflicts 代替旧的 check_itinerary_conflicts。

        Args:
            proposed_plans: 修复后的全部行程
            structured_requirement: 结构化需求
            day_num: 要检查的天数

        Returns:
            (is_valid, remaining_errors) 
            is_valid: True 表示当天没有 error 冲突
            remaining_errors: 当天剩下的 error 冲突列表
        """
        from .conflict_detector import detect_conflicts

        detection = detect_conflicts(proposed_plans, structured_requirement)
        day_errors = [
            c for c in detection.conflicts
            if c.get("severity") == "error" and c.get("day") == day_num
        ]

        return (len(day_errors) == 0, day_errors)

    async def collect_agent_consensus(
        self,
        proposed_plans: List[dict],
        original_plans: List[dict],
        conflict: dict,
        strategy_name: str,
        session_id: str,
        structured_requirement: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        收集 Agent 对修复方案的意见（加权投票制）

        投票权重规则（从 shared_context 读取，可动态配置）：
          - attractions_agent     权重 0.30（景点安排重要性高）
          - food_agent            权重 0.15（餐饮可调整空间大）
          - transport_agent       权重 0.25（交通依赖性强）
          - hotel_agent           权重 0.10（住宿一般不直接影响）
          - dispatcher            权重 0.20（协调方拥有否决权）
          - 未注册 agent          权重 0.05

        决策阈值：赞成票权重之和 >= 0.60 则通过（默认）。
        支持从 shared_context 中动态读取阈值，适配不同协商场景。

        Args:
            proposed_plans: 修复后的方案
            original_plans: 修复前的方案
            conflict: 冲突信息
            strategy_name: 使用的策略名称
            session_id: 会话ID

        Returns:
            {
                "approved": bool,          # 是否通过
                "pass_ratio": float,       # 赞成比例
                "approve_weight": float,
                "veto_weight": float,
                "threshold": float,
                "vote_details": List[str],
                "counter_proposals": List[Dict],  # Agent 提出的反提案
                "veto_reasons": List[Dict],       # 否决理由详情
            }
        """
        from src.services.negotiation_event_bus import agent_message_bus, AgentMessageType

        # === 默认权重体系 ===
        default_weights = {
            "attractions_agent": 0.30,
            "attractions_agent_001": 0.30,
            "food_agent": 0.15,
            "food_agent_001": 0.15,
            "transport_agent": 0.25,
            "transport_agent_001": 0.25,
            "hotel_agent": 0.10,
            "hotel_agent_001": 0.10,
            "dispatcher": 0.20,
        }
        # 默认权重总和 >= 1.0，但每个agent独立权重用于加权计算
        default_pass_threshold = 0.60

        # === 从 shared_context 读取动态配置（如存在） ===
        ctx = agent_message_bus.get_shared_context(session_id)
        weights = ctx.get("voting_weights", default_weights)
        pass_threshold = ctx.get("voting_pass_threshold", default_pass_threshold)

        # === 构建投票请求 ===
        conflict_type = conflict.get("type", "")
        day = conflict.get("day", 1)
        day_idx = day - 1

        old_plan = original_plans[day_idx] if 0 <= day_idx < len(original_plans) else {}
        new_plan = proposed_plans[day_idx] if 0 <= day_idx < len(proposed_plans) else {}

        changes = self._summarize_changes(old_plan, new_plan)

        message_payload = {
            "action": "consensus_vote",
            "conflict_type": conflict_type,
            "conflict_description": conflict.get("description", ""),
            "strategy_applied": strategy_name,
            "day_num": day,
            "changes": changes,
            "original_day_summary": self._summarize_day_plan(old_plan),
            "proposed_day_summary": self._summarize_day_plan(new_plan),
        }

        try:
            responses = await agent_message_bus.broadcast(
                from_agent="dispatcher",
                message={
                    "type": AgentMessageType.COORDINATE_REQUEST,
                    "payload": message_payload,
                },
                session_id=session_id,
            )
        except Exception as e:
            logger.error(f"[协商投票] broadcast 异常: {e}，返回不通过")
            return {
                "approved": False,
                "pass_ratio": 0.0,
                "approve_weight": 0.0,
                "veto_weight": 0.0,
                "threshold": pass_threshold,
                "vote_details": [],
                "counter_proposals": [],
                "veto_reasons": [],
                "hard_veto": False,
                "error": str(e),
            }

        # === 加权计票 ===
        approve_weight = 0.0
        veto_weight = 0.0
        vote_details = []
        counter_proposals = []   # 收集反提案
        veto_reasons = []        # 收集否决理由

        for agent_id, response in responses.items():
            if not isinstance(response, dict):
                continue

            agent_weight = weights.get(agent_id, 0.05)
            vote = response.get("vote", "approve")  # approve / veto

            if vote == "veto" or response.get("veto"):
                veto_weight += agent_weight
                reason = response.get("reason", "无理由")
                vote_details.append(f"{agent_id}(反对,权重{agent_weight:.2f}): {reason}")
                veto_reasons.append({
                    "agent_id": agent_id,
                    "weight": agent_weight,
                    "reason": reason,
                    "strategy": strategy_name,
                })

                # 收集反提案（Agent 可以在否决时附带替代方案）
                counter = response.get("counter_proposal")
                if counter and isinstance(counter, dict):
                    counter_proposals.append({
                        "agent_id": agent_id,
                        "strategy": counter.get("strategy", ""),
                        "params": counter.get("params", {}),
                        "reason": counter.get("reason", reason),
                    })

            elif vote == "approve":
                approve_weight += agent_weight
                vote_details.append(f"{agent_id}(赞成,权重{agent_weight:.2f})")

            # dispatcher 硬否决 — 【阶段C】先尝试LLM仲裁兜底
            if agent_id == "dispatcher" and (vote == "veto" or response.get("veto")):
                logger.info(
                    f"[协商加权投票] Dispatcher 否决方案 {strategy_name}，尝试LLM仲裁兜底"
                )
                # 尝试用 LLM 仲裁生成替代方案
                llm_solution = await self._try_llm_arbitration_for_veto(
                    session_id=session_id,
                    day_plans=proposed_plans,
                    structured_requirement=structured_requirement or {},
                    conflict=conflict,
                    strategy_name=strategy_name,
                    veto_reason=response.get("reason", ""),
                )
                if llm_solution:
                    logger.info(
                        f"[协商加权投票] LLM仲裁兜底成功，采纳替代方案"
                    )
                    return {
                        "approved": True,
                        "pass_ratio": 1.0,
                        "approve_weight": weights.get("dispatcher", 0.20),
                        "veto_weight": 0.0,
                        "threshold": pass_threshold,
                        "vote_details": vote_details + [f"llm_arbiter(兜底采纳)"],
                        "counter_proposals": counter_proposals,
                        "veto_reasons": veto_reasons,
                        "hard_veto": False,
                        "llm_fallback": True,
                        "llm_adjustments": llm_solution.get("adjustments", []),
                        "llm_modified_plans": llm_solution.get("day_plans", proposed_plans),
                    }
                # LLM 也失败，才执行硬否决
                logger.info(
                    f"[协商加权投票] LLM仲裁兜底失败，执行硬否决"
                )
                return {
                    "approved": False,
                    "pass_ratio": 0.0,
                    "approve_weight": 0.0,
                    "veto_weight": 1.0,
                    "threshold": pass_threshold,
                    "vote_details": vote_details,
                    "counter_proposals": counter_proposals,
                    "veto_reasons": veto_reasons,
                    "hard_veto": True,
                }

        total_voted = approve_weight + veto_weight
        pass_ratio = approve_weight / total_voted if total_voted > 0 else 0.0
        passed = pass_ratio >= pass_threshold

        logger.info(
            f"[协商加权投票] 方案={strategy_name}, 赞成={approve_weight:.2f}, "
            f"反对={veto_weight:.2f}, 通过率={pass_ratio:.2%}, "
            f"阈值={pass_threshold:.0%}, 详情={'; '.join(vote_details)}"
        )

        # 将投票结果写入 shared_context（供其他环节参考）
        ctx["last_vote_result"] = {
            "approve_weight": approve_weight,
            "veto_weight": veto_weight,
            "pass_ratio": pass_ratio,
            "threshold": pass_threshold,
            "passed": passed,
            "vote_details": vote_details,
            "counter_proposals": counter_proposals,
            "veto_reasons": veto_reasons,
        }

        return {
            "approved": passed,
            "pass_ratio": pass_ratio,
            "approve_weight": approve_weight,
            "veto_weight": veto_weight,
            "threshold": pass_threshold,
            "vote_details": vote_details,
            "counter_proposals": counter_proposals,
            "veto_reasons": veto_reasons,
            "hard_veto": False,
        }

    async def _try_llm_arbitration_for_veto(
        self,
        session_id: str,
        day_plans: List[Dict[str, Any]],
        structured_requirement: Dict[str, Any],
        conflict: Dict[str, Any],
        strategy_name: str,
        veto_reason: str,
    ) -> Optional[Dict[str, Any]]:
        """
        【阶段C】Dispatcher硬否决时，先尝试LLM仲裁兜底。

        让 LLM 分析当前的冲突和行程，看是否有可行的替代方案。
        如果有，返回调整后的方案；否则返回 None。

        Args:
            session_id: 会话ID
            day_plans: 当前行程
            structured_requirement: 结构化需求
            conflict: 冲突信息
            strategy_name: 被否决的策略名
            veto_reason: 否决理由

        Returns:
            {"adjustments": [...], "day_plans": [...]} 或 None
        """
        try:
            from src.services.negotiation_llm_arbiter import llm_arbiter

            # 构造协商日志片段
            negotiation_log = [
                {
                    "round": "final_vote",
                    "conflict_type": conflict.get("type", ""),
                    "strategy_applied": strategy_name,
                    "veto_reason": veto_reason,
                    "dispatcher_veto": True,
                }
            ]

            llm_result = await llm_arbiter.arbitrate(
                day_plans=day_plans,
                structured_requirement=structured_requirement,
                conflicts=[conflict],
                negotiation_log=negotiation_log,
                session_id=session_id,
            )

            if llm_result and llm_result.get("adjustments"):
                logger.info(
                    f"[LLM仲裁兜底] 策略={strategy_name}, "
                    f"生成了{len(llm_result['adjustments'])}项调整"
                )
                return llm_result

            logger.info(
                f"[LLM仲裁兜底] 策略={strategy_name}, LLM未生成可行方案"
            )
            return None

        except Exception as e:
            logger.warning(f"[LLM仲裁兜底] 异常: {e}")
            return None

    async def try_counter_proposal(
        self,
        session_id: str,
        conflict: Dict[str, Any],
        day_plans: List[Dict[str, Any]],
        structured_requirement: Dict[str, Any],
        negotiation_log: Optional[List[Dict]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        当加权投票失败后，触发反提案机制

        Args:
            session_id: 会话ID
            conflict: 当前冲突
            day_plans: 当前行程
            structured_requirement: 结构化需求
            negotiation_log: 协商日志

        Returns:
            反提案结果（含修改后的行程），或 None 表示全部失败
        """
        from src.services.negotiation_core.counter_proposal import counter_proposal_engine

        logger.info(
            f"[协商] 加权投票失败，触发反提案机制: session={session_id}, "
            f"conflict_type={conflict.get('type', '')}"
        )

        result = await counter_proposal_engine.trigger_counter_proposal(
            session_id=session_id,
            conflict=conflict,
            day_plans=day_plans,
            structured_requirement=structured_requirement,
            negotiation_log=negotiation_log,
        )

        if result and result.get("adjustments"):
            logger.info(
                f"[协商] 反提案成功: author={result.get('proposal_author', 'unknown')}, "
                f"调整数={len(result.get('adjustments', []))}"
            )
        else:
            logger.info("[协商] 反提案流程无有效结果")

        return result

    async def consult_agents(
        self,
        day_plans: List[dict],
        day_idx: int,
        conflict: dict,
        session_id: str,
        iteration: int,
    ) -> List[dict]:
        """
        在执行策略前，征询 Agent 意见

        Args:
            day_plans: 当前行程
            day_idx: 当前 day 索引
            conflict: 冲突信息
            session_id: 会话ID
            iteration: 当前迭代轮数

        Returns:
            Agent 建议列表
        """
        from src.services.negotiation_event_bus import agent_message_bus, AgentMessageType

        conflict_type = conflict.get("type", "")
        conflict_activities = conflict.get("activities", [])
        day_num = conflict.get("day", 1)

        agent_query_payload = {
            "action": "conflict_consultation",
            "session_id": session_id,
            "conflict_type": conflict_type,
            "conflict_description": conflict.get("description", ""),
            "conflict_activities": conflict_activities,
            "day_num": day_num,
            "day_plan_summary": {
                "attractions": [
                    a.get("name", "") for a in day_plans[day_idx].get("attractions", [])
                    if isinstance(a, dict)
                ],
                "meals": [
                    m.get("name", "") for m in day_plans[day_idx].get("meals", [])
                    if isinstance(m, dict)
                ],
            },
            "iteration": iteration,
        }

        responses = await agent_message_bus.broadcast(
            from_agent="dispatcher",
            message={
                "type": AgentMessageType.PREFERENCE_QUERY,
                "payload": agent_query_payload,
            },
            session_id=session_id,
        )

        agent_suggestions = []
        if responses:
            for agent_id, response in responses.items():
                if response and isinstance(response, dict):
                    suggestion = response.get("suggestion") or response.get("response", "")
                    if suggestion:
                        agent_suggestions.append({
                            "agent_id": agent_id,
                            "suggestion": str(suggestion)[:100],
                        })
                        logger.info(
                            f"[协商] Agent {agent_id} 建议: {str(suggestion)[:100]}"
                        )

        return agent_suggestions

    async def consult_agents_on_conflict(
        self,
        session_id: str,
        conflict: Dict[str, Any],
        day_plan: Dict[str, Any],
        day_idx: int,
    ) -> Dict[str, Any]:
        """
        事前咨询：在执行策略前先问 Agent 意见。

        Agent 可以返回：
        - 建议的策略名称和参数（suggested_strategy）
        - 不希望执行的策略（veto_strategies）
        - 偏好说明（preferences）

        对应重构清单 4.2.2：Agent 投票机制增强 — 事前咨询。
        这样 Agent 从"事后否决"变为"事前建议"。

        Args:
            session_id: 会话ID
            conflict: 冲突信息
            day_plan: 当前天的行程
            day_idx: 天索引

        Returns:
            {
                "suggested_strategies": [
                    {"agent_id": str, "name": str, "params": dict}
                ],
                "veto_strategies": [str],
                "agent_responses": {agent_id: response_dict}
            }
        """
        from src.services.negotiation_event_bus import agent_message_bus, AgentMessageType

        conflict_type = conflict.get("type", "")
        day_num = conflict.get("day", 1)

        payload = {
            "action": "consult_conflict",
            "conflict_type": conflict_type,
            "conflict_description": conflict.get("description", ""),
            "day": day_num,
            "activities": conflict.get("activities", []),
            "current_day_summary": {
                "attractions": [
                    f"{a.get('name', '?')}({a.get('start_time', '?')}-{a.get('end_time', '?')})"
                    for a in day_plan.get("attractions", []) if isinstance(a, dict)
                ],
                "meals": [
                    f"{m.get('name', '?')}({m.get('start_time', m.get('time', '?'))})"
                    for m in day_plan.get("meals", []) if isinstance(m, dict)
                ],
            },
        }

        try:
            responses = await agent_message_bus.broadcast(
                from_agent="dispatcher",
                message={
                    "type": AgentMessageType.COORDINATE_REQUEST,
                    "payload": payload,
                },
                session_id=session_id,
            )
        except Exception as e:
            logger.warning(f"[协商] consult_agents_on_conflict broadcast异常: {e}")
            responses = {}

        suggested_strategies = []
        veto_strategies = []
        agent_responses = {}

        for agent_id, response in responses.items():
            if not isinstance(response, dict):
                continue

            agent_responses[agent_id] = response

            # Agent 建议的策略
            suggested = response.get("suggested_strategy")
            if suggested:
                suggested_strategies.append({
                    "agent_id": agent_id,
                    "name": suggested,
                    "params": response.get("suggested_params", {}),
                })

            # Agent 反对的策略
            veto_list = response.get("veto_strategies", [])
            if veto_list:
                veto_strategies.extend(veto_list)

        return {
            "suggested_strategies": suggested_strategies,
            "veto_strategies": list(set(veto_strategies)),
            "agent_responses": agent_responses,
        }

    def build_adjustment_details(
        self,
        plan_before: dict,
        plan_after: dict,
        strategy_name: str,
    ) -> list:
        """
        对比修复前后的 day_plan，生成详细的调整内容列表

        返回格式:
        [
            {
                "field": "start_time|end_time|duration|location|activity_name|day",
                "item_name": "故宫",
                "before": "09:00",
                "after": "08:30",
                "strategy": "strategy_time_shift",
                "human_readable": "将故宫的游览开始时间从09:00调整为08:30"
            },
            ...
        ]

        【第四阶段】新增 human_readable 字段，便于前端直接展示中文说明。
        """
        from .explanation_templates import build_human_readable_from_adjustment

        details = []

        # 比较景点变化
        before_attrs = {a.get("name", ""): a for a in plan_before.get("attractions", []) if isinstance(a, dict)}
        after_attrs = {a.get("name", ""): a for a in plan_after.get("attractions", []) if isinstance(a, dict)}

        all_names = set(list(before_attrs.keys()) + list(after_attrs.keys()))
        for name in all_names:
            before_attr = before_attrs.get(name)
            after_attr = after_attrs.get(name)

            if not before_attr and after_attr:
                adj = {
                    "field": "activity_name",
                    "item_name": name,
                    "before": "无",
                    "after": after_attr.get("name", name),
                    "strategy": strategy_name,
                }
                adj["human_readable"] = build_human_readable_from_adjustment(adj)
                details.append(adj)
                continue

            if before_attr and not after_attr:
                adj = {
                    "field": "activity_name",
                    "item_name": name,
                    "before": before_attr.get("name", name),
                    "after": "已移除",
                    "strategy": strategy_name,
                }
                adj["human_readable"] = build_human_readable_from_adjustment(adj)
                details.append(adj)
                continue

            if not before_attr or not after_attr:
                continue

            b_start = before_attr.get("start_time") or before_attr.get("visit_time", "")
            a_start = after_attr.get("start_time") or after_attr.get("visit_time", "")
            b_end = before_attr.get("end_time", "")
            a_end = after_attr.get("end_time", "")
            if b_start != a_start:
                adj = {
                    "field": "start_time",
                    "item_name": name,
                    "before": b_start,
                    "after": a_start,
                    "strategy": strategy_name,
                }
                adj["human_readable"] = build_human_readable_from_adjustment(adj)
                details.append(adj)
            if b_end != a_end and b_end and a_end:
                adj = {
                    "field": "end_time",
                    "item_name": name,
                    "before": b_end,
                    "after": a_end,
                    "strategy": strategy_name,
                }
                adj["human_readable"] = build_human_readable_from_adjustment(adj)
                details.append(adj)

            b_dur = before_attr.get("duration") or before_attr.get("visit_duration", "")
            a_dur = after_attr.get("duration") or after_attr.get("visit_duration", "")
            if b_dur != a_dur:
                adj = {
                    "field": "duration",
                    "item_name": name,
                    "before": str(b_dur) if b_dur else "",
                    "after": str(a_dur) if a_dur else "",
                    "strategy": strategy_name,
                }
                adj["human_readable"] = build_human_readable_from_adjustment(adj)
                details.append(adj)

            b_slot = before_attr.get("visit_time_slot", "")
            a_slot = after_attr.get("visit_time_slot", "")
            slot_map = {"morning": "上午", "afternoon": "下午", "evening": "晚上"}
            if b_slot != a_slot:
                adj = {
                    "field": "visit_time_slot",
                    "item_name": name,
                    "before": slot_map.get(b_slot, b_slot),
                    "after": slot_map.get(a_slot, a_slot),
                    "strategy": strategy_name,
                }
                adj["human_readable"] = build_human_readable_from_adjustment(adj)
                details.append(adj)

        # 比较餐饮变化
        before_meals = {m.get("name", ""): m for m in plan_before.get("meals", []) if isinstance(m, dict)}
        after_meals = {m.get("name", ""): m for m in plan_after.get("meals", []) if isinstance(m, dict)}

        for name, after_meal in after_meals.items():
            before_meal = before_meals.get(name)
            if not before_meal:
                continue
            b_time = before_meal.get("start_time") or before_meal.get("time") or before_meal.get("meal_time", "")
            a_time = after_meal.get("start_time") or after_meal.get("time") or after_meal.get("meal_time", "")
            if b_time != a_time:
                adj = {
                    "field": "meal_time",
                    "item_name": name,
                    "before": b_time,
                    "after": a_time,
                    "strategy": strategy_name,
                }
                adj["human_readable"] = build_human_readable_from_adjustment(adj)
                details.append(adj)

        if not details:
            adj = {
                "field": "调整策略",
                "item_name": "行程",
                "before": "冲突状态",
                "after": f"执行{strategy_name}",
                "strategy": strategy_name,
            }
            adj["human_readable"] = build_human_readable_from_adjustment(adj)
            details.append(adj)

        return details

    def _summarize_changes(self, old_plan: dict, new_plan: dict) -> list:
        """生成两版行程之间的差异摘要"""
        changes = []

        old_attrs = {a.get("name", ""): a for a in old_plan.get("attractions", []) if isinstance(a, dict)}
        new_attrs = {a.get("name", ""): a for a in new_plan.get("attractions", []) if isinstance(a, dict)}

        all_names = set(list(old_attrs.keys()) + list(new_attrs.keys()))
        for name in all_names:
            old_a = old_attrs.get(name)
            new_a = new_attrs.get(name)

            if old_a and new_a:
                old_start = old_a.get("start_time", "")
                new_start = new_a.get("start_time", "")
                if old_start != new_start:
                    changes.append(f"{name}: {old_start} → {new_start}")

                old_dur = old_a.get("visit_duration", old_a.get("duration", ""))
                new_dur = new_a.get("visit_duration", new_a.get("duration", ""))
                if old_dur != new_dur:
                    changes.append(f"{name}: 时长 {old_dur} → {new_dur}")

            elif old_a and not new_a:
                changes.append(f"{name}: 已移除")
            elif not old_a and new_a:
                changes.append(f"{name}: 新增")

        return changes

    def _summarize_day_plan(self, plan: dict) -> dict:
        """生成单日行程的摘要"""
        return {
            "attractions": [
                f"{a.get('name', '?')}({a.get('start_time', '?')}-{a.get('end_time', '?')})"
                for a in plan.get("attractions", []) if isinstance(a, dict)
            ],
            "meals": [
                f"{m.get('name', '?')}({m.get('start_time', m.get('time', '?'))})"
                for m in plan.get("meals", []) if isinstance(m, dict)
            ],
        }


# 全局单例
repair_validator = RepairValidator()
