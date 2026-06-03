"""
智能体基类
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from src.services.deepseek_client import DeepSeekClient

class BaseAgent(ABC):
    """智能体基类"""

    def __init__(self, agent_id: str, name: str, description: str):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.llm_client = DeepSeekClient()

    @abstractmethod
    async def execute(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行任务"""
        pass

    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """获取智能体能力列表"""
        pass

    async def call_llm(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """调用大语言模型"""
        response = await self.llm_client.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response["choices"][0]["message"]["content"]

    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        """解析JSON格式的响应"""
        import json
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            # 尝试提取JSON代码块
            import re
            json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            raise ValueError(f"无法解析响应为JSON: {response_text}")
