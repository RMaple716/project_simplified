"""
协商事件查询器

从数据库读取历史协商事件记录，供前端和历史对比使用。
"""

import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class NegotiationEventQuerier:
    """
    协商事件查询器（从数据库读取历史记录）

    提供按 session_id / task_id 查询历史事件的方法。
    与 NegotiationEventPublisher 配合使用。
    """

    def __init__(self):
        self._persistence = None

    def bind_persistence(self, persistence) -> None:
        """绑定持久化服务实例"""
        self._persistence = persistence

    async def get_session_events(self, session_id: str) -> List[dict]:
        """
        获取某个会话的全部事件（按时间排序）

        Args:
            session_id: 会话ID

        Returns:
            事件列表，按时间升序排列
        """
        if self._persistence is None:
            logger.warning("[事件查询器] 未绑定持久化服务")
            return []

        return await self._persistence.get_events(session_id)

    async def get_task_events(self, task_id: str) -> List[dict]:
        """
        获取某个任务的全部事件

        Args:
            task_id: 任务ID

        Returns:
            事件列表，按时间升序排列
        """
        if self._persistence is None:
            logger.warning("[事件查询器] 未绑定持久化服务")
            return []

        return await self._persistence.get_events_by_task(task_id)

    async def get_session_summary(self, session_id: str) -> Optional[dict]:
        """
        获取会话的简要统计信息

        Args:
            session_id: 会话ID

        Returns:
            {"session_id": str, "total_events": int, "event_types": dict, "first_event_time": str, "last_event_time": str}
            如果找不到返回 None
        """
        events = await self.get_session_events(session_id)
        if not events:
            return None

        event_types = {}
        for evt in events:
            etype = evt.get("event_type", "UNKNOWN")
            event_types[etype] = event_types.get(etype, 0) + 1

        return {
            "session_id": session_id,
            "total_events": len(events),
            "event_types": event_types,
            "first_event_time": events[0].get("timestamp", ""),
            "last_event_time": events[-1].get("timestamp", ""),
        }


# 全局单例
event_querier = NegotiationEventQuerier()