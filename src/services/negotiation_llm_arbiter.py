"""
LLM仲裁者 — 当规则化策略全部失败时，让LLM创造性解决

功能:
1. ✅ 当所有确定性策略都失败时，调用LLM生成创造性解决方案
2. ✅ LLM驱动的反提案：让Agent通过LLM理解并生成替代方案
3. ✅ 超时保护和降级机制
4. ✅ 完整的prompt模板和上下文构建

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
"""
import json
import copy
import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from src.services.deepseek_client import DeepSeekClient

logger = logging.getLogger(__name__)


# ==================== Prompt 模板 ====================

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


# ==================== LLM 仲裁者 ====================

class LLMArbiter:
    """
    LLM仲裁者

    当规则化策略全部失败时，调用LLM生成创造性解决方案。
    支持超时保护和降级机制。
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


# ==================== 全局单例 ====================

llm_arbiter = LLMArbiter()
