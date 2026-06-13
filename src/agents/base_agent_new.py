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
        """解析JSON格式的响应，支持处理被截断的JSON"""
        import json
        import re

        # 首先尝试直接解析
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        # 尝试提取JSON代码块
        json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
        if json_match:
            json_text = json_match.group(1)
            try:
                return json.loads(json_text)
            except json.JSONDecodeError:
                # 尝试修复被截断的JSON
                return self._fix_truncated_json(json_text)

        # 尝试查找第一个{和最后一个}之间的内容
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')
        if start_idx != -1 and end_idx != -1:
            json_text = response_text[start_idx:end_idx + 1]
            try:
                return json.loads(json_text)
            except json.JSONDecodeError:
                result = self._fix_truncated_json(json_text)
                if result:
                    return result

        # 最后尝试：从后向前逐步截断查找合法JSON
        start_idx = response_text.find('{')
        if start_idx != -1:
            search_end = response_text.rfind('}')
            if search_end == -1:
                search_end = len(response_text)
            for end_idx in range(search_end, start_idx, -1):
                chunk = response_text[start_idx:end_idx + 1]
                if chunk.rstrip()[-1] in (',', ':'):
                    continue
                try:
                    return json.loads(chunk)
                except json.JSONDecodeError:
                    continue

        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"[BaseAgent] 无法解析响应为JSON，返回空字典。原始文本前200字符: {response_text[:200]}")
        return {}

    def _fix_truncated_json(self, json_text: str) -> Dict[str, Any]:
        """尝试修复被截断的JSON（增强版）"""
        import json

        # 尝试1：补充缺失的闭合括号
        open_braces = json_text.count('{')
        close_braces = json_text.count('}')
        open_brackets = json_text.count('[')
        close_brackets = json_text.count(']')

        fixed_json = json_text
        if open_brackets > close_brackets:
            fixed_json += ']' * (open_brackets - close_brackets)
        if open_braces > close_braces:
            fixed_json += '}' * (open_braces - close_braces)

        # 如果最后一个字符是引号开头（不完整的字符串值），移除它
        stripped = fixed_json.rstrip()
        if stripped.endswith('"') and not stripped.endswith('\\"'):
            # 检查是否可能是不完整的字符串值
            pass

        try:
            return json.loads(fixed_json)
        except json.JSONDecodeError:
            pass

        # 尝试2：删除最后一个不完整元素（逗号后的内容）
        last_comma_idx = fixed_json.rfind(',')
        if last_comma_idx != -1:
            remaining = fixed_json[last_comma_idx + 1:].strip()
            if not remaining.startswith('"'):
                fixed_json = fixed_json[:last_comma_idx]
                open_braces = fixed_json.count('{')
                close_braces = fixed_json.count('}')
                open_brackets = fixed_json.count('[')
                close_brackets = fixed_json.count(']')
                if open_brackets > close_brackets:
                    fixed_json += ']' * (open_brackets - close_brackets)
                if open_braces > close_braces:
                    fixed_json += '}' * (open_braces - close_braces)
                try:
                    return json.loads(fixed_json)
                except json.JSONDecodeError:
                    pass

        # 尝试3：如果存在不完整的键值对，删除最后一个键值对
        last_key_match = fixed_json.rfind('"')
        if last_key_match > fixed_json.rfind('{'):
            next_comma = fixed_json.rfind(',', 0, last_key_match)
            if next_comma != -1:
                fixed_json = fixed_json[:next_comma]
                open_braces = fixed_json.count('{')
                close_braces = fixed_json.count('}')
                open_brackets = fixed_json.count('[')
                close_brackets = fixed_json.count(']')
                if open_brackets > close_brackets:
                    fixed_json += ']' * (open_brackets - close_brackets)
                if open_braces > close_braces:
                    fixed_json += '}' * (open_braces - close_braces)
                try:
                    return json.loads(fixed_json)
                except json.JSONDecodeError:
                    pass

        return {}
