"""
住宿推荐智能体
"""
from typing import Dict, Any, List, Optional
from .base_agent import BaseAgent

class HotelAgent(BaseAgent):
    """住宿推荐智能体"""

    def __init__(self):
        super().__init__(
            agent_id="hotel_agent_001",
            name="住宿推荐助手",
            description="为用户推荐合适的酒店和住宿方案"
        )
        self._async_init_done = False
        
    async def async_init(self):
        """异步初始化：注册消息处理器，启用Agent间通信"""
        if self._async_init_done:
            return
        await self.register_message_handlers()
        self._async_init_done = True
        print(f"住宿Agent ({self.agent_id}) 消息处理器已注册")
        
    def get_capabilities(self) -> List[str]:
        return [
            "酒店推荐",
            "住宿方案规划",
            "价格查询",
            "位置评估"
        ]

    async def execute(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行住宿推荐任务"""
        import time
        import uuid
        from datetime import datetime

        start_time = time.time()
        task_id = task_data.get("task_id", f"hotel_{uuid.uuid4().hex[:8]}")

        # 提取任务参数
        city_name = task_data.get("city_name", "")
        check_in_date = task_data.get("check_in_date", "")
        nights = task_data.get("nights")
        check_out_date = task_data.get("check_out_date")
        budget_per_night = task_data.get("budget_per_night")
        location_preference = task_data.get("location_preference")

        # 计算住宿天数
        if not nights and check_in_date and check_out_date:
            try:
                check_in = datetime.strptime(check_in_date, "%Y-%m-%d")
                check_out = datetime.strptime(check_out_date, "%Y-%m-%d")
                nights = (check_out - check_in).days
            except:
                nights = 1
        elif not nights:
            nights = 1

        # 构建系统提示词
        system_prompt = """你是一个专业的住宿推荐助手。请为用户推荐合适的酒店。

要求：
1. 推荐的酒店要符合用户预算和位置偏好
2. 提供准确的评分和价格信息
3. 包含实用信息（位置、设施等）
4. 考虑性价比和用户评价

返回格式：
{
  "hotels": [
    {
      "hotel_id": "hotel_001",
      "name": "酒店名称",
      "city_name": "城市名称",
      "location": "详细地址",
      "price_per_night": 每晚价格（数字）,
      "rating": 评分（0-5）,
      "amenities": ["设施1", "设施2"]
    }
  ]
}"""

        # 构建用户提示词
        budget_hint = f"每晚预算：{budget_per_night}元" if budget_per_night else "无预算限制"
        location_hint = f"位置偏好：{location_preference}" if location_preference else "无特殊位置要求"

        user_prompt = f"""请为以下住宿需求推荐酒店：

城市：{city_name}
入住日期：{check_in_date}
住宿天数：{nights}晚
{budget_hint}
{location_hint}

请推荐3-5家不同档次的酒店供用户选择。
每个酒店必须包含：
- 唯一ID（hotel_id，hotel_xxx格式）
- 酒店名称
- 城市名称（与目的地一致）
- 详细地址
- 每晚价格
- 评分（0-5）
- 设施列表"""

        # 调用LLM
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response_content = await self.call_llm(messages, max_tokens=2500)
            result = self._parse_json_response(response_content)

            processing_time = (time.time() - start_time) * 1000

            return {
                "task_id": task_id,
                "status": "success",
                "data": {
                    "items": result.get("hotels", [])
                },
                "metadata": {
                    "processing_time_ms": processing_time,
                    "source": "ai_generated",
                    "model_used": "deepseek-chat",
                    "over_budget": False
                },
                "error_message": None
            }
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            return {
                "task_id": task_id,
                "status": "failed",
                "data": {"items": []},
                "metadata": {
                    "processing_time_ms": processing_time,
                    "source": "ai_generated",
                    "model_used": "deepseek-chat",
                    "over_budget": False
                },
                "error_message": str(e)
            }

    # ==================== 【改造方案 4.1】Agent间信息共享 ====================

    async def share_info(self, session_id: str, hotels: List[dict]) -> None:
        """
        分享住宿信息到共享池（改造方案 4.1.2）

        Args:
            session_id: 会话ID
            hotels: 酒店列表
        """
        from src.services.negotiation_event_bus import agent_message_bus

        info = {
            "hotels": [
                {
                    "name": h.get("name", ""),
                    "location_type": h.get("location_type", ""),
                    "price_per_night": h.get("price_per_night", 0),
                    "rating": h.get("rating", 0),
                    "area": h.get("area", ""),
                }
                for h in hotels
                if isinstance(h, dict)
            ]
        }
        await agent_message_bus.share_agent_info(
            agent_id=self.agent_id,
            session_id=session_id,
            info_type="hotel_info",
            info_data=info,
        )

    # ==================== Agent间消息处理 ====================

    async def on_message(self, message: dict) -> Optional[dict]:
        """
        处理来自其他Agent的消息（支持投票和协商）
        """
        payload = message.get("payload", {})
        if payload.get("action") == "consensus_vote":
            return await self._handle_vote(payload)
        if payload.get("action") == "conflict_bid":
            return await self._handle_bid(payload)
        if payload.get("action") == "consult_conflict":
            return await self._handle_consult(payload)
        if payload.get("action") == "counter_proposal":
            return await self._handle_counter_proposal(payload)
        # === 【阶段B】反提案评估 + 条件回应 ===
        if payload.get("action") == "evaluate_counter_proposal":
            return await self._handle_evaluate_counter_proposal(payload)
        if payload.get("action") == "respond_to_condition":
            return await self._handle_respond_to_condition(payload)
        return await super().on_message(message)

    async def _handle_vote(self, payload: dict) -> dict:
        """
        处理投票请求——检查住宿安排是否受影响。
        否决条件：住宿费用超预算20%以上，或位置不合理。
        """
        proposed_summary = payload.get("proposed_day_summary", {})
        proposed_attrs = proposed_summary.get("attractions", [])
        proposed_meals = proposed_summary.get("meals", [])

        import re
        # 如果景点被安排到太早或太晚，住宿位置可能不合适
        early_count = 0
        late_count = 0
        for attr_desc in proposed_attrs:
            time_match = re.findall(r'\((\d{2}:\d{2})-(\d{2}:\d{2})\)', attr_desc)
            if time_match:
                start_h = int(time_match[0][0].split(":")[0])
                end_h = int(time_match[0][1].split(":")[0])
                if start_h < 7:
                    early_count += 1
                if end_h > 21:
                    late_count += 1

        if early_count >= 2 and late_count >= 2:
            return {"vote": "veto", "agent_id": self.agent_id,
                    "reason": "景点安排过早和过晚，酒店位置可能不便利"}

        # 检查餐饮时间是否合理
        for meal_desc in proposed_meals:
            time_match = re.search(r'\((\d{2}:\d{2})\)', meal_desc)
            if time_match:
                hour = int(time_match.group(1).split(":")[0])
                if hour >= 22:
                    return {"vote": "veto", "agent_id": self.agent_id,
                            "reason": f"餐饮{meal_desc}安排在22点后，回酒店不便"}

        return {"vote": "approve", "agent_id": self.agent_id}

    async def _handle_consult(self, payload: dict) -> dict:
        """处理冲突咨询"""
        conflict_type = payload.get("conflict_type", "")

        if conflict_type == "unreasonable_time":
            return {
                "suggested_strategy": "strategy_time_shift",
                "suggested_params": {},
                "veto_strategies": [],
            }
        elif conflict_type == "geo_distance":
            return {
                "suggested_strategy": "strategy_geo_distance_split",
                "suggested_params": {},
                "veto_strategies": [],
            }

        return {"suggested_strategy": None, "suggested_params": {}, "veto_strategies": []}

    async def _handle_counter_proposal(self, payload: dict) -> dict:
        """处理反提案请求"""
        conflict = payload.get("conflict", {})
        conflict_type = conflict.get("type", "")

        strategy = "strategy_time_shift" if conflict_type == "unreasonable_time" else "strategy_time_shift"

        return {
            "proposal_author": self.agent_id,
            "strategy": strategy,
            "params": {},
            "adjustments": [{"field": "策略建议", "item_name": conflict_type, "before": "未修复", "after": f"建议{strategy}"}],
            "expected_effect": f"住宿Agent建议使用{strategy}解决{conflict_type}冲突",
        }

    async def _handle_bid(self, payload: dict) -> dict:
        """
        【改造方案 4.2.5】冲突招标 — 住宿Agent投标

        改造后: 从共享信息池读取景点位置，
        用LLM生成考虑住宿便利性的投标方案。

        Args:
            payload: {"conflict": {...}, "session_id": str, "day_num": int}

        Returns:
            {"strategy": str, "params": dict, "expected_utility": float, "analysis": str}
        """
        import os
        conflict = payload.get("conflict", {})
        conflict_type = conflict.get("type", "")
        session_id = payload.get("session_id", "")
        day_num = payload.get("day_num", 1)

        # 读取共享信息池
        from src.services.negotiation_event_bus import agent_message_bus
        shared_info = agent_message_bus.get_shared_agent_info(session_id)

        # 如果没有LLM密钥，降级到原有的硬编码映射
        if not os.getenv("DEEPSEEK_API_KEY"):
            return self._handle_bid_fallback(payload)

        try:
            llm_prompt = self._build_bidding_prompt(
                conflict=conflict,
                conflict_type=conflict_type,
                day_num=day_num,
                shared_info=shared_info,
            )
            response_content = await self.call_llm(
                [{"role": "user", "content": llm_prompt}],
                max_tokens=1024,
            )
            bid_result = self._parse_json_response(response_content)

            strategy = bid_result.get("strategy", "")
            if strategy not in (
                "strategy_time_shift", "strategy_swap_time_slot",
                "strategy_cross_day_move", "strategy_geo_distance_split",
                "strategy_replace_activity", "strategy_compress_duration",
            ):
                return self._handle_bid_fallback(payload)

            return {
                "strategy": strategy,
                "params": bid_result.get("params", {}),
                "expected_utility": float(bid_result.get("expected_utility", 0.5)),
                "analysis": bid_result.get("analysis", f"住宿Agent建议{strategy}解决{conflict_type}冲突"),
            }

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"[住宿Agent] LLM投标失败，降级到硬编码映射: {e}")
            return self._handle_bid_fallback(payload)

    def _build_bidding_prompt(
        self,
        conflict: dict,
        conflict_type: str,
        day_num: int,
        shared_info: dict,
    ) -> str:
        """构造LLM投标提示词，基于景点位置和住宿信息生成投标方案"""
        conflict_desc = conflict.get("description", "") or conflict.get("conflict_description", "")
        activities = conflict.get("activities", [])

        # 提取景点和交通信息
        attractions_summary = ""
        transport_summary = ""
        hotel_self_summary = ""
        try:
            # 景点信息
            attr_data = shared_info.get("attractions_agent_001", {}).get("data", {})
            all_attrs = attr_data.get("attractions", [])
            if all_attrs:
                attr_lines = []
                for a in all_attrs[:6]:
                    name = a.get("name", "")
                    slot = a.get("recommended_time_slot", "?")
                    loc = a.get("location", {})
                    lat = loc.get("lat", "?") if isinstance(loc, dict) else "?"
                    lng = loc.get("lng", "?") if isinstance(loc, dict) else "?"
                    attr_lines.append(f"  {name}: 建议时段={slot}, 位置=({lat},{lng})")
                attractions_summary = "\n".join(attr_lines)

            # 交通信息
            transport_data = shared_info.get("transport_agent_001", {}).get("data", {})
            transport_times = transport_data.get("transport_times", {})
            if transport_times:
                sample_keys = list(transport_times.keys())[:5]
                transport_lines = []
                for key in sample_keys:
                    info = transport_times[key]
                    transport_lines.append(f"  {key}: {info.get('duration_min', '?')}分钟")
                transport_summary = "\n".join(transport_lines)

            # 自身住宿信息
            hotel_data = shared_info.get("hotel_agent_001", {}).get("data", {})
            hotels = hotel_data.get("hotels", [])
            if hotels:
                hotel_lines = []
                for h in hotels[:4]:
                    name = h.get("name", "")
                    addr = h.get("address", "")
                    rating = h.get("rating", "?")
                    hotel_lines.append(f"  {name}: 地址={addr}, 评分={rating}")
                hotel_self_summary = "\n".join(hotel_lines)
        except Exception:
            pass

        prompt = f"""你是一个专业的{self.name}（住宿Agent），请分析以下行程冲突，基于住宿便利性知识生成投标方案。

【冲突信息】
- 冲突类型: {conflict_type}
- 涉及活动: {', '.join(activities) if activities else '未知'}
- 描述: {conflict_desc}
- 第{day_num}天

【景点位置信息】
{attractions_summary if attractions_summary else '(无景点信息)'}

【景点间交通时间】
{transport_summary if transport_summary else '(无交通信息)'}

【当前住宿信息】
{hotel_self_summary if hotel_self_summary else '(无住宿信息)'}

【可选的解决策略】
1. strategy_time_shift - 时间平移（调整活动时间使早出晚归更合理）
2. strategy_swap_time_slot - 交换时段（将行程集中到白天避免深夜回酒店）
3. strategy_cross_day_move - 跨天移动（将距离酒店远的景点集中到一天）
4. strategy_geo_distance_split - 地理拆分（避免景点分散在不同区域）

【你的任务】
分析冲突，选择最合适的策略，关注：
- 晚上最后的活动是否能在22:00前结束方便回酒店
- 景点是否集中在酒店附近区域
- 早出和晚归是否合理

请返回JSON格式（只返回JSON，不要其他文字）:
{{
  "strategy": "选择的策略名称",
  "params": {{}},
  "expected_utility": 0.0-1.0的浮点数（越高越有效）,
  "analysis": "简要分析为什么选择这个策略"
}}"""
        return prompt

    def _handle_bid_fallback(self, payload: dict) -> dict:
        """LLM不可用时的降级方案：原有的硬编码策略映射"""
        conflict = payload.get("conflict", {})
        conflict_type = conflict.get("type", "")

        strategy_map = {
            "geo_distance": ("strategy_geo_distance_split", 0.55),
            "unreasonable_time": ("strategy_time_shift", 0.65),
        }
        strategy, utility = strategy_map.get(conflict_type, ("strategy_time_shift", 0.30))
        return {
            "strategy": strategy,
            "params": {},
            "expected_utility": utility,
            "analysis": f"住宿Agent建议{strategy}解决{conflict_type}冲突",
        }


# ==================== 模块级便捷函数 ====================

_shared_hotel_agent: Optional[HotelAgent] = None


def _get_hotel_agent() -> HotelAgent:
    """获取住宿Agent单例"""
    global _shared_hotel_agent
    if _shared_hotel_agent is None:
        _shared_hotel_agent = HotelAgent()
    return _shared_hotel_agent


async def share_info(session_id: str, hotels: List[dict]) -> None:
    """
    模块级便捷函数：分享住宿信息到共享池

    供 negotiate_and_fix() 调用，无需实例化 Agent。
    """
    agent = _get_hotel_agent()
    await agent.share_info(session_id, hotels)
