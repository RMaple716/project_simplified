"""
DeepSeek API客户端
"""
import os
import httpx
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

load_dotenv()

class DeepSeekClient:
    """DeepSeek API客户端"""

    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
        self.timeout = 30
        self.max_retries = 3
        self.retry_delay = 1

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """调用DeepSeek聊天完成API，带重试机制"""

        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY环境变量未设置")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        import asyncio

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload
                    )
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise

    async def analyze_travel_requirement(
        self,
        user_requirement: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """分析旅行需求"""

        system_prompt = """你是一个专业的旅行规划助手。请分析用户的旅行需求，提取关键信息并返回结构化数据。

返回格式要求：
{
  "city_name": "城市名称",
  "travel_days": 天数,
  "total_budget": 预算,
  "travel_date": "日期",
  "traveler_count": 人数,
  "preferences": ["偏好1", "偏好2"],
  "special_needs": "特殊需求（如有）"
}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_requirement}
        ]

        if context:
            messages.append({
                "role": "system",
                "content": f"上下文信息：{context}"
            })

        response = await self.chat_completion(messages)

        try:
            import json
            content = response["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, json.JSONDecodeError) as e:
            raise ValueError(f"解析DeepSeek响应失败: {e}")
