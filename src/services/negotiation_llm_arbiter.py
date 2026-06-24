"""
LLM仲裁者 — 当规则化策略全部失败时，让LLM创造性解决

功能:
1. ✅ 当所有确定性策略都失败时，调用LLM生成创造性解决方案
2. ✅ LLM驱动的反提案：让Agent通过LLM理解并生成替代方案
3. ✅ 超时保护和降级机制
4. ✅ 完整的prompt模板和上下文构建
5. ✅ 【新增】LLM驱动的多Agent协商回合 — 将各Agent偏好和否决理由传递给LLM生成结构化折中方案
6. ✅ 【新增】Contract Net Protocol（合同网协议） — 作为LLM不可用时的兜底方案

使用方式:
    from src.services.negotiation_llm_arbiter import llm_arbiter

    # 当所有策略都失败时调用
    result = await llm_arbiter.arbitrate(
        day_plans=current_plans,
        structured_requirement=structured_req,
        conflicts=remaining_conflicts,
        negotiation_log=negotiation_log,
        session_id=session_id,
    )
    if result:
        current_plans = result["day_plans"]

    # 【新增】LLM协商回合（多Agent协商）
    result = await llm_arbiter.negotiate_with_llm(
        day_plans=current_plans,
        structured_requirement=structured_req,
        conflicts=remaining_conflicts,
        session_id=session_id,
        negotiation_log=negotiation_log,
        agent_vote_history=agent_vote_history,
    )

    # 【新增】Contract Net Protocol（LLM不可用时的兜底）
    result = await contract_net_protocol.run_round(
        day_plans=current_plans,
        structured_requirement=structured_req,
        conflicts=remaining_conflicts,
        session_id=session_id,
    )
"""
import json
import copy
import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from src.services.deepseek_client import DeepSeekClient

logger = logging.getLogger(__name__)


# ==================== Prompt 模板（原有） ====================

SYSTEM_PROMPT = """你是一个专业的旅行规划仲裁者。你的任务是当自动化修复策略全部失败时，
创造性地解决行程中的冲突。

请分析以下行程冲突，给出一个具体的修复方案。

你的回复必须严格遵循以下 JSON 格式（不要包含任何其他文字）：
{
    "analysis": "对冲突原因的简要分析（一句话）",
    "solution_type": "creative_reschedule | swap_activities | replace_recommendation | split_group | adjust_timing",
    "adjustments": [
        {
            "day": 1,
            "action": "调整景点时间" | "替换景点" | "移动景点到其他天" | "调整餐饮时间" | "调整交通时间",
            "target": "景点/餐厅名称",
            "from": "原来的时间或安排",
            "to": "新的时间或安排",
            "reason": "调整原因"
        }
    ],
    "expected_effect": "预期的修复效果描述"
}

注意事项：
1. 保持原有的景点和餐饮不变，除非必须替换
2. 调整后的时间必须在合理范围内（6:00-23:00）
3. 确保调整后的行程仍然符合用户的偏好
4. 如果某天行程太满，可以将活动移到其他天
5. 如果两个景点距离太远，考虑在中间安排一个顺路的景点"""


# ==================== 【新增】多Agent协商Prompt ====================

NEGOTIATION_SYSTEM_PROMPT = """你是一个专业的多智能体旅行规划协商主持人（mediator）。

当前行程中存在一些未能解决的冲突。各智能体（Agent）已经表达了他们的偏好和否决理由。
你的任务是分析各方的诉求，生成一个能够兼顾各方利益的折中方案。

请综合考虑：
1. 景点Agent的诉求（游览时间、景点选择、营业时间）
2. 美食Agent的诉求（餐饮时间、餐厅选择）
3. 交通Agent的诉求（路线顺序、交通时间）
4. 住宿Agent的诉求（住宿地点、入住/退房时间）
5. 用户偏好（预算、兴趣、特殊需求）

你的回复必须严格遵循以下 JSON 格式（不要包含任何其他文字）：
{
    "analysis": "对冲突和各Agent诉求的简要分析",
    "solution_type": "balanced_compromise | prioritize_attractions | prioritize_transport | prioritize_dining | creative_workaround",
    "adjustments": [
        {
            "day": 1,
            "action": "调整景点时间" | "替换景点" | "移动景点到其他天" | "调整餐饮时间" | "调整交通时间",
            "target": "景点/餐厅名称",
            "from": "原来的时间或安排",
            "to": "新的时间或安排",
            "reason": "调整原因（说明兼顾了哪些Agent的诉求）"
        }
    ],
    "expected_effect": "预期修复效果",
    "agent_satisfaction": {
        "attractions_agent": "满意/部分满意/不满意",
        "food_agent": "满意/部分满意/不满意",
        "transport_agent": "满意/部分满意/不满意",
        "hotel_agent": "满意/部分满意/不满意"
    }
}

注意事项：
1. 尽量保持原有的景点组合不变
2. 调整后的时间必须在合理范围内（6:00-23:00）
3. 对于每个被否决的方案，理解其背后的合理原因
4. 尝试提出能让更多Agent接受的创造性方案"""


