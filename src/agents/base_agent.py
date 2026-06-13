"""
智能体基类（增强版 — 支持Agent间通信）

【新增功能】
1. ✅ Agent间消息收发（通过 AgentMessageBus）
2. ✅ 消息处理器注册（自动响应其他Agent的请求）
3. ✅ 协商事件发布（参与协商流程）
4. ✅ LLM驱动的消息响应（可基于大模型生成回复）
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable, Awaitable
from src.services.deepseek_client import DeepSeekClient
from src.services.negotiation_event_bus import (
    event_bus,
    agent_message_bus,
    create_negotiation_event,
    create_agent_message,
    NegotiationEventType,
    NegotiationPhase,
    AgentMessageType,
)


class BaseAgent(ABC):
    """智能体基类（增强版）"""

    def __init__(self, agent_id: str, name: str, description: str):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.llm_client = DeepSeekClient()
        # 【新增】是否已注册消息处理器
        self._handler_registered = False

    @abstractmethod
    async def execute(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行任务"""
        pass

    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """获取智能体能力列表"""
        pass

    # ==================== 新增：Agent间通信能力 ====================

    async def register_message_handlers(self):
        """
        注册消息处理器（在Agent初始化后调用）

        注册后，其他Agent可以通过 agent_message_bus.send() 向此Agent发送消息，
        此Agent的 on_message() 方法会被自动调用。
        """
        if self._handler_registered:
            return
        agent_message_bus.register_handler(self.agent_id, self._handle_agent_message)
        self._handler_registered = True
        print(f"  ✅ Agent '{self.name}' ({self.agent_id}) 已注册消息处理器")

    async def unregister_message_handlers(self):
        """注销消息处理器"""
        if self._handler_registered:
            agent_message_bus.unregister_handler(self.agent_id, self._handle_agent_message)
            self._handler_registered = False

    async def _handle_agent_message(self, message: dict) -> Optional[dict]:
        """
        内部消息处理器（自动调用 on_message）

        Args:
            message: 收到的消息 {"fromAgent", "type", "payload", ...}

        Returns:
            Agent的响应（可选）
        """
        try:
            return await self.on_message(message)
        except Exception as e:
            print(f"  ⚠️ Agent '{self.name}' 处理消息失败: {e}")
            return {"error": str(e), "agent_id": self.agent_id}

    async def on_message(self, message: dict) -> Optional[dict]:
        """
        【子类可重写】处理收到的Agent消息

        默认实现：记录日志并返回基本信息。
        子类可以重写此方法来实现特定的消息处理逻辑。

        Args:
            message: {
                "messageId": str,
                "sessionId": str,
                "fromAgent": str,
                "type": str (AgentMessageType),
                "payload": any,
                "metadata": dict,
                "timestamp": int
            }

        Returns:
            响应字典（可选），如果返回None则发送方不会收到响应
        """
        msg_type = message.get("type", "unknown")
        from_agent = message.get("fromAgent", "unknown")

        print(f"  📬 Agent '{self.name}' 收到来自 '{from_agent}' 的消息: type={msg_type}")

        return {
            "status": "received",
            "agent_id": self.agent_id,
            "ack": True,
            "original_type": msg_type,
        }

    async def send_message(
        self,
        to_agent: str,
        msg_type: str,
        payload: Any,
        session_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
        publish_event: bool = True
    ) -> Optional[dict]:
        """
        发送消息给另一个Agent

        Args:
            to_agent: 目标Agent ID（如 "food_agent"）
            msg_type: 消息类型（AgentMessageType 枚举值）
            payload: 消息内容
            session_id: 会话ID
            metadata: 附加元数据
            publish_event: 是否同时发布为协商事件

        Returns:
            目标Agent的响应（如果有）
        """
        response = await agent_message_bus.send(
            from_agent=self.agent_id,
            to_agent=to_agent,
            message={
                "type": msg_type,
                "payload": payload,
                "metadata": metadata or {},
            },
            session_id=session_id,
        )

        # 同时发布事件到事件总线
        if publish_event:
            await event_bus.publish(
                session_id,
                create_negotiation_event(
                    event_type=NegotiationEventType.AGENT_MSG,
                    session_id=session_id,
                    from_agent=self.agent_id,
                    to_agent=to_agent,
                    phase=NegotiationPhase.NEGOTIATE,
                    proposal=payload,
                    extra={
                        "agentMsgType": msg_type,
                        "metadata": metadata or {},
                    },
                )
            )

        return response

    async def broadcast_message(
        self,
        msg_type: str,
        payload: Any,
        session_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        广播消息给所有其他Agent

        Args:
            msg_type: 消息类型
            payload: 消息内容
            session_id: 会话ID
            metadata: 附加元数据

        Returns:
            {agent_id: response, ...} 所有Agent的响应
        """
        return await agent_message_bus.broadcast(
            from_agent=self.agent_id,
            message={
                "type": msg_type,
                "payload": payload,
                "metadata": metadata or {},
            },
            session_id=session_id,
        )

    async def query_agent(self, to_agent: str, query: str, session_id: str = "default") -> Optional[dict]:
        """
        向另一个Agent发起查询（便捷方法）

        Args:
            to_agent: 目标Agent ID
            query: 查询内容（自然语言）
            session_id: 会话ID

        Returns:
            查询结果
        """
        return await self.send_message(
            to_agent=to_agent,
            msg_type=AgentMessageType.PREFERENCE_QUERY,
            payload={"query": query},
            session_id=session_id,
        )

    async def share_location(self, to_agent: str, location_data: dict, session_id: str = "default") -> Optional[dict]:
        """
        向另一个Agent共享位置信息（便捷方法）

        Args:
            to_agent: 目标Agent ID
            location_data: {"name": str, "lat": float, "lng": float, ...}
            session_id: 会话ID
        """
        return await self.send_message(
            to_agent=to_agent,
            msg_type=AgentMessageType.LOCATION_SHARE,
            payload=location_data,
            session_id=session_id,
        )

    async def propose_schedule(self, to_agent: str, schedule_data: dict, session_id: str = "default") -> Optional[dict]:
        """
        向另一个Agent提出时间安排建议（便捷方法）

        Args:
            to_agent: 目标Agent ID
            schedule_data: {"attraction": str, "start_time": str, "end_time": str, ...}
            session_id: 会话ID
        """
        return await self.send_message(
            to_agent=to_agent,
            msg_type=AgentMessageType.SCHEDULE_PROPOSAL,
            payload=schedule_data,
            session_id=session_id,
        )

    # ==================== LLM调用能力 ====================

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
        """
        解析JSON格式的响应，支持处理被截断的JSON
        """
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
                return self._fix_truncated_json(json_text)

        # 尝试提取最外层的 {} 块
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
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

        # 尝试3：如果存在不完整的键值对（如 "key": 后内容不完整），删除最后一个键值对
        # 查找最后一个完整的 "key": value 结构
        last_key_match = fixed_json.rfind('"')
        if last_key_match > fixed_json.rfind('{'):
            # 尝试从上一个逗号处截断
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
