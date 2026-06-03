"""
住宿推荐智能体
"""
from typing import Dict, Any, List
from .base_agent import BaseAgent

class HotelAgent(BaseAgent):
    """住宿推荐智能体"""

    def __init__(self):
        super().__init__(
            agent_id="hotel_agent_001",
            name="住宿推荐助手",
            description="为用户推荐合适的酒店和住宿方案"
        )

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