# ==================== 构建Prompt函数（原有 + 新增） ====================

def build_arbitration_prompt(
    day_plans: List[Dict[str, Any]],
    structured_requirement: Dict[str, Any],
    conflicts: List[Dict[str, Any]],
    negotiation_log: List[Dict[str, Any]],
) -> str:
    """
    构建仲裁Prompt

    Args:
        day_plans: 当前行程
        structured_requirement: 结构化需求
        conflicts: 未能解决的冲突列表
        negotiation_log: 已尝试过的修复日志

    Returns:
        完整的用户提示词
    """
    # 基础需求信息
    city = structured_requirement.get("city_name", "未知城市")
    days = structured_requirement.get("travel_days", 1)
    budget = structured_requirement.get("total_budget", "未设置")
    preferences = structured_requirement.get("preferences", [])
    special_needs = structured_requirement.get("special_needs", "")

    prompt = f"""## 行程基本信息
- 目的地城市：{city}
- 行程天数：{days}天
- 总预算：{budget}元
- 用户偏好：{', '.join(preferences) if preferences else '未指定'}
- 特殊需求：{special_needs if special_needs else '无'}

## 当前行程安排
"""

    for day_idx, plan in enumerate(day_plans):
        day_num = day_idx + 1
        prompt += f"\n### 第{day_num}天\n"

        # 景点
        attrs = plan.get("attractions", [])
        if attrs:
            prompt += "景点：\n"
            for attr in attrs:
                if not isinstance(attr, dict):
                    continue
                name = attr.get("name", "未知")
                start = attr.get("start_time") or attr.get("visit_time", "未知")
                end = attr.get("end_time", "")
                time_str = f"{start}-{end}" if end else start
                duration = attr.get("duration") or attr.get("visit_duration", "未知")
                prompt += f"  - {name} ({time_str}, 预计游览{duration})\n"

        # 餐饮
        meals = plan.get("meals", [])
        if meals:
            prompt += "餐饮：\n"
            for meal in meals:
                if not isinstance(meal, dict):
                    continue
                name = meal.get("name", "未知")
                time = meal.get("start_time") or meal.get("time", "未知")
                prompt += f"  - {name} ({time})\n"

        # 交通
        transport = plan.get("transport")
        if isinstance(transport, dict):
            prompt += f"交通：从{transport.get('from', '未知')}到{transport.get('to', '未知')}\n"

    # 冲突信息
    prompt += f"\n## 未解决的冲突（共{len(conflicts)}个）\n"
    for c_idx, conflict in enumerate(conflicts):
        prompt += f"\n### 冲突{c_idx + 1}\n"
        prompt += f"- 类型：{conflict.get('type', '未知')}\n"
        prompt += f"- 严重程度：{conflict.get('severity', '未知')}\n"
        prompt += f"- 描述：{conflict.get('description', '无')}\n"
        activities = conflict.get("activities", [])
        if activities:
            prompt += f"- 涉及活动：{', '.join(activities)}\n"

    # 已尝试的策略
    attempted_strategies = set()
    for log in negotiation_log:
        action = log.get("action", "")
        if action and "策略" not in action and "广播" not in action:
            attempted_strategies.add(action)

    if attempted_strategies:
        prompt += f"\n## 已尝试但失败的修复策略\n"
        for s in attempted_strategies:
            prompt += f"- {s}\n"
        prompt += "\n请尝试以上策略之外的创造性解决方案。\n"
    else:
        prompt += "\n## 提示\n请提供创造性的解决方案来解决上述冲突。\n"

    return prompt


