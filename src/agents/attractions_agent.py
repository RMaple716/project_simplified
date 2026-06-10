
"""
景点推荐智能体
"""
from typing import Dict, Any, List, Optional
from .base_agent import BaseAgent
from src.services.weather_service import weather_service


class AttractionsAgent(BaseAgent):
    """景点推荐智能体"""

    def __init__(self):
        super().__init__(
            agent_id="attractions_agent_001",
            name="景点推荐助手",
            description="基于用户偏好推荐合适的旅游景点"
        )
        self.weather_service = weather_service

    def get_capabilities(self) -> List[str]:
        return [
            "景点推荐",
            "行程规划",
            "景点信息查询",
            "游览时间建议"
        ]

    async def execute(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行景点推荐任务"""
        import time
        import uuid
        import os

        start_time = time.time()
        task_id = task_data.get("task_id", f"attr_{uuid.uuid4().hex[:8]}")

        # 提取任务参数
        city_name = task_data.get("city_name", "")
        travel_days = task_data.get("travel_days", 1)
        ticket_budget = task_data.get("ticket_budget")
        preferences = task_data.get("preferences", [])
        dislikes = task_data.get("dislikes", [])
        location_preference = task_data.get("location_preference")
        traveler_count = task_data.get("traveler_count", 1)
        travel_date = task_data.get("travel_date", "")  # 获取旅行日期

        # 获取天气信息
        weather_info = None
        if city_name:
            try:
                # 获取天气预报信息
                weather_response = await self.weather_service.get_weather(city_name, extensions="all")
                if weather_response.get("status") == "success":
                    forecasts = weather_response.get("data", [])
                    if forecasts and len(forecasts) > 0:
                        available_forecasts = forecasts[0].get("casts", [])
                        # 高德天气API通常只提供4天预报
                        available_days = min(len(available_forecasts), travel_days) if travel_days else len(available_forecasts)
                        weather_info = {
                            "city": city_name,
                            "forecasts": available_forecasts[:available_days],
                            "available_days": available_days,
                            "total_days": travel_days
                        }
            except Exception as e:
                print(f"获取天气信息失败: {str(e)}")

                # 如果没有配置API密钥，返回模拟数据
        if not os.getenv("DEEPSEEK_API_KEY"):
              return self._get_mock_data(task_id, city_name, travel_days, start_time, weather_info, preferences)

        # 构建系统提示词
        system_prompt = """你是一个专业的景点推荐助手。请根据用户需求和天气情况推荐合适的旅游景点。

要求：
1. 推荐的景点要符合用户偏好和预算
2. 合理安排游览时间，根据天气情况调整室内外景点的比例
3. 提供准确的费用信息
4. 包含实用信息（位置、最佳游览时间等）
5. 如果天气不佳（如雨天），优先推荐室内景点
6. 如果天气良好，可以适当增加户外景点
7. 【关键】同一城市内，推荐的景点应集中在城市核心区或同一地理片区，景点之间的直线距离不宜超过15公里。优先推荐地铁/公交可达且相邻景点间交通耗时不超过60分钟的景点组合。避免同时推荐位于城市两端或相距极远的景点（如北京同时推荐八达岭长城和故宫）。
8. 长途旅行（多天）时，可将较远的景点（如郊区、周边县市）安排在单独的某一天集中游览，不要与市中心景点混在一天。
9. **【重要】必须包含该城市最具代表性的核心景点（如衡阳必须包含南岳衡山）**，不能遗漏用户所在城市的标志性景点。核心景点优先安排。
10. **【关键】如果用户的「偏好」列表中包含具体的景点名称（如"衡山""故宫""黄山"等），则该景点为必去景点，必须包含在推荐结果中。** 请先解析偏好列表，识别其中的具体景点名称，确保这些景点被优先列入行程。

返回格式：
{
  "attractions": [
    {
      "attraction_id": "att_001",
      "name": "景点名称",
      "city_name": "城市名称",
      "address": "详细地址（仅用文字描述）",
      "location": {"lat": 纬度数字, "lng": 经度数字},
      "description": "景点描述",
      "recommended_duration": "游览时长（如：4小时）",
      "visit_time_slot": "morning/afternoon/evening",
      "ticket_price": 门票价格（数字）,
      "rating": 评分（0-5）,
      "opening_hours": "营业时间",
      "tags": ["标签1", "标签2"]
    }
  ]
}"""

        # 构建用户提示词
        # 添加天气信息到提示词
        weather_text = ""
        if weather_info and weather_info.get("forecasts"):
            weather_text = "\n天气预报信息：\n"
            available_days = weather_info.get("available_days", 0)
            total_days = weather_info.get("total_days", 0)

            for i, forecast in enumerate(weather_info["forecasts"]):
                date = forecast.get("date", "")
                day_weather = forecast.get("dayweather", "")
                night_weather = forecast.get("nightweather", "")
                temperature = f"{forecast.get('daytemp', '')}°C/{forecast.get('nighttemp', '')}°C"
                weather_text += f"第{i+1}天 ({date}): 白天{day_weather}, 夜间{night_weather}, 温度{temperature}\n"

            if total_days > available_days:
                weather_text += f"\n注意：仅获取到前{available_days}天的天气预报，第{available_days+1}天至第{total_days}天请根据季节和城市特点合理推测天气情况。\n"
        location_format = '{"lat": 纬度数字, "lng": 经度数字}'
        user_prompt = f"""请为以下旅行需求推荐景点：
        目的地：{city_name}
        旅行天数：{travel_days}天
        门票预算：{ticket_budget}元（如未指定则不考虑预算）
        偏好：{', '.join(preferences) if preferences else '无特殊偏好'}
        不喜欢的：{', '.join(dislikes) if dislikes else '无'}
        区域偏好：{location_preference if location_preference else '无特殊要求'}
        旅行人数：{traveler_count}人{weather_text}
        
        请推荐{travel_days * 3}个左右的景点，确保每天有合理的游览安排。
        每个景点必须包含：
        - 唯一ID（attraction_id，att_xxx格式）
        - 景点名称
        - 城市名称（与目的地一致）
        - 景点地址（address，详细地址文字）
        - 坐标（location，格式为 {location_format}）
        - 景点描述（简要介绍）
        - 建议游览时长
        - 建议游览时段（morning/afternoon/evening）
        - 门票价格
        - 评分（0-5）
        - 营业时间
        - 标签"""
        
        # 调用LLM
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            # 根据旅行天数决定是否分批生成
            # 超过7天时采用分批策略，避免JSON被截断
            if travel_days > 7:
                result = await self._generate_attractions_in_batches(
                    task_data, weather_info, system_prompt, user_prompt
                )
            else:
                response_content = await self.call_llm(messages, max_tokens=8192)
                result = self._parse_json_response(response_content)

            processing_time = (time.time() - start_time) * 1000

            return {
                "task_id": task_id,
                "status": "success",
                "data": {
                    "items": result.get("attractions", [])
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

    def _get_mock_data(self, task_id: str, city_name: str, travel_days: int, start_time: float, weather_info: Optional[Dict[str, Any]] = None, preferences: Optional[List[str]] = None) -> Dict[str, Any]:
        """生成模拟景点数据"""
        import time
        
        # 根据天气情况调整景点推荐
        weather_adjustment = ""
        if weather_info and weather_info.get("forecasts"):
            first_day_weather = weather_info["forecasts"][0].get("dayweather", "")
            if "雨" in first_day_weather or "雪" in first_day_weather:
                weather_adjustment = " (天气不佳，推荐室内景点)"
            elif "晴" in first_day_weather or "多云" in first_day_weather:
                weather_adjustment = " (天气良好，适合户外活动)"

        # 根据城市名称生成不同的景点
        city_attractions = {
            "北京": [
                {"attraction_id": "att_001", "name": "故宫博物院", "city_name": city_name, "address": "北京市东城区景山前街4号", "location": {"lat": 39.916, "lng": 116.397}, "description": "中国明清两代的皇家宫殿,世界文化遗产", "recommended_duration": "4小时", "visit_time_slot": "morning", "ticket_price": 60, "rating": 4.8, "opening_hours": "8:30-17:00", "tags": ["历史", "文化", "世界遗产"]},
                {"attraction_id": "att_002", "name": "天坛公园", "city_name": city_name, "address": "北京市东城区天坛路甲1号", "location": {"lat": 39.882, "lng": 116.407}, "description": "明清两代皇帝祭天的场所,中国古代建筑杰作", "recommended_duration": "3小时", "visit_time_slot": "afternoon", "ticket_price": 35, "rating": 4.7, "opening_hours": "6:00-22:00", "tags": ["历史", "建筑", "公园"]},
                {"attraction_id": "att_003", "name": "颐和园", "city_name": city_name, "address": "北京市海淀区新建宫门路19号", "location": {"lat": 39.998, "lng": 116.275}, "description": "中国古典园林之首,皇家园林博物馆", "recommended_duration": "4小时", "visit_time_slot": "morning", "ticket_price": 50, "rating": 4.8, "opening_hours": "6:30-18:00", "tags": ["园林", "历史", "皇家"]},
                {"attraction_id": "att_004", "name": "长城(八达岭)", "city_name": city_name, "address": "北京市延庆区八达岭镇", "location": {"lat": 40.350, "lng": 116.017}, "description": "世界文化遗产,中国古代军事防御工程", "recommended_duration": "5小时", "visit_time_slot": "morning", "ticket_price": 40, "rating": 4.9, "opening_hours": "7:30-16:00", "tags": ["历史", "世界遗产", "徒步"]},
                {"attraction_id": "att_005", "name": "南锣鼓巷", "city_name": city_name, "address": "北京市东城区南锣鼓巷", "location": {"lat": 39.937, "lng": 116.404}, "description": "北京最古老的街区之一,胡同文化体验地", "recommended_duration": "2小时", "visit_time_slot": "afternoon", "ticket_price": 0, "rating": 4.5, "opening_hours": "全天", "tags": ["文化", "购物", "美食"]},
                {"attraction_id": "att_006", "name": "798艺术区", "city_name": city_name, "address": "北京市朝阳区酒仙桥路4号", "location": {"lat": 39.985, "lng": 116.495}, "description": "当代艺术聚集地,工业遗址改造的艺术区", "recommended_duration": "3小时", "visit_time_slot": "afternoon", "ticket_price": 0, "rating": 4.6, "opening_hours": "10:00-18:00", "tags": ["艺术", "文化", "摄影"]},
            ],
            "上海": [
                {"attraction_id": "att_001", "name": "外滩", "city_name": city_name, "address": "上海市黄浦区中山东一路", "location": {"lat": 31.240, "lng": 121.490}, "description": "上海标志性景点,万国建筑博览群", "recommended_duration": "2小时", "visit_time_slot": "evening", "ticket_price": 0, "rating": 4.8, "opening_hours": "全天", "tags": ["历史", "建筑", "夜景"]},
                {"attraction_id": "att_002", "name": "东方明珠", "city_name": city_name, "address": "上海市浦东新区世纪大道1号", "location": {"lat": 31.240, "lng": 121.500}, "description": "上海地标建筑,登高俯瞰城市全景", "recommended_duration": "2小时", "visit_time_slot": "evening", "ticket_price": 220, "rating": 4.7, "opening_hours": "9:00-21:30", "tags": ["地标", "观景", "夜景"]},
                {"attraction_id": "att_003", "name": "豫园", "city_name": city_name, "address": "上海市黄浦区福佑路168号", "location": {"lat": 31.228, "lng": 121.487}, "description": "明代私家园林,江南古典园林代表", "recommended_duration": "2小时", "visit_time_slot": "morning", "ticket_price": 40, "rating": 4.6, "opening_hours": "8:30-17:00", "tags": ["园林", "历史", "文化"]},
                {"attraction_id": "att_004", "name": "田子坊", "city_name": city_name, "address": "上海市黄浦区泰康路210弄", "location": {"lat": 31.215, "lng": 121.475}, "description": "艺术创意园区,石库门建筑群", "recommended_duration": "2小时", "visit_time_slot": "afternoon", "ticket_price": 0, "rating": 4.5, "opening_hours": "10:00-21:00", "tags": ["艺术", "文化", "购物"]},
                {"attraction_id": "att_005", "name": "南京路步行街", "city_name": city_name, "address": "上海市黄浦区南京东路", "location": {"lat": 31.235, "lng": 121.478}, "description": "中华商业第一街,购物天堂", "recommended_duration": "3小时", "visit_time_slot": "afternoon", "ticket_price": 0, "rating": 4.6, "opening_hours": "全天", "tags": ["购物", "美食", "商业"]},
                {"attraction_id": "att_006", "name": "上海博物馆", "city_name": city_name, "address": "上海市黄浦区人民大道201号", "location": {"lat": 31.230, "lng": 121.475}, "description": "中国古代艺术博物馆,文物收藏丰富", "recommended_duration": "3小时", "visit_time_slot": "morning", "ticket_price": 0, "rating": 4.7, "opening_hours": "9:00-17:00", "tags": ["博物馆", "历史", "文化"]},
            ],
            "杭州": [
                {"attraction_id": "att_001", "name": "西湖", "city_name": city_name, "address": "浙江省杭州市西湖区", "location": {"lat": 30.259, "lng": 120.155}, "description": "世界文化遗产,中国最美湖泊之一", "recommended_duration": "4小时", "visit_time_slot": "morning", "ticket_price": 0, "rating": 4.9, "opening_hours": "全天", "tags": ["自然", "文化", "世界遗产"]},
                {"attraction_id": "att_002", "name": "灵隐寺", "city_name": city_name, "address": "浙江省杭州市西湖区灵隐路法云弄1号", "location": {"lat": 30.245, "lng": 120.098}, "description": "中国著名佛教寺院,千年古刹", "recommended_duration": "2小时", "visit_time_slot": "morning", "ticket_price": 75, "rating": 4.7, "opening_hours": "7:00-18:00", "tags": ["宗教", "历史", "文化"]},
                {"attraction_id": "att_003", "name": "雷峰塔", "city_name": city_name, "address": "浙江省杭州市西湖区南山路15号", "location": {"lat": 30.234, "lng": 120.148}, "description": "西湖十景之一,白娘子传说发源地", "recommended_duration": "2小时", "visit_time_slot": "afternoon", "ticket_price": 40, "rating": 4.6, "opening_hours": "8:00-20:00", "tags": ["历史", "传说", "观景"]},
                {"attraction_id": "att_004", "name": "宋城", "city_name": city_name, "address": "浙江省杭州市西湖区之江路148号", "location": {"lat": 30.170, "lng": 120.128}, "description": "大型文化主题公园,宋城千古情演出", "recommended_duration": "4小时", "visit_time_slot": "afternoon", "ticket_price": 310, "rating": 4.5, "opening_hours": "10:00-21:00", "tags": ["主题公园", "演出", "文化"]},
                {"attraction_id": "att_005", "name": "西溪湿地", "city_name": city_name, "address": "浙江省杭州市西湖区天目山路518号", "location": {"lat": 30.270, "lng": 120.058}, "description": "国家湿地公园,城市绿肺", "recommended_duration": "3小时", "visit_time_slot": "morning", "ticket_price": 80, "rating": 4.7, "opening_hours": "7:30-18:30", "tags": ["自然", "生态", "休闲"]},
                {"attraction_id": "att_006", "name": "龙井村", "city_name": city_name, "address": "浙江省杭州市西湖区龙井村", "location": {"lat": 30.222, "lng": 120.120}, "description": "西湖龙井茶产地,茶文化体验", "recommended_duration": "2小时", "visit_time_slot": "afternoon", "ticket_price": 0, "rating": 4.6, "opening_hours": "全天", "tags": ["茶文化", "乡村", "自然"]},
            ],
            "成都": [
                {"attraction_id": "att_001", "name": "大熊猫繁育研究基地", "city_name": city_name, "address": "四川省成都市成华区熊猫大道1375号", "location": {"lat": 30.733, "lng": 104.145}, "description": "世界著名的大熊猫迁地保护基地", "recommended_duration": "3小时", "visit_time_slot": "morning", "ticket_price": 58, "rating": 4.8, "opening_hours": "7:30-18:00", "tags": ["动物", "自然", "亲子"]},
                {"attraction_id": "att_002", "name": "宽窄巷子", "city_name": city_name, "address": "四川省成都市青羊区宽窄巷子", "location": {"lat": 30.666, "lng": 104.053}, "description": "成都历史文化街区,体验老成都生活", "recommended_duration": "2小时", "visit_time_slot": "afternoon", "ticket_price": 0, "rating": 4.6, "opening_hours": "全天", "tags": ["文化", "美食", "历史"]},
                {"attraction_id": "att_003", "name": "锦里古街", "city_name": city_name, "address": "四川省成都市武侯区武侯祠大街231号", "location": {"lat": 30.648, "lng": 104.050}, "description": "仿古商业街,三国文化体验地", "recommended_duration": "2小时", "visit_time_slot": "afternoon", "ticket_price": 0, "rating": 4.5, "opening_hours": "全天", "tags": ["文化", "购物", "美食"]},
                {"attraction_id": "att_004", "name": "武侯祠", "city_name": city_name, "address": "四川省成都市武侯区武侯祠大街231号", "location": {"lat": 30.648, "lng": 104.048}, "description": "中国唯一的君臣合祀祠庙,三国圣地", "recommended_duration": "2小时", "visit_time_slot": "morning", "ticket_price": 60, "rating": 4.7, "opening_hours": "8:00-18:00", "tags": ["历史", "文化", "三国"]},
                {"attraction_id": "att_005", "name": "杜甫草堂", "city_name": city_name, "address": "四川省成都市青羊区青华路37号", "location": {"lat": 30.662, "lng": 104.038}, "description": "唐代诗人杜甫的故居,文学圣地", "recommended_duration": "2小时", "visit_time_slot": "morning", "ticket_price": 60, "rating": 4.6, "opening_hours": "8:00-18:30", "tags": ["历史", "文化", "文学"]},
                {"attraction_id": "att_006", "name": "春熙路", "city_name": city_name, "address": "四川省成都市锦江区春熙路", "location": {"lat": 30.657, "lng": 104.080}, "description": "成都最繁华的商业街,购物美食天堂", "recommended_duration": "2小时", "visit_time_slot": "evening", "ticket_price": 0, "rating": 4.5, "opening_hours": "全天", "tags": ["购物", "美食", "商业"]},
            ]
        }

        # 获取对应城市的景点,如果没有则使用通用景点
        attractions = city_attractions.get(city_name, [
            {"attraction_id": "att_001", "name": f"{city_name}博物馆", "city_name": city_name, "address": f"{city_name}市中心", "location": {"lat": 30.0, "lng": 120.0}, "description": f"了解{city_name}历史文化的好去处", "recommended_duration": "2小时", "visit_time_slot": "morning", "ticket_price": 50, "rating": 4.5, "opening_hours": "9:00-17:00", "tags": ["历史", "文化"]},
            {"attraction_id": "att_002", "name": f"{city_name}公园", "city_name": city_name, "address": f"{city_name}市中心", "location": {"lat": 30.0, "lng": 120.1}, "description": f"{city_name}市民休闲的好去处", "recommended_duration": "2小时", "visit_time_slot": "afternoon", "ticket_price": 0, "rating": 4.4, "opening_hours": "6:00-22:00", "tags": ["自然", "休闲"]},
            {"attraction_id": "att_003", "name": f"{city_name}古街", "city_name": city_name, "address": f"{city_name}老城区", "location": {"lat": 30.1, "lng": 120.0}, "description": f"体验{city_name}传统文化", "recommended_duration": "2小时", "visit_time_slot": "afternoon", "ticket_price": 0, "rating": 4.5, "opening_hours": "全天", "tags": ["文化", "历史"]},
        ])

                # 根据天数选择景点数量（至少返回 4 个，确保覆盖足够多的景点）
        num_attractions = min(len(attractions), max(travel_days * 3, 4))
        selected_attractions = attractions[:num_attractions]

        # 检查用户偏好中的景点名是否在列表中，如果不在则追加
        if preferences:
            for pref in preferences:
                if not pref:
                    continue
                # 查找偏好中提到的景点名是否在 selected_attractions 中
                pref_lower = pref.lower()
                found = any(pref_lower in a.get('name', '').lower() for a in selected_attractions)
                if not found:
                    # 在完整列表中查找匹配的景点
                    for a in attractions:
                        a_name = a.get('name', '').lower()
                        a_tags = [t.lower() for t in a.get('tags', [])]
                        if pref_lower in a_name or pref_lower in a_tags:
                            if a not in selected_attractions:
                                selected_attractions.append(a)
                                break

        processing_time = (time.time() - start_time) * 1000

        return {
            "task_id": task_id,
            "status": "success",
            "data": {
                "items": selected_attractions
            },
            "metadata": {
                "processing_time_ms": processing_time,
                "source": "mock_data",
                "model_used": None,
                "over_budget": False
            },
            "error_message": None
        }

    async def _generate_attractions_in_batches(
        self,
        task_data: Dict[str, Any],
        weather_info:Optional[ Dict[str, Any]]=None,
        system_prompt: str="",
        user_prompt: str=""
    ) -> Dict[str, Any]:
        """
        分批生成景点推荐，用于长时间旅行规划

        Args:
            task_data: 任务数据
            weather_info: 天气信息
            system_prompt: 系统提示词
            user_prompt: 用户提示词

        Returns:
            包含所有景点推荐的字典
        """
        travel_days = task_data.get("travel_days", 1)
        city_name = task_data.get("city_name", "")
        preferences = task_data.get("preferences", [])
        dislikes = task_data.get("dislikes", [])
        ticket_budget = task_data.get("ticket_budget")
        traveler_count = task_data.get("traveler_count", 1)
        location_preference = task_data.get("location_preference")

        # 计算需要的景点总数
        total_attractions = travel_days * 3

        # 分批策略：每批生成5天的景点（最多15个景点）
        batch_days = 5
        all_attractions = []

        # 构建基础提示词（不包含天数）
        base_user_prompt = f"""目的地：{city_name}
门票预算：{ticket_budget}元（如未指定则不考虑预算）
偏好：{', '.join(preferences) if preferences else '无特殊偏好'}
不喜欢的：{', '.join(dislikes) if dislikes else '无'}
区域偏好：{location_preference if location_preference else '无特殊要求'}
旅行人数：{traveler_count}人"""

        # 添加天气信息
        weather_text = ""
        if weather_info and weather_info.get("forecasts"):
            weather_text = "\n天气预报信息：\n"
            available_days = weather_info.get("available_days", 0)
            total_days = weather_info.get("total_days", 0)

            for i, forecast in enumerate(weather_info["forecasts"]):
                date = forecast.get("date", "")
                day_weather = forecast.get("dayweather", "")
                night_weather = forecast.get("nightweather", "")
                temperature = f"{forecast.get('daytemp', '')}°C/{forecast.get('nighttemp', '')}°C"
                weather_text += f"第{i+1}天 ({date}): 白天{day_weather}, 夜间{night_weather}, 温度{temperature}\n"

            if total_days > available_days:
                weather_text += f"\n注意：仅获取到前{available_days}天的天气预报，第{available_days+1}天至第{total_days}天请根据季节和城市特点合理推测天气情况。\n"

        base_user_prompt += weather_text

        # 分批生成
        current_day = 1
        batch_num = 1

        while current_day <= travel_days:
            # 计算当前批次的结束天数
            end_day = min(current_day + batch_days - 1, travel_days)
            batch_travel_days = end_day - current_day + 1

            # 构建当前批次的提示词
            batch_user_prompt = f"""{base_user_prompt}

本次规划：第{current_day}天至第{end_day}天（共{batch_travel_days}天）

请为这{batch_travel_days}天推荐{batch_travel_days * 3}个左右的景点。
每个景点必须包含：
- 唯一ID（attraction_id，att_xxx格式）
- 景点名称
- 城市名称（与目的地一致）
- 景点地址（详细地址）
- 景点描述（简要介绍）
- 建议游览时长
- 建议游览时段（morning/afternoon/evening）
- 门票价格
- 评分（0-5）
- 营业时间
- 标签

注意：这是第{batch_num}批推荐，请确保与之前推荐的景点不重复。"""

            # 调用LLM生成当前批次的景点
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": batch_user_prompt}
            ]

            try:
                response_content = await self.call_llm(messages, max_tokens=4000)
                batch_result = self._parse_json_response(response_content)
                batch_attractions = batch_result.get("attractions", [])

                # 更新景点的day_index，标记它们属于哪一天
                for attraction in batch_attractions:
                    attraction["day_index"] = current_day

                all_attractions.extend(batch_attractions)

                # 如果当前批次没有返回足够的景点，补充默认景点
                expected_count = batch_travel_days * 3
                if len(batch_attractions) < expected_count:
                    # 添加一些默认景点作为补充
                    for i in range(expected_count - len(batch_attractions)):
                        all_attractions.append({
                           "attraction_id": f"att_default_{len(all_attractions) + 1}",
                           "name": f"{city_name}特色景点{len(all_attractions) + 1}",
                           "city_name": city_name,
                           "address": f"{city_name}市区",
                           "location": {"lat": 0, "lng": 0},
                           "description": "待探索的特色景点",
                           "recommended_duration": "3小时",
                           "visit_time_slot": "afternoon",
                           "ticket_price": 50,
                           "rating": 4.0,
                           "opening_hours": "9:00-17:00",
                           "tags": ["待探索"],
                           "day_index": current_day
                        })

            except Exception as e:
                print(f"第{batch_num}批景点生成失败: {str(e)}")
                # 如果生成失败，添加默认景点
                for i in range(batch_travel_days * 3):
                    all_attractions.append({
                        "attraction_id": f"att_default_{len(all_attractions) + 1}",
                        "name": f"{city_name}特色景点{len(all_attractions) + 1}",
                        "city_name": city_name,
                        "address": f"{city_name}市区",
                        "location": {"lat": 0, "lng": 0},
                        "description": "待探索的特色景点",
                        "recommended_duration": "3小时",
                        "visit_time_slot": "afternoon",
                        "ticket_price": 50,
                        "rating": 4.0,
                        "opening_hours": "9:00-17:00",
                        "tags": ["待探索"],
                        "day_index": current_day
                    })

            # 移动到下一批次
            current_day = end_day + 1
            batch_num += 1

        return {"attractions": all_attractions}
