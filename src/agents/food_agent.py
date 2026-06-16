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