def build_negotiation_prompt(
    day_plans: List[Dict[str, Any]],
    structured_requirement: Dict[str, Any],
    conflicts: List[Dict[str, Any]],
    agent_vote_history: List[Dict[str, Any]],
    negotiation_log: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    【新增】构建多Agent协商Prompt

    将各Agent的偏好和否决理由纳入Prompt，让LLM理解各方诉求后生成折中方案。

    Args:
        day_plans: 当前行程
        structured_requirement: 结构化需求
        conflicts: 未能解决的冲突列表
        agent_vote_history: Agent投票历史（含否决理由）
        negotiation_log: 协商日志

    Returns:
        完整的用户提示词
    """
    # 基础需求信息
    city = structured_requirement.get("city_name", "未知城市")
    days = structured_requirement.get("travel_days", 1)
    budget = structured_requirement.get("total_budget", "未设置")
    preferences = structured_requirement.get("preferences", [])
    special_needs = structured_requirement.get("special_needs", "")

    prompt = f"""## 行程基本信息
- 目的地城市：{city}
- 行程天数：{days}天
- 总预算：{budget}元
- 用户偏好：{', '.join(preferences) if preferences else '未指定'}
- 特殊需求：{special_needs if special_needs else '无'}

## 当前行程安排
"""

    for day_idx, plan in enumerate(day_plans):
        day_num = day_idx + 1
        prompt += f"\n### 第{day_num}天\n"

        attrs = plan.get("attractions", [])
        if attrs:
            prompt += "景点：\n"
            for attr in attrs:
                if not isinstance(attr, dict):
                    continue
                name = attr.get("name", "未知")
                start = attr.get("start_time") or attr.get("visit_time", "未知")
                end = attr.get("end_time", "")
                time_str = f"{start}-{end}" if end else start
                duration = attr.get("duration") or attr.get("visit_duration", "未知")
                prompt += f"  - {name} ({time_str}, 预计游览{duration})\n"

        meals = plan.get("meals", [])
        if meals:
            prompt += "餐饮：\n"
            for meal in meals:
                if not isinstance(meal, dict):
                    continue
                name = meal.get("name", "未知")
                time = meal.get("start_time") or meal.get("time", "未知")
                prompt += f"  - {name} ({time})\n"

        transport = plan.get("transport")
        if isinstance(transport, dict):
            prompt += f"交通：从{transport.get('from', '未知')}到{transport.get('to', '未知')}\n"

    # 冲突信息
    prompt += f"\n## 待解决的冲突（共{len(conflicts)}个）\n"
    for c_idx, conflict in enumerate(conflicts):
        prompt += f"\n### 冲突{c_idx + 1}\n"
        prompt += f"- 类型：{conflict.get('type', '未知')}\n"
        prompt += f"- 严重程度：{conflict.get('severity', '未知')}\n"
        prompt += f"- 描述：{conflict.get('description', '无')}\n"
        activities = conflict.get("activities", [])
        if activities:
            prompt += f"- 涉及活动：{', '.join(activities)}\n"

    # Agent偏好与否决历史
    prompt += f"\n## 各Agent的偏好与投票历史\n"
    if agent_vote_history:
        for vote_item in agent_vote_history:
            agent_id = vote_item.get("agent_id", "未知Agent")
            strategy = vote_item.get("strategy_name", "未知策略")
            vote = vote_item.get("vote", "unknown")
            reason = vote_item.get("reason", "无理由")
            prompt += f"\n### {agent_id} 对「{strategy}」的投票\n"
            prompt += f"- 投票：{vote}\n"
            prompt += f"- 理由：{reason}\n"
    else:
        prompt += "（无详细投票记录）\n"

    # 已尝试的修复策略
    if negotiation_log:
        prompt += "\n## 已尝试过的修复策略\n"
        for log in negotiation_log:
            action = log.get("action", "")
            if action:
                prompt += f"- {action}\n"

    prompt += "\n请生成一个能兼顾各方诉求的创造性折中方案，输出JSON格式。\n"
    return prompt


# ==================== LLM 仲裁者（增强版） ====================

class LLMArbiter:
    """
    LLM仲裁者（增强版）

    当规则化策略全部失败时，调用LLM生成创造性解决方案。
    新增功能：
    - `negotiate_with_llm()`: 多Agent协商回合，将各Agent偏好传递给LLM
    - 支持超时保护和降级机制

    使用方式:
        # 原有仲裁
        result = await llm_arbiter.arbitrate(...)

        # 【新增】多Agent LLM协商
        result = await llm_arbiter.negotiate_with_llm(
            day_plans=...,
            structured_requirement=...,
            conflicts=...,
            session_id=...,
            agent_vote_history=[...],
        )
    """

    def __init__(self):
        self.llm_client = DeepSeekClient()
        # 超时时间（秒）
        self.timeout_seconds = 30.0
        # 最大重试次数
        self.max_retries = 2
        # 是否启用LLM仲裁
        self.enabled = True
        logger.info("[LLM仲裁者] 初始化完成")

    async def arbitrate(
        self,
        day_plans: List[Dict[str, Any]],
        structured_requirement: Dict[str, Any],
        conflicts: List[Dict[str, Any]],
        negotiation_log: Optional[List[Dict[str, Any]]] = None,
        session_id: str = "default",
    ) -> Optional[Dict[str, Any]]:
        """
        执行LLM仲裁

        Args:
            day_plans: 当前行程（将被深度拷贝，不会修改原数据）
            structured_requirement: 结构化需求
            conflicts: 未能解决的冲突列表
            negotiation_log: 已尝试过的修复日志
            session_id: 会话ID

        Returns:
            修复建议:
            {
                "day_plans": 修复后的行程（如LLM能返回完整行程）,
                "adjustments": 调整列表,
                "analysis": 冲突分析,
                "solution_type": 解决方案类型,
            }
            如果仲裁失败返回None
        """
        if not self.enabled:
            logger.info("[LLM仲裁者] 已禁用，跳过仲裁")
            return None

        if not conflicts:
            logger.info("[LLM仲裁者] 无冲突需要仲裁")
            return None

        try:
            # 检查API Key是否配置
            if not self.llm_client.api_key:
                logger.warning("[LLM仲裁者] API Key未配置，跳过LLM仲裁")
                return None

            # 构建Prompt
            prompt = build_arbitration_prompt(
                day_plans, structured_requirement, conflicts,
                negotiation_log or []
            )

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            logger.info(
                f"[LLM仲裁者] session={session_id}: 开始LLM仲裁, "
                f"冲突数={len(conflicts)}, 超时={self.timeout_seconds}s"
            )

            # 调用LLM（带超时）
            result = await asyncio.wait_for(
                self._call_llm_with_retry(messages),
                timeout=self.timeout_seconds,
            )

            if result is None:
                logger.warning("[LLM仲裁者] LLM返回空结果")
                return None

            # 解析LLM响应
            adjustments = result.get("adjustments", [])
            if not adjustments:
                logger.warning("[LLM仲裁者] LLM未返回任何调整建议")
                return None

            # 应用调整到行程
            modified_plans = self._apply_adjustments(
                copy.deepcopy(day_plans), adjustments
            )

            logger.info(
                f"[LLM仲裁者] session={session_id}: 仲裁成功, "
                f"生成{len(adjustments)}项调整, 解决方案类型={result.get('solution_type', 'unknown')}"
            )

            return {
                "day_plans": modified_plans,
                "adjustments": adjustments,
                "analysis": result.get("analysis", ""),
                "solution_type": result.get("solution_type", ""),
                "expected_effect": result.get("expected_effect", ""),
            }

        except asyncio.TimeoutError:
            logger.warning(f"[LLM仲裁者] session={session_id}: LLM调用超时({self.timeout_seconds}s)")
            return None
        except Exception as e:
            logger.warning(f"[LLM仲裁者] session={session_id}: 仲裁失败: {e}")
            return None

    # ==============================================================
    # 【新增】LLM驱动的多Agent协商回合
    # ==============================================================

    async def negotiate_with_llm(
        self,
        day_plans: List[Dict[str, Any]],
        structured_requirement: Dict[str, Any],
        conflicts: List[Dict[str, Any]],
        session_id: str = "default",
        negotiation_log: Optional[List[Dict[str, Any]]] = None,
        agent_vote_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        【新增】LLM驱动的多Agent协商回合

        当确定性策略链 + 反提案机制全部失败后，
        将各Agent的偏好、否决理由、冲突信息传递给LLM，
        让LLM理解各方诉求，生成一个结构化折中方案。

        这模拟了多Agent协商过程，LLM充当主持人（mediator）角色，
        它了解每个Agent的"红线"（否决理由）和"偏好"，
        然后提出能兼顾多方利益的创造性方案。

        Args:
            day_plans: 当前行程
            structured_requirement: 结构化需求
            conflicts: 未能解决的冲突列表
            session_id: 会话ID
            negotiation_log: 已尝试过的修复日志
            agent_vote_history: Agent投票历史（含否决理由），结构:
                [
                    {
                        "agent_id": "attractions_agent_001",
                        "strategy_name": "strategy_time_shift",
                        "vote": "veto",
                        "reason": "故宫游览时间太短，建议至少2小时"
                    },
                    ...
                ]

        Returns:
            协商结果:
            {
                "day_plans": 折中后的行程,
                "adjustments": 调整列表,
                "analysis": LLM对冲突的分析,
                "solution_type": 解决方案类型,
                "agent_satisfaction": 各Agent满意度评估,
            }
            如果协商失败返回None
        """
        if not self.enabled:
            logger.info("[LLM仲裁者-协商] 已禁用，跳过LLM协商")
            return None

        if not conflicts:
            logger.info("[LLM仲裁者-协商] 无冲突需要协商")
            return None

        try:
            if not self.llm_client.api_key:
                logger.warning("[LLM仲裁者-协商] API Key未配置，跳过LLM协商")
                return None

            # 构建多Agent协商Prompt
            prompt = build_negotiation_prompt(
                day_plans=day_plans,
                structured_requirement=structured_requirement,
                conflicts=conflicts,
                agent_vote_history=agent_vote_history or [],
                negotiation_log=negotiation_log,
            )

            messages = [
                {"role": "system", "content": NEGOTIATION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            logger.info(
                f"[LLM仲裁者-协商] session={session_id}: 开始LLM多Agent协商, "
                f"冲突数={len(conflicts)}, Agent投票记录={len(agent_vote_history or [])}条"
            )

            # 调用LLM（带超时）
            result = await asyncio.wait_for(
                self._call_llm_with_retry(messages),
                timeout=self.timeout_seconds,
            )

            if result is None:
                logger.warning("[LLM仲裁者-协商] LLM返回空结果")
                return None

            adjustments = result.get("adjustments", [])
            if not adjustments:
                logger.warning("[LLM仲裁者-协商] LLM未返回任何调整建议")
                return None

            # 应用调整到行程
            modified_plans = self._apply_adjustments(
                copy.deepcopy(day_plans), adjustments
            )

            agent_satisfaction = result.get("agent_satisfaction", {})

            logger.info(
                f"[LLM仲裁者-协商] session={session_id}: 协商成功, "
                f"生成{len(adjustments)}项调整, 方案类型={result.get('solution_type', 'unknown')}"
            )

            if agent_satisfaction:
                satisfied = sum(1 for v in agent_satisfaction.values() if v == "满意")
                total = len(agent_satisfaction)
                logger.info(
                    f"[LLM仲裁者-协商] Agent满意度: {satisfied}/{total} Agent满意"
                )

            return {
                "day_plans": modified_plans,
                "adjustments": adjustments,
                "analysis": result.get("analysis", ""),
                "solution_type": result.get("solution_type", ""),
                "expected_effect": result.get("expected_effect", ""),
                "agent_satisfaction": agent_satisfaction,
                "method": "llm_negotiation",
            }

        except asyncio.TimeoutError:
            logger.warning(f"[LLM仲裁者-协商] session={session_id}: LLM调用超时({self.timeout_seconds}s)")
            return None
        except Exception as e:
            logger.warning(f"[LLM仲裁者-协商] session={session_id}: 协商失败: {e}")
            return None

    async def _call_llm_with_retry(
        self, messages: List[Dict[str, str]]
    ) -> Optional[Dict[str, Any]]:
        """
        调用LLM并带重试机制

        Args:
            messages: 消息列表

        Returns:
            解析后的JSON响应
        """
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = await self.llm_client.chat_completion(
                    messages=messages,
                    temperature=0.8,  # 创造性需要稍高温度
                    max_tokens=2000,
                )

                content = response["choices"][0]["message"]["content"]
                return self._parse_llm_response(content)

            except Exception as e:
                last_error = e
                logger.warning(f"[LLM仲裁者] 第{attempt + 1}次调用失败: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(0.5)

        logger.error(f"[LLM仲裁者] 所有重试均失败: {last_error}")
        return None

    def _parse_llm_response(self, content: str) -> Optional[Dict[str, Any]]:
        """
        解析LLM的JSON响应（含截断修复）

        Args:
            content: LLM返回的文本

        Returns:
            解析后的字典
        """
        import re

        # 尝试提取JSON代码块
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
        if json_match:
            json_text = json_match.group(1).strip()
        else:
            # 尝试提取最外层的{}
            brace_match = re.search(r'\{[\s\S]*\}', content)
            if brace_match:
                json_text = brace_match.group(0)
            else:
                logger.warning("[LLM仲裁者] 无法从响应中提取JSON")
                return None

        # 尝试直接解析
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            pass

        # 尝试修复截断JSON
        fixed = self._fix_truncated_json(json_text)
        if fixed:
            return fixed

        logger.warning("[LLM仲裁者] JSON解析失败")
        return None

    def _fix_truncated_json(self, json_text: str) -> Optional[Dict[str, Any]]:
        """修复被截断的JSON"""
        try:
            open_braces = json_text.count('{')
            close_braces = json_text.count('}')
            open_brackets = json_text.count('[')
            close_brackets = json_text.count(']')

            fixed = json_text
            if open_brackets > close_brackets:
                fixed += ']' * (open_brackets - close_brackets)
            if open_braces > close_braces:
                fixed += '}' * (open_braces - close_braces)

            return json.loads(fixed)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"[LLM仲裁者] JSON修复失败: {e}")
            return None

    def _apply_adjustments(
        self,
        day_plans: List[Dict[str, Any]],
        adjustments: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        将LLM的调整建议应用到行程中

        Args:
            day_plans: 行程数据（深度拷贝后的，可安全修改）
            adjustments: 调整列表

        Returns:
            调整后的行程
        """
        for adj in adjustments:
            try:
                day = adj.get("day", 1)
                action = adj.get("action", "")
                target = adj.get("target", "")
                new_value = adj.get("to", "")

                if day < 1 or day > len(day_plans):
                    continue

                plan = day_plans[day - 1]

                if "景点" in action or "时间" in action:
                    # 调整景点时间
                    for attr in plan.get("attractions", []):
                        if not isinstance(attr, dict):
                            continue
                        if attr.get("name", "") == target:
                            if "->" in str(new_value) or "-" in str(new_value):
                                parts = new_value.replace("->", "-").split("-")
                                if len(parts) >= 2:
                                    attr["start_time"] = parts[0].strip()
                                    attr["end_time"] = parts[1].strip()
                            elif new_value:
                                attr["start_time"] = new_value
                            break

                elif "替换" in action and "景点" in action:
                    # 替换景点（标记移除，保留名称以提示替换）
                    for i, attr in enumerate(plan.get("attractions", [])):
                        if not isinstance(attr, dict):
                            continue
                        if attr.get("name", "") == target:
                            # 保留占位，name改为新名称
                            if new_value:
                                attr["name"] = new_value
                                attr["_llm_replaced"] = True
                            break

                elif "移动" in action:
                    # 跨天移动
                    target_day = self._parse_target_day(new_value)
                    if target_day and target_day != day and 1 <= target_day <= len(day_plans):
                        # 从当前天移除
                        moved_attr = None
                        for i, attr in enumerate(plan.get("attractions", [])):
                            if not isinstance(attr, dict):
                                continue
                            if attr.get("name", "") == target:
                                moved_attr = attr
                                plan["attractions"].pop(i)
                                break
                        # 添加到目标天
                        if moved_attr:
                            day_plans[target_day - 1].setdefault("attractions", []).append(moved_attr)

                elif "餐饮" in action or "用餐" in action:
                    # 调整餐饮时间
                    for meal in plan.get("meals", []):
                        if not isinstance(meal, dict):
                            continue
                        if meal.get("name", "") == target:
                            if new_value:
                                meal["start_time"] = new_value
                                meal["time"] = new_value
                            break

            except Exception as e:
                logger.warning(f"[LLM仲裁者] 应用调整失败: {adj.get('target', 'unknown')}: {e}")
                continue

        return day_plans

    def _parse_target_day(self, text: str) -> Optional[int]:
        """从文本中解析目标天数字"""
        import re
        match = re.search(r'第(\d+)天', str(text))
        if match:
            return int(match.group(1))
        match = re.search(r'day\s*(\d+)', str(text), re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None

    async def generate_counter_proposal(
        self,
        agent_id: str,
        current_plan: Dict[str, Any],
        conflict_description: str,
        preferences: Optional[List[str]] = None,
        session_id: str = "default",
    ) -> Optional[Dict[str, Any]]:
        """
        LLM驱动的反提案生成

        让Agent通过LLM理解冲突并生成替代方案，用于真正的多Agent谈判。

        Args:
            agent_id: 生成反提案的Agent ID
            current_plan: 当前Agent的推荐方案
            conflict_description: 冲突描述
            preferences: 用户偏好
            session_id: 会话ID

        Returns:
            反提案内容
        """
        if not self.enabled:
            return None

        prompt = f"""作为{agent_id}，你正在参与一个多智能体行程协商过程。

## 你的当前推荐
{json.dumps(current_plan, ensure_ascii=False, indent=2)}

## 冲突描述
{conflict_description}

## 用户偏好
{', '.join(preferences) if preferences else '未指定'}

请生成一个反提案（counter proposal）来解决上述冲突。
反提案应该尽量保留你的原始推荐，但做出必要的调整。

请返回JSON格式：
{{
    "analysis": "对冲突的分析",
    "proposed_changes": [
        {{
            "item": "要调整的项目",
            "current": "当前值",
            "proposed": "建议值",
            "reason": "调整理由"
        }}
    ],
    "expected_outcome": "预期的结果"
}}"""

        messages = [
            {"role": "system", "content": "你是一个专业的旅行规划智能体，擅长通过协商解决行程冲突。"},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await asyncio.wait_for(
                self._call_llm_with_retry(messages),
                timeout=self.timeout_seconds,
            )
            return response
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.warning(f"[LLM仲裁者] 反提案生成失败 ({agent_id}): {e}")
            return None


# ==================== 【新增】Contract Net Protocol（合同网协议） ====================

class ContractNetProtocol:
    """
    【新增】Contract Net Protocol（合同网协议）

    当LLM不可用时（API Key未配置、超时、异常等），
    使用此确定性的合同网协议作为兜底方案。

    流程:
    1. 招标阶段（announce）: dispatcher 将冲突作为"标的"发布给所有Agent
    2. 投标阶段（bid）: 各Agent评估自己能解决该冲突并投标
    3. 评标阶段（evaluate）: dispatcher 根据效用评估选择最优投标
    4. 授标阶段（award）: dispatcher 通知获胜Agent执行其方案

    核心设计:
    - 完全确定性：不依赖LLM，所有逻辑基于规则
    - 每个Agent根据其领域知识投标（景点Agent擅长时间调整，交通Agent擅长路线优化等）
    - 评标依据：投标方案的效用值（调用 utility_evaluator）
    - 设置最大轮次防止死循环

    使用方式:
        from src.services.negotiation_llm_arbiter import contract_net_protocol

        result = await contract_net_protocol.run_round(
            day_plans=current_plans,
            structured_requirement=structured_req,
            conflicts=remaining_conflicts,
            session_id=session_id,
        )

        返回格式:
        {
            "day_plans": 调整后的行程,
            "adjustments": 调整列表,
            "winning_bid": {
                "agent_id": "attractions_agent_001",
                "strategy": "strategy_time_shift",
                "utility": 0.85,
            },
            "all_bids": [...],
        }
    """

    def __init__(self):
        self.max_rounds = 3
        self.bid_timeout = 10.0  # 投标超时（秒）
        # 各Agent专长映射：agent_id -> {conflict_types, strategies, priority}
        # 用于合同网协议中Agent根据自身专长投标
        # 对应重构清单 4.2 节：Agent投票机制增强 + 反提案机制
        self.AGENT_EXPERTISE = {
            "attractions_agent_001": {
                "conflict_types": [
                    "time_overlap", "outside_opening_hours",
                    "closed_day", "too_short_duration", "too_long_duration",
                ],
                "strategies": [
                    "strategy_time_shift",
                    "strategy_swap_time_slot",
                    "strategy_compress_duration",
                    "strategy_replace_activity",
                    "strategy_cross_day_move",
                ],
                "priority": 1,
            },
            "food_agent_001": {
                "conflict_types": [
                    "unreasonable_meal_time", "time_overlap",
                    "budget_exceeded",
                ],
                "strategies": [
                    "strategy_time_shift",
                    "strategy_swap_time_slot",
                ],
                "priority": 2,
            },
            "transport_agent_001": {
                "conflict_types": [
                    "geo_distance", "geo_distance_warning",
                    "time_overlap", "overloaded_day",
                ],
                "strategies": [
                    "strategy_geo_distance_split",
                    "strategy_cross_day_move",
                    "strategy_transport_split",
                ],
                "priority": 3,
            },
            "hotel_agent_001": {
                "conflict_types": [
                    "unreasonable_time",
                ],
                "strategies": [
                    "strategy_time_shift",
                ],
                "priority": 4,
            },
        }
        logger.info("[合同网协议] 初始化完成")

    async def run_round(
        self,
        day_plans: List[Dict[str, Any]],
        structured_requirement: Dict[str, Any],
        conflicts: List[Dict[str, Any]],
        session_id: str = "default",
    ) -> Optional[Dict[str, Any]]:
        """
        执行一轮合同网协商

        流程: 招标 → 投标 → 评标 → 授标

        Args:
            day_plans: 当前行程
            structured_requirement: 结构化需求
            conflicts: 未能解决的冲突列表
            session_id: 会话ID

        Returns:
            协商结果（含调整后的行程），None表示全部失败
        """
        if not conflicts:
            return None

        from src.services.negotiation_event_bus import agent_message_bus, AgentMessageType
        from src.services.negotiation_core.strategy_executor import strategy_executor
        from src.services.negotiation_utility import compute_utility_dict
        from src.services.negotiation_core.conflict_detector import detect_conflicts

        plans = copy.deepcopy(day_plans)
        all_bids = []
        winning_bid = None
        best_utility = -1.0

        # ========== 阶段1: 招标（针对每个冲突） ==========
        for conflict in conflicts:
            conflict_type = conflict.get("type", "")
            day = conflict.get("day", 1)
            day_idx = day - 1

            if day_idx < 0 or day_idx >= len(plans):
                continue

            logger.info(
                f"[合同网] session={session_id}: 招标发布冲突 "
                f"type={conflict_type}, day={day}"
            )

            # ========== 阶段2: 投标 ==========
            bids = await self._collect_bids(
                conflict=conflict,
                day_plans=plans,
                day_idx=day_idx,
                structured_requirement=structured_requirement,
                session_id=session_id,
            )

            if not bids:
                logger.info(
                    f"[合同网] session={session_id}: 冲突 type={conflict_type} 无Agent投标"
                )
                continue

            all_bids.extend(bids)

            # ========== 阶段3: 评标 ==========
            for bid in bids:
                # 模拟应用投标方案并计算效用
                bid_plans = self._simulate_bid(
                    plans=plans,
                    day_idx=day_idx,
                    bid=bid,
                )

                if bid_plans is None:
                    continue

                # 计算效用
                utility = compute_utility_dict(bid_plans, structured_requirement)
                utility_value = self._calc_overall_utility(utility)

                bid_agent = bid.get("agent_id", "unknown")
                bid_strategy = bid.get("strategy", "unknown")

                logger.info(
                    f"[合同网] 评标: agent={bid_agent}, strategy={bid_strategy}, "
                    f"utility={utility_value:.4f}"
                )

                if utility_value > best_utility:
                    best_utility = utility_value
                    winning_bid = {
                        "agent_id": bid_agent,
                        "strategy": bid_strategy,
                        "utility": utility_value,
                        "plans_after": bid_plans,
                        "adjustments": bid.get("adjustments", []),
                    }

        if winning_bid is None:
            logger.info(f"[合同网] session={session_id}: 所有冲突均无有效投标")
            return None

        # ========== 阶段4: 授标 ==========
        logger.info(
            f"[合同网] session={session_id}: 授标给 "
            f"agent={winning_bid['agent_id']}, strategy={winning_bid['strategy']}, "
            f"utility={winning_bid['utility']:.4f}"
        )

        # 通知获胜Agent（广播事件）
        try:
            await agent_message_bus.broadcast(
                from_agent="dispatcher",
                message={
                    "type": AgentMessageType.SCHEDULE_PROPOSAL,
                    "payload": {
                        "action": "contract_award",
                        "session_id": session_id,
                        "winning_agent": winning_bid["agent_id"],
                        "strategy": winning_bid["strategy"],
                        "adjustments": winning_bid["adjustments"],
                        "all_bids": [
                            {"agent_id": b["agent_id"], "strategy": b["strategy"]}
                            for b in all_bids
                        ],
                    }
                },
                session_id=session_id,
            )
        except Exception as e:
            logger.warning(f"[合同网] Agent广播失败（非致命）: {e}")

        # 应用最优方案
        final_plans = winning_bid.get("plans_after", plans)

        # 验证授标后的结果
        detection_after = detect_conflicts(final_plans, structured_requirement)
        logger.info(
            f"[合同网] session={session_id}: 授标后剩余 "
            f"{detection_after.error_count} 个error冲突"
        )

        return {
            "day_plans": final_plans,
            "adjustments": winning_bid.get("adjustments", []),
            "winning_bid": {
                "agent_id": winning_bid["agent_id"],
                "strategy": winning_bid["strategy"],
                "utility": winning_bid["utility"],
            },
            "all_bids": [
                {
                    "agent_id": b["agent_id"],
                    "strategy": b["strategy"],
                    "conflict_type": b.get("conflict_type", ""),
                }
                for b in all_bids
            ],
            "method": "contract_net",
        }

    async def _collect_bids(
        self,
        conflict: Dict[str, Any],
        day_plans: List[Dict[str, Any]],
        day_idx: int,
        structured_requirement: Dict[str, Any],
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """
        收集各Agent对某个冲突的投标

        每个Agent根据其领域知识（AGENT_EXPERTISE）评估自己能解决该冲突，
        并返回建议的策略和预期调整。

        Args:
            conflict: 冲突信息
            day_plans: 当前行程
            day_idx: 当前day索引
            structured_requirement: 结构化需求
            session_id: 会话ID

        Returns:
            投标列表
        """
        conflict_type = conflict.get("type", "")
        bids = []

        # 遍历所有Agent，检查其专长是否匹配此冲突类型
        for agent_id, expertise in self.AGENT_EXPERTISE.items():
            # 检查Agent的专长是否匹配此冲突类型
            if expertise["conflict_types"]:
                if conflict_type not in expertise["conflict_types"]:
                    continue

            # Agent投标：从可用策略中选择最佳匹配策略
            chosen_strategy = None
            from src.services.negotiation_strategies import strategy_selector, register_default_strategies
            # 确保策略已注册（首次使用时自动注册）
            if strategy_selector.registry.strategy_count == 0:
                register_default_strategies(strategy_selector)
            for strategy in expertise["strategies"]:
                if strategy_selector.registry.has_adapter(strategy):
                    chosen_strategy = strategy
                    break

            if chosen_strategy is None:
                continue

            # 构建投标
            bid = {
                "agent_id": agent_id,
                "strategy": chosen_strategy,
                "conflict_type": conflict_type,
                "priority": expertise["priority"],
                "adjustments": [],
            }

            # 生成调整描述
            try:
                activities = conflict.get("activities", [])
                target_name = activities[0] if activities else "未知活动"
                adjustment = {
                    "field": "合同网投标",
                    "item_name": target_name,
                    "before": conflict.get("description", ""),
                    "after": f"{agent_id}建议使用{chosen_strategy}策略修复",
                    "strategy": chosen_strategy,
                }
                bid["adjustments"].append(adjustment)
            except Exception:
                pass

            bids.append(bid)

        return bids

    def _simulate_bid(
        self,
        plans: List[Dict[str, Any]],
        day_idx: int,
        bid: Dict[str, Any],
    ) -> Optional[List[Dict[str, Any]]]:
        """
        模拟应用投标方案，返回应用后的行程

        Args:
            plans: 当前行程
            day_idx: 当前day索引
            bid: 投标信息

        Returns:
            应用投标后的行程，失败返回None
        """
        from src.services.negotiation_core.strategy_executor import strategy_executor

        strategy_name = bid.get("strategy", "")
        if not strategy_name:
            return None

        # 构造冲突对象（简化版）
        conflict = {
            "type": bid.get("conflict_type", "unknown"),
            "activities": [],
        }
        conflict_type = bid.get("conflict_type", "unknown")

        try:
            # 通过StrategyExecutor执行该策略
            result, is_multi_day = strategy_executor.execute_strategy(
                strategy_info={"name": strategy_name, "func": None},
                day_plans=plans,
                day_idx=day_idx,
                conflict=conflict,
                conflict_type=conflict_type,
                backup_attractions=[],
                structured_requirement={},
            )

            if result is not None:
                bid_plans = strategy_executor.apply_strategy_result(
                    day_plans=copy.deepcopy(plans),
                    day_idx=day_idx,
                    result=result,
                    is_multi_day=is_multi_day,
                    strategy_name=strategy_name,
                )
                return bid_plans

        except Exception as e:
            logger.warning(
                f"[合同网] 模拟投标失败: agent={bid.get('agent_id')}, "
                f"strategy={strategy_name}: {e}"
            )

        return None

    def _calc_overall_utility(self, utility_dict: Dict[str, Any]) -> float:
        """
        从效用字典中计算总体效用值

        Args:
            utility_dict: compute_utility_dict() 的返回值

        Returns:
            总体效用值（0~1之间）
        """
        if not isinstance(utility_dict, dict):
            return 0.0

        # 尝试获取总效用值
        overall = (
            utility_dict.get("overall_utility") or
            utility_dict.get("total") or
            utility_dict.get("utility", 0)
        )

        # 如果是数值直接返回
        if isinstance(overall, (int, float)):
            return float(overall)

        # 尝试从维度加权计算
        dimensions = [
            utility_dict.get("geo_compactness", 0.5),
            utility_dict.get("budget_conformance", 0.5),
            utility_dict.get("time_compactness", 0.5),
            utility_dict.get("preference_match", 0.5),
        ]
        return sum(dimensions) / len(dimensions)


# 全局单例
contract_net_protocol = ContractNetProtocol()
llm_arbiter = LLMArbiter()

