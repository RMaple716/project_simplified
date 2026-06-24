"""
交通推荐智能体（增强版 — 支持Agent间协商）
"""
import time
import uuid
from typing import Dict, Any, List, Optional
from .base_agent import BaseAgent
from src.services.navigation_service import navigation_service

class TransportAgent(BaseAgent):
    """交通推荐智能体"""

    def __init__(self):
        super().__init__(
            agent_id="transport_agent_001",
            name="交通规划助手",
            description="为用户提供交通方案推荐"
        )
        self._async_init_done = False

    async def async_init(self):
        """异步初始化：注册消息处理器，启用Agent间通信"""
        if self._async_init_done:
            return
        await self.register_message_handlers()
        self._async_init_done = True
        print(f"交通Agent ({self.agent_id}) 消息处理器已注册")

    def get_capabilities(self) -> List[str]:
        return [
            "交通方案推荐",
            "路线规划",
            "票价查询",
            "时刻表查询"
        ]

    async def execute(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行交通推荐任务"""
        import os
        import logging

        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)

        start_time = time.time()
        task_id = task_data.get("task_id", f"trans_{uuid.uuid4().hex[:8]}")

        logger.info(f"[Transport] 开始执行任务 {task_id}")

        # 提取任务参数
        from_location = task_data.get("from_location", {})
        to_location = task_data.get("to_location", {})
        mode_preference = task_data.get("mode_preference", "driving")  # walking/transit/driving

        logger.info(f"[Transport] 任务参数 - 起点: {from_location}, 终点: {to_location}, 模式: {mode_preference}")

        # 如果没有配置API密钥，返回模拟数据
        if not os.getenv("AMAP_API_KEY"):
            logger.warning("[Transport] 未配置API密钥，返回模拟数据")
            return self._get_mock_data(task_id, from_location, to_location, start_time, None)

        # 获取起点和终点的坐标或名称
        from_name = from_location.get("name", "")
        to_name = to_location.get("name", "")
        from_coords = from_location.get("coords", "")
        to_coords = to_location.get("coords", "")

        # 如果没有提供坐标，尝试通过地址获取坐标
        if not from_coords and from_name:
            logger.info(f"[Transport] 正在获取起点坐标: {from_name}")
            from_coords = await navigation_service.geocode(from_name)
            logger.info(f"[Transport] 起点坐标: {from_coords}")
        if not to_coords and to_name:
            logger.info(f"[Transport] 正在获取终点坐标: {to_name}")
            to_coords = await navigation_service.geocode(to_name)
            logger.info(f"[Transport] 终点坐标: {to_coords}")

        # 优先使用坐标，如果没有则使用名称
        origin = from_coords if from_coords else from_name
        destination = to_coords if to_coords else to_name

        # 如果无法获取坐标，返回模拟数据
        if not origin or not destination:
            logger.warning(f"[Transport] 无法获取坐标 - 起点: {origin}, 终点: {destination}")
            return self._get_mock_data(task_id, from_location, to_location, start_time, "无法获取地址坐标")

        # 调用导航API
        try:
            logger.info(f"[Transport] 调用导航API - 起点: {origin}, 终点: {destination}, 模式: {mode_preference}")
            nav_result = await navigation_service.get_direction(
                origin=origin,
                destination=destination,
                mode=mode_preference
            )
            logger.info(f"[Transport] API返回结果: {nav_result}")

            if nav_result['status'] == 'success':
                route_data = nav_result['data']

                # 构建交通方案
                transport_option = {
                    "transport_id": f"trans_{uuid.uuid4().hex[:8]}",
                    "type": mode_preference,
                    "from": from_name,
                    "to": to_name,
                    "distance": route_data['distance'],
                    "distance_text": navigation_service.format_distance(route_data['distance']),
                    "duration": route_data['duration'],
                    "duration_text": navigation_service.format_duration(route_data['duration']),
                    "steps": route_data['steps'],
                    "polyline": route_data.get('polyline', '')
                }

                processing_time = (time.time() - start_time) * 1000

                return {
                    "task_id": task_id,
                    "status": "success",
                    "data": {
                        "items": [transport_option],
                    },
                    "metadata": {
                        "processing_time_ms": processing_time,
                        "source": "api_generated",
                        "model_used": "amap_navigation",
                        "over_budget": False
                    },
                    "error_message": None
                }
            else:
                # API调用失败，返回模拟数据
                return self._get_mock_data(task_id, from_location, to_location, start_time, nav_result.get('message', '未知错误'))

        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            return {
                "task_id": task_id,
                "status": "failed",
                "data": {"items": []},
                "metadata": {
                    "processing_time_ms": processing_time,
                    "source": "api_generated",
                    "model_used": "amap_navigation",
                    "over_budget": False
                },
                "error_message": str(e)
            }

    def _get_mock_data(self, task_id: str, from_location: Dict[str, Any], 
                       to_location: Dict[str, Any], start_time: float, 
                       error_msg: Optional[str] = None) -> Dict[str, Any]:
        """返回模拟数据"""
        from_name = from_location.get("name", "起点")
        to_name = to_location.get("name", "终点")

        mock_option = {
            "transport_id": f"trans_{uuid.uuid4().hex[:8]}",
            "type": "driving",
            "from": from_name,
            "to": to_name,
            "distance": 5000,
            "distance_text": "5.0公里",
            "duration": 900,
            "duration_text": "15分钟",
            "steps": [
                {
                    "instruction": f"从{from_name}出发",
                    "distance": 5000,
                    "duration": 900,
                    "polyline": ""
                }
            ],
            "polyline": ""
        }

        processing_time = (time.time() - start_time) * 1000

        return {
            "task_id": task_id,
            "status": "success",
            "data": {
                "items": [mock_option]
            },
            "metadata": {
                "processing_time_ms": processing_time,
                "source": "mock_data",
                "model_used": None,
                "over_budget": False
            },
            "error_message": error_msg
        }

    # ==================== 【改造方案 4.1】Agent间信息共享 ====================

    async def share_info(self, session_id: str, day_plans: List[dict]) -> None:
        """
        分享交通信息到共享池（改造方案 4.1.2）

        分析行程中的景点间交通时间，共享给其他 Agent。

        Args:
            session_id: 会话ID
            day_plans: 每日行程列表
        """
        from src.services.negotiation_event_bus import agent_message_bus

        transport_info = {
            "transport_times": {},
            "recommended_routes": {},
        }

        for plan in day_plans:
            attrs = plan.get("attractions", [])
            valid = [a for a in attrs if isinstance(a, dict)]
            for i in range(len(valid) - 1):
                a = valid[i]
                b = valid[i + 1]
                a_name = a.get("name", "")
                b_name = b.get("name", "")
                key = f"{a_name}→{b_name}"

                a_loc = a.get("location", {})
                b_loc = b.get("location", {})
                if isinstance(a_loc, dict) and isinstance(b_loc, dict):
                    lat1 = a_loc.get("lat")
                    lng1 = a_loc.get("lng")
                    lat2 = b_loc.get("lat")
                    lng2 = b_loc.get("lng")
                    if lat1 and lng1 and lat2 and lng2:
                        import math
                        # 估算交通时间（按 25km/h 的平均速度）
                        dlat = math.radians(float(lat2) - float(lat1))
                        dlng = math.radians(float(lng2) - float(lng1))
                        a_sin = math.sin(dlat / 2) ** 2 + math.cos(math.radians(float(lat1))) * math.cos(math.radians(float(lat2))) * math.sin(dlng / 2) ** 2
                        c = 2 * math.atan2(math.sqrt(a_sin), math.sqrt(1 - a_sin))
                        dist_km = 6371 * c
                        duration_min = int((dist_km / 25) * 60)

                        transport_info["transport_times"][key] = {
                            "distance_km": round(dist_km, 1),
                            "duration_min": duration_min,
                            "mode": "transit",
                        }

        await agent_message_bus.share_agent_info(
            agent_id=self.agent_id,
            session_id=session_id,
            info_type="transport_info",
            info_data=transport_info,
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
        处理投票请求——检查交通方案是否受影响。
        否决条件：交通时间显著延长或路线顺序不合理。
        """
        proposed_summary = payload.get("proposed_day_summary", {})
        proposed_attrs = proposed_summary.get("attractions", [])
        original_summary = payload.get("original_day_summary", {})
        original_attrs = original_summary.get("attractions", [])

        if len(proposed_attrs) != len(original_attrs):
            return {"vote": "veto", "agent_id": self.agent_id,
                    "reason": f"景点数量从{len(original_attrs)}变为{len(proposed_attrs)}，需重规划路线"}

        proposed_names = [a.split("(")[0].strip() for a in proposed_attrs]
        original_names = [a.split("(")[0].strip() for a in original_attrs]

        for i, name in enumerate(original_names):
            if name in proposed_names:
                new_pos = proposed_names.index(name)
                if abs(new_pos - i) > 1:
                    return {"vote": "veto", "agent_id": self.agent_id,
                            "reason": f"'{name}'从第{i+1}位调至第{new_pos+1}位，会导致绕路"}

        return {"vote": "approve", "agent_id": self.agent_id}

    async def _handle_consult(self, payload: dict) -> dict:
        """处理冲突咨询"""
        conflict_type = payload.get("conflict_type", "")

        if conflict_type == "geo_distance":
            return {
                "suggested_strategy": "strategy_geo_distance_split",
                "suggested_params": {},
                "veto_strategies": ["strategy_compress_duration"],
            }
        elif conflict_type == "geo_distance_warning":
            return {
                "suggested_strategy": "strategy_cross_day_move",
                "suggested_params": {},
                "veto_strategies": [],
            }
        elif conflict_type == "time_overlap":
            return {
                "suggested_strategy": "strategy_swap_time_slot",
                "suggested_params": {},
                "veto_strategies": [],
            }
        elif conflict_type == "overloaded_day":
            return {
                "suggested_strategy": "strategy_cross_day_move",
                "suggested_params": {},
                "veto_strategies": [],
            }

        return {"suggested_strategy": None, "suggested_params": {}, "veto_strategies": []}

    async def _handle_counter_proposal(self, payload: dict) -> dict:
        """处理反提案请求"""
        conflict = payload.get("conflict", {})
        conflict_type = conflict.get("type", "")

        strategy_map = {
            "geo_distance": "strategy_geo_distance_split",
            "geo_distance_warning": "strategy_cross_day_move",
            "time_overlap": "strategy_swap_time_slot",
            "overloaded_day": "strategy_cross_day_move",
        }

        strategy = strategy_map.get(conflict_type, "strategy_time_shift")

        return {
            "proposal_author": self.agent_id,
            "strategy": strategy,
            "params": {},
            "adjustments": [{"field": "策略建议", "item_name": conflict_type, "before": "未修复", "after": f"建议{strategy}"}],
            "expected_effect": f"交通Agent建议使用{strategy}解决{conflict_type}冲突",
        }

    async def _handle_bid(self, payload: dict) -> dict:
        """
        【改造方案 4.2.5】冲突招标 — 交通Agent投标

        改造后: 从共享信息池读取景点和餐饮位置，
        用LLM生成考虑真实交通条件的投标方案。

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

            # 验证返回的有效性
            strategy = bid_result.get("strategy", "")
            if strategy not in (
                "strategy_time_shift", "strategy_swap_time_slot",
                "strategy_cross_day_move", "strategy_geo_distance_split",
                "strategy_replace_activity", "strategy_compress_duration",
            ):
                return self._handle_bid_fallback(payload)

            return {
                "strategy": strategy,
                "params": bid_result.get("params", {"mode": "transit"}),
                "expected_utility": float(bid_result.get("expected_utility", 0.5)),
                "analysis": bid_result.get("analysis", f"交通Agent建议{strategy}解决{conflict_type}冲突"),
            }

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"[交通Agent] LLM投标失败，降级到硬编码映射: {e}")
            return self._handle_bid_fallback(payload)

    def _build_bidding_prompt(
        self,
        conflict: dict,
        conflict_type: str,
        day_num: int,
        shared_info: dict,
    ) -> str:
        """构造LLM投标提示词，基于景点位置和交通信息生成投标方案"""
        conflict_desc = conflict.get("description", "") or conflict.get("conflict_description", "")
        activities = conflict.get("activities", [])

        # 提取景点位置信息
        attractions_info_summary = ""
        transport_self_summary = ""
        try:
            # 读取景点Agent的共享信息
            attr_data = shared_info.get("attractions_agent_001", {}).get("data", {})
            all_attrs = attr_data.get("attractions", [])
            if all_attrs:
                attr_lines = []
                for a in all_attrs[:8]:
                    loc = a.get("location", {})
                    lat = loc.get("lat", "?")
                    lng = loc.get("lng", "?")
                    name = a.get("name", "")
                    attr_lines.append(f"  {name} (位置: {lat},{lng})")
                attractions_info_summary = "\n".join(attr_lines)

            # 读取自身的交通时间估算
            transport_data = shared_info.get("transport_agent_001", {}).get("data", {})
            transport_times = transport_data.get("transport_times", {})
            if transport_times:
                sample_keys = list(transport_times.keys())[:8]
                transport_lines = []
                for key in sample_keys:
                    info = transport_times[key]
                    transport_lines.append(
                        f"  {key}: {info.get('distance_km', '?')}km, 约{info.get('duration_min', '?')}分钟, 交通方式={info.get('mode', 'transit')}"
                    )
                transport_self_summary = "\n".join(transport_lines)
        except Exception:
            pass

        prompt = f"""你是一个专业的{self.name}（交通Agent），请分析以下行程冲突，基于交通规划知识生成投标方案。

【冲突信息】
- 冲突类型: {conflict_type}
- 涉及活动: {', '.join(activities) if activities else '未知'}
- 描述: {conflict_desc}
- 第{day_num}天

【景点位置信息】
{attractions_info_summary if attractions_info_summary else '(无景点位置信息)'}

【已有交通时间估算】
{transport_self_summary if transport_self_summary else '(无交通时间数据)'}

【可选的解决策略】
1. strategy_time_shift - 时间平移（调整出发/到达时间避开拥堵或匹配开放时间）
2. strategy_swap_time_slot - 交换时段（将上午/下午的景点互换以优化路线）
3. strategy_cross_day_move - 跨天移动（将路途远的景点移到另一天集中游览）
4. strategy_geo_distance_split - 地理拆分（将不在同一片区的景点分到不同时段/天）
5. strategy_compress_duration - 压缩时长（减少交通中转时间）

【你的任务】
分析冲突，选择最合适的策略，关注：
- 景点之间的地理距离和交通时间
- 路线顺序是否合理（避免走回头路）
- 交通时间是否在合理范围内（单段<90分钟）

请返回JSON格式（只返回JSON，不要其他文字）:
{{
  "strategy": "选择的策略名称",
  "params": {{
    "mode": "transit"
  }},
  "expected_utility": 0.0-1.0的浮点数（越高越有效）,
  "analysis": "简要分析为什么选择这个策略"
}}"""
        return prompt

    def _handle_bid_fallback(self, payload: dict) -> dict:
        """LLM不可用时的降级方案：原有的硬编码策略映射"""
        conflict = payload.get("conflict", {})
        conflict_type = conflict.get("type", "")

        strategy_map = {
            "geo_distance": ("strategy_geo_distance_split", 0.75),
            "geo_distance_warning": ("strategy_cross_day_move", 0.65),
            "time_overlap": ("strategy_swap_time_slot", 0.70),
            "overloaded_day": ("strategy_cross_day_move", 0.60),
        }
        strategy, utility = strategy_map.get(conflict_type, ("strategy_time_shift", 0.30))
        return {
            "strategy": strategy,
            "params": {"mode": "transit"},
            "expected_utility": utility,
            "analysis": f"交通Agent建议{strategy}解决{conflict_type}冲突",
        }


# ==================== 模块级便捷函数 ====================

_shared_transport_agent: Optional[TransportAgent] = None


def _get_transport_agent() -> TransportAgent:
    """获取交通Agent单例"""
    global _shared_transport_agent
    if _shared_transport_agent is None:
        _shared_transport_agent = TransportAgent()
    return _shared_transport_agent


async def share_info(session_id: str, day_plans: List[dict]) -> None:
    """
    模块级便捷函数：分享交通信息到共享池

    供 negotiate_and_fix() 调用，无需实例化 Agent。
    """
    agent = _get_transport_agent()
    await agent.share_info(session_id, day_plans)
