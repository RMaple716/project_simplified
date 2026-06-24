"""
美食推荐智能体
"""
from typing import Dict, Any, List
from .base_agent import BaseAgent
from typing import Optional
class FoodAgent(BaseAgent):
    """美食推荐智能体"""

    def __init__(self):
        super().__init__(
            agent_id="food_agent_001",
            name="美食推荐助手",
            description="为用户推荐当地特色美食和餐厅"
        )
        self._async_init_done = False
    async def async_init(self):
        """异步初始化：注册消息处理器，启用Agent间通信"""
        if self._async_init_done:
            return
        await self.register_message_handlers()
        self._async_init_done = True
        print(f"美食Agent ({self.agent_id}) 消息处理器已注册")
        
    def get_capabilities(self) -> List[str]:
        return [
            "美食推荐",
            "餐厅推荐",
            "特色菜介绍",
            "价格查询"
        ]

    async def execute(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行美食推荐任务"""
        import time
        import uuid

        start_time = time.time()
        task_id = task_data.get("task_id", f"food_{uuid.uuid4().hex[:8]}")

        # 提取任务参数
        city_name = task_data.get("city_name", "")
        meal_type = task_data.get("meal_type")  # breakfast/lunch/dinner
        budget_per_person = task_data.get("budget_per_person")
        cuisine_preference = task_data.get("cuisine_preference")

        # 如果没有配置API密钥，返回模拟数据
        import os
        if not os.getenv("DEEPSEEK_API_KEY"):
            return self._get_mock_data(task_id, city_name, budget_per_person, start_time)

        # 构建系统提示词
        system_prompt = """你是一个专业的美食推荐助手。请为用户推荐当地特色美食和餐厅。

要求：
1. 推荐的餐厅要符合用户预算和口味偏好
2. 包含当地特色菜品
3. 提供准确的价格和评分信息
4. 包含实用信息（位置、特色等）

返回格式：
{
  "restaurants": [
    {
      "restaurant_id": "rest_001",
      "name": "餐厅名称",
      "city_name": "城市名称",
      "address": "详细地址（仅用文字描述）",
      "location": {"lat": 纬度数字, "lng": 经度数字},
      "cuisine_type": "菜系类型",
      "avg_price": 人均消费（数字）,
      "rating": 评分（0-5）,
      "specialties": ["特色菜1", "特色菜2"]
    }
  ]
}"""

        # 构建用户提示词
        budget_hint = f"人均预算：{budget_per_person}元" if budget_per_person else "无预算限制"
        cuisine_hint = f"菜系偏好：{cuisine_preference}" if cuisine_preference else "推荐当地特色菜系"
        meal_hint = f"餐别：{meal_type}" if meal_type else "全天用餐"
        location_format = '{"lat": 纬度数字, "lng": 经度数字}'
        user_prompt = f"""请为以下美食需求推荐餐厅：

                         城市：{city_name}
                         {meal_hint}
                         {budget_hint}
                         {cuisine_hint}
                         
                         请推荐5-8家不同特色的餐厅，包括当地知名餐厅和特色小店。
                         每个餐厅必须包含：
                         - 唯一ID（restaurant_id，rest_xxx格式）
                         - 餐厅名称
                         - 城市名称（与目的地一致）
                         - 餐厅地址（address，详细地址文字）
                         - 坐标（location，格式为 {location_format}）
                         - 菜系类型
                         - 人均消费
                         - 评分（0-5）
                         - 特色菜品"""

        # 调用LLM
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response_content = await self.call_llm(messages, max_tokens=3000)
            result = self._parse_json_response(response_content)

            processing_time = (time.time() - start_time) * 1000

            return {
                "task_id": task_id,
                "status": "success",
                "data": {
                    "items": result.get("restaurants", [])
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

    def _get_mock_data(self, task_id: str, city_name: str, budget_per_person: Optional[float] = None, start_time: float = 0) -> Dict[str, Any]:
        """生成模拟餐厅数据"""
        import time

        # 根据城市名称生成不同的餐厅
        city_restaurants = {
            "北京": [
                {"restaurant_id": "rest_001", "name": "全聚德烤鸭店", "city_name": city_name, "address": "北京市东城区前门大街30号", "location": {"lat": 39.896, "lng": 116.397}, "cuisine_type": "北京菜", "avg_price": 200, "rating": 4.7, "specialties": ["北京烤鸭", "京酱肉丝"]},
                {"restaurant_id": "rest_002", "name": "东来顺饭庄", "city_name": city_name, "address": "北京市东城区王府井大街198号", "location": {"lat": 39.913, "lng": 116.410}, "cuisine_type": "涮羊肉", "avg_price": 150, "rating": 4.6, "specialties": ["涮羊肉", "芝麻烧饼"]},
                {"restaurant_id": "rest_002", "name": "东来顺饭庄", "city_name": city_name, "address": "北京市东城区王府井大街198号", "location": {"lat": 39.913, "lng": 116.410}, "cuisine_type": "涮羊肉", "avg_price": 150, "rating": 4.6, "specialties": ["涮羊肉", "芝麻烧饼"]},
                {"restaurant_id": "rest_003", "name": "庆丰包子铺", "city_name": city_name, "address": "北京市西城区地安门外大街", "location": {"lat": 39.936, "lng": 116.397}, "cuisine_type": "北京小吃", "avg_price": 50, "rating": 4.5, "specialties": ["猪肉大葱包子", "豆汁"]},
                {"restaurant_id": "rest_004", "name": "老北京炸酱面", "city_name": city_name, "address": "北京市西城区南锣鼓巷", "location": {"lat": 39.937, "lng": 116.404}, "cuisine_type": "北京菜", "avg_price": 60, "rating": 4.4, "specialties": ["炸酱面", "卤煮火烧"]},
                {"restaurant_id": "rest_005", "name": "护国寺小吃", "city_name": city_name, "address": "北京市西城区护国寺大街", "location": {"lat": 39.931, "lng": 116.374}, "cuisine_type": "北京小吃", "avg_price": 40, "rating": 4.5, "specialties": ["豌豆黄", "驴打滚"]},
                {"restaurant_id": "rest_006", "name": "便宜坊烤鸭店", "city_name": city_name, "address": "北京市崇文门外大街16号", "location": {"lat": 39.895, "lng": 116.419}, "cuisine_type": "北京菜", "avg_price": 180, "rating": 4.6, "specialties": ["焖炉烤鸭", "芥末鸭掌"]},
            ],
            "上海": [
                {"restaurant_id": "rest_001", "name": "小杨生煎", "city_name": city_name, "address": "上海市黄浦区南京东路", "location": {"lat": 31.235, "lng": 121.478}, "cuisine_type": "上海菜", "avg_price": 40, "rating": 4.6, "specialties": ["生煎包", "牛肉粉丝汤"]},
                {"restaurant_id": "rest_002", "name": "南翔馒头店", "city_name": city_name, "address": "上海市黄浦区豫园路", "location": {"lat": 31.228, "lng": 121.487}, "cuisine_type": "上海菜", "avg_price": 50, "rating": 4.7, "specialties": ["小笼包", "蟹粉小笼"]},
                {"restaurant_id": "rest_003", "name": "绿波廊", "city_name": city_name, "address": "上海市黄浦区豫园路", "location": {"lat": 31.228, "lng": 121.488}, "cuisine_type": "上海菜", "avg_price": 200, "rating": 4.8, "specialties": ["桂花拉糕", "眉毛酥"]},
                {"restaurant_id": "rest_004", "name": "沈大成", "city_name": city_name, "address": "上海市黄浦区南京东路", "location": {"lat": 31.235, "lng": 121.480}, "cuisine_type": "上海菜", "avg_price": 60, "rating": 4.5, "specialties": ["青团", "条头糕"]},
                {"restaurant_id": "rest_005", "name": "老正兴", "city_name": city_name, "address": "上海市黄浦区福州路", "location": {"lat": 31.232, "lng": 121.482}, "cuisine_type": "上海菜", "avg_price": 180, "rating": 4.6, "specialties": ["红烧肉", "油爆虾"]},
                {"restaurant_id": "rest_006", "name": "大壶春", "city_name": city_name, "address": "上海市黄浦区四川南路", "location": {"lat": 31.230, "lng": 121.485}, "cuisine_type": "上海菜", "avg_price": 45, "rating": 4.5, "specialties": ["生煎包", "咖喱牛肉汤"]},
            ],
            "杭州": [
                {"restaurant_id": "rest_001", "name": "知味观", "city_name": city_name, "address": "杭州市上城区仁和路83号", "location": {"lat": 30.252, "lng": 120.169}, "cuisine_type": "杭帮菜", "avg_price": 100, "rating": 4.7, "specialties": ["东坡肉", "西湖醋鱼"]},
                {"restaurant_id": "rest_002", "name": "楼外楼", "city_name": city_name, "address": "杭州市西湖区孤山路30号", "location": {"lat": 30.264, "lng": 120.154}, "cuisine_type": "杭帮菜", "avg_price": 200, "rating": 4.8, "specialties": ["西湖醋鱼", "龙井虾仁"]},
                {"restaurant_id": "rest_003", "name": "外婆家", "city_name": city_name, "address": "杭州市上城区湖滨银泰", "location": {"lat": 30.253, "lng": 120.172}, "cuisine_type": "杭帮菜", "avg_price": 80, "rating": 4.6, "specialties": ["茶香鸡", "外婆红烧肉"]},
                {"restaurant_id": "rest_004", "name": "绿茶餐厅", "city_name": city_name, "address": "杭州市西湖区龙井路", "location": {"lat": 30.240, "lng": 120.113}, "cuisine_type": "杭帮菜", "avg_price": 90, "rating": 4.5, "specialties": ["绿茶烤肉", "面包诱惑"]},
                {"restaurant_id": "rest_005", "name": "新白鹿", "city_name": city_name, "address": "杭州市上城区延安路", "location": {"lat": 30.255, "lng": 120.174}, "cuisine_type": "杭帮菜", "avg_price": 70, "rating": 4.5, "specialties": ["蛋黄鸡翅", "红烧肉"]},
                {"restaurant_id": "rest_006", "name": "奎元馆", "city_name": city_name, "address": "杭州市上城区解放路", "location": {"lat": 30.247, "lng": 120.171}, "cuisine_type": "杭帮菜", "avg_price": 60, "rating": 4.6, "specialties": ["虾爆鳝面", "片儿川"]},
            ],
            "成都": [
                {"restaurant_id": "rest_001", "name": "陈麻婆豆腐", "city_name": city_name, "address": "成都市青羊区西玉龙街", "location": {"lat": 30.668, "lng": 104.058}, "cuisine_type": "川菜", "avg_price": 80, "rating": 4.7, "specialties": ["麻婆豆腐", "回锅肉"]},
                {"restaurant_id": "rest_002", "name": "龙抄手", "city_name": city_name, "address": "成都市青羊区春熙路", "location": {"lat": 30.657, "lng": 104.080}, "cuisine_type": "川菜", "avg_price": 50, "rating": 4.6, "specialties": ["龙抄手", "钟水饺"]},
                {"restaurant_id": "rest_003", "name": "火锅店", "city_name": city_name, "address": "成都市锦江区春熙路", "location": {"lat": 30.656, "lng": 104.081}, "cuisine_type": "火锅", "avg_price": 120, "rating": 4.7, "specialties": ["毛肚", "黄喉"]},
                {"restaurant_id": "rest_004", "name": "串串香", "city_name": city_name, "address": "成都市武侯区玉林路", "location": {"lat": 30.632, "lng": 104.056}, "cuisine_type": "川菜", "avg_price": 60, "rating": 4.5, "specialties": ["串串香", "冰粉"]},
                {"restaurant_id": "rest_005", "name": "钵钵鸡", "city_name": city_name, "address": "成都市青羊区宽窄巷子", "location": {"lat": 30.666, "lng": 104.053}, "cuisine_type": "川菜", "avg_price": 55, "rating": 4.6, "specialties": ["钵钵鸡", "夫妻肺片"]},
                {"restaurant_id": "rest_006", "name": "担担面", "city_name": city_name, "address": "成都市锦江区太古里", "location": {"lat": 30.656, "lng": 104.083}, "cuisine_type": "川菜", "avg_price": 40, "rating": 4.5, "specialties": ["担担面", "甜水面"]},
            ]
        }

        # 获取对应城市的餐厅,如果没有则使用通用餐厅
        restaurants = city_restaurants.get(city_name, [
            {"restaurant_id": "rest_001", "name": f"{city_name}特色餐厅", "city_name": city_name, "address": f"{city_name}市中心", "location": {"lat": 30.0, "lng": 120.0}, "cuisine_type": "当地菜", "avg_price": 100, "rating": 4.5, "specialties": ["特色菜1", "特色菜2"]},
            {"restaurant_id": "rest_002", "name": f"{city_name}小吃店", "city_name": city_name, "address": f"{city_name}老城区", "location": {"lat": 30.0, "lng": 120.1}, "cuisine_type": "小吃", "avg_price": 50, "rating": 4.4, "specialties": ["小吃1", "小吃2"]},
            {"restaurant_id": "rest_003", "name": f"{city_name}火锅店", "city_name": city_name, "address": f"{city_name}商业区", "location": {"lat": 30.1, "lng": 120.0}, "cuisine_type": "火锅", "avg_price": 120, "rating": 4.6, "specialties": ["火锅特色菜"]},
        ])

        processing_time = (time.time() - start_time) * 1000

        return {
            "task_id": task_id,
            "status": "success",
            "data": {
                "items": restaurants
            },
            "metadata": {
                "processing_time_ms": processing_time,
                "source": "mock_data",
                "model_used": None,
                "over_budget": False
            },
            "error_message": None
        }

    # ==================== 【改造方案 4.1】Agent间信息共享 ====================

    async def share_info(self, session_id: str, restaurants: List[dict]) -> None:
        """
        分享美食信息到共享池（改造方案 4.1.2）

        Args:
            session_id: 会话ID
            restaurants: 餐厅列表
        """
        from src.services.negotiation_event_bus import agent_message_bus

        info = {
            "restaurants": [
                {
                    "name": r.get("name", ""),
                    "location": r.get("location", {}),
                    "cuisine_type": r.get("cuisine_type", ""),
                    "avg_price": r.get("avg_price", 0),
                    "rating": r.get("rating", 0),
                    "meal_type": r.get("meal_type", ""),
                }
                for r in restaurants
                if isinstance(r, dict)
            ]
        }
        await agent_message_bus.share_agent_info(
            agent_id=self.agent_id,
            session_id=session_id,
            info_type="food_info",
            info_data=info,
        )

    # ==================== 【步1】新增：Agent间投票处理 ====================

    async def on_message(self, message: dict) -> Optional[dict]:
        """处理来自其他Agent的消息（增强版：支持投票）"""
        msg_type = message.get("type", "unknown")
        from_agent = message.get("fromAgent", "unknown")
        payload = message.get("payload", {})

        # 投票请求
        if payload.get("action") == "consensus_vote":
            return await self._handle_vote(payload)

        # 【改造方案 4.2.5】冲突招标
        if payload.get("action") == "conflict_bid":
            return await self._handle_bid(payload)

        # 【P2】冲突咨询
        if payload.get("action") == "consult_conflict":
            return await self._handle_consult(payload)

                # 【P2】反提案请求
        if payload.get("action") == "counter_proposal":
            return await self._handle_counter_proposal(payload)

        # === 【阶段B】反提案评估 + 条件回应 ===
        if payload.get("action") == "evaluate_counter_proposal":
            return await self._handle_evaluate_counter_proposal(payload)
        if payload.get("action") == "respond_to_condition":
            return await self._handle_respond_to_condition(payload)

        print(f"\n  🍽️ 美食Agent收到来自 [{from_agent}] 的消息: {msg_type}")

        # 其他消息类型走默认处理
        from .base_agent import BaseAgent
        return await BaseAgent.on_message(self, message)

    async def _handle_vote(self, payload: dict) -> dict:
        """
        处理投票请求——检查餐饮时间是否受影响。
        否决条件：餐饮被安排在极不合理的时间（早6点前或晚22点后）。
        """
        proposed_summary = payload.get("proposed_day_summary", {})
        proposed_meals = proposed_summary.get("meals", [])

        import re
        for meal_desc in proposed_meals:
            # meal_desc 格式: "餐厅名(HH:MM)"
            time_match = re.search(r'\((\d{2}:\d{2})\)', meal_desc)
            if time_match:
                time_str = time_match.group(1)
                hour = int(time_str.split(":")[0])
                name = meal_desc.split("(")[0]

                if hour < 6 or hour >= 22:
                    return {
                        "vote": "veto",
                        "agent_id": self.agent_id,
                        "reason": f"餐饮'{name}'安排在{time_str}，不在合理用餐时间",
                    }

        return {"vote": "approve", "agent_id": self.agent_id}

    async def _handle_consult(self, payload: dict) -> dict:
        """处理冲突咨询"""
        conflict_type = payload.get("conflict_type", "")

        if conflict_type == "unreasonable_meal_time":
            return {
                "suggested_strategy": "strategy_time_shift",
                "suggested_params": {"margin": 15},
                "veto_strategies": ["strategy_compress_duration"],
            }
        elif conflict_type == "budget_exceeded":
            return {
                "suggested_strategy": "strategy_replace_activity",
                "suggested_params": {},
                "veto_strategies": [],
            }
        elif conflict_type == "time_overlap":
            return {
                "suggested_strategy": "strategy_swap_time_slot",
                "suggested_params": {},
                "veto_strategies": [],
            }

        return {"suggested_strategy": None, "suggested_params": {}, "veto_strategies": []}

    async def _handle_counter_proposal(self, payload: dict) -> dict:
        """处理反提案请求"""
        conflict = payload.get("conflict", {})
        conflict_type = conflict.get("type", "")

        strategy_map = {
            "unreasonable_meal_time": "strategy_time_shift",
            "budget_exceeded": "strategy_replace_activity",
            "time_overlap": "strategy_swap_time_slot",
        }

        strategy = strategy_map.get(conflict_type, "strategy_time_shift")

        return {
            "proposal_author": self.agent_id,
            "strategy": strategy,
            "params": {},
            "adjustments": [{"field": "策略建议", "item_name": conflict_type, "before": "未修复", "after": f"建议{strategy}"}],
            "expected_effect": f"美食Agent建议使用{strategy}解决{conflict_type}冲突",
        }

    async def _handle_bid(self, payload: dict) -> dict:
        """
        【改造方案 4.2.5】冲突招标 — 美食Agent投标

        改造后: 从共享信息池读取景点位置和餐饮偏好，
        用LLM生成考虑行程时序的投标方案。

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
                "params": bid_result.get("params", {"meal_margin": 30}),
                "expected_utility": float(bid_result.get("expected_utility", 0.5)),
                "analysis": bid_result.get("analysis", f"美食Agent建议{strategy}解决{conflict_type}冲突"),
            }

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"[美食Agent] LLM投标失败，降级到硬编码映射: {e}")
            return self._handle_bid_fallback(payload)

    def _build_bidding_prompt(
        self,
        conflict: dict,
        conflict_type: str,
        day_num: int,
        shared_info: dict,
    ) -> str:
        """构造LLM投标提示词，基于景点和餐饮信息生成投标方案"""
        conflict_desc = conflict.get("description", "") or conflict.get("conflict_description", "")
        activities = conflict.get("activities", [])

        # 提取景点和自身餐饮信息
        attractions_summary = ""
        food_self_summary = ""
        try:
            # 景点信息
            attr_data = shared_info.get("attractions_agent_001", {}).get("data", {})
            all_attrs = attr_data.get("attractions", [])
            if all_attrs:
                attr_lines = []
                for a in all_attrs[:6]:
                    name = a.get("name", "")
                    slot = a.get("recommended_time_slot", "?")
                    duration = a.get("best_visit_duration", "?")
                    attr_lines.append(f"  {name}: 建议时段={slot}, 游览时长={duration}分钟")
                attractions_summary = "\n".join(attr_lines)

            # 自身的餐饮信息
            food_data = shared_info.get("food_agent_001", {}).get("data", {})
            restaurants = food_data.get("restaurants", [])
            if restaurants:
                rest_lines = []
                for r in restaurants[:6]:
                    name = r.get("name", "")
                    meal_type = r.get("meal_type", "")
                    rating = r.get("rating", "?")
                    addr = r.get("address", "")
                    rest_lines.append(f"  {name}: {meal_type}, 评分={rating}, 地址={addr}")
                food_self_summary = "\n".join(rest_lines)
        except Exception:
            pass

        prompt = f"""你是一个专业的{self.name}（美食Agent），请分析以下行程冲突，基于餐饮规划知识生成投标方案。

【冲突信息】
- 冲突类型: {conflict_type}
- 涉及活动: {', '.join(activities) if activities else '未知'}
- 描述: {conflict_desc}
- 第{day_num}天

【景点游览信息】
{attractions_summary if attractions_summary else '(无景点信息)'}

【附近餐饮信息】
{food_self_summary if food_self_summary else '(无餐饮信息)'}

【可选的解决策略】
1. strategy_time_shift - 时间平移（将用餐时间提前或推迟到正常饭点）
2. strategy_swap_time_slot - 交换时段（将午餐/晚餐互换时间）
3. strategy_cross_day_move - 跨天移动（将餐厅移到另一天）
4. strategy_compress_duration - 压缩时长（缩短用餐时间）

【你的任务】
分析冲突，选择最合适的策略，关注：
- 用餐时间是否在正常饭点（午餐11:00-13:30，晚餐17:30-20:00）
- 是否与附近景点游览时间匹配
- 各餐之间是否留出合理的间隔时间

请返回JSON格式（只返回JSON，不要其他文字）:
{{
  "strategy": "选择的策略名称",
  "params": {{
    "meal_margin": 30
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
            "unreasonable_meal_time": ("strategy_time_shift", 0.80),
            "budget_exceeded": ("strategy_replace_activity", 0.55),
            "time_overlap": ("strategy_swap_time_slot", 0.70),
            "too_short_duration": ("strategy_time_shift", 0.45),
        }
        strategy, utility = strategy_map.get(conflict_type, ("strategy_time_shift", 0.30))
        return {
            "strategy": strategy,
            "params": {"meal_margin": 30},
            "expected_utility": utility,
            "analysis": f"美食Agent建议{strategy}解决{conflict_type}冲突",
        }


# ==================== 模块级便捷函数 ====================

_shared_food_agent: Optional[FoodAgent] = None


def _get_food_agent() -> FoodAgent:
    """获取美食Agent单例"""
    global _shared_food_agent
    if _shared_food_agent is None:
        _shared_food_agent = FoodAgent()
    return _shared_food_agent


async def share_info(session_id: str, restaurants: List[dict]) -> None:
    """
    模块级便捷函数：分享美食信息到共享池

    供 negotiate_and_fix() 调用，无需实例化 Agent。
    """
    agent = _get_food_agent()
    await agent.share_info(session_id, restaurants)