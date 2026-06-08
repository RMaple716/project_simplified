"""
协商事件总线 - 事件驱动协商可视化基础设施

功能:
1. 定义标准化协商事件结构
2. 事件发布/订阅机制（支持 WebSocket 和日志记录）
3. 事件日志收集与序列化

使用方式:
    from src.services.negotiation_event_bus import NegotiationEventBus

    event_bus = NegotiationEventBus()
    await event_bus.publish("task_001", {
        "eventType": "CFP",
        "sessionId": "task_001",
        ...
    })
"""
import uuid
import time
import json
import logging
from typing import Dict, Any, List, Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


# ==================== 标准事件类型常量 ====================

class NegotiationEventType:
    """协商事件类型枚举"""
    CFP = "CFP"             # 招标
    PROPOSE = "PROPOSE"     # 投标
    COUNTER = "COUNTER"     # 反提案
    ACCEPT = "ACCEPT"       # 接受
    REJECT = "REJECT"       # 拒绝
    FINALIZED = "FINALIZED" # 最终确定


class NegotiationPhase:
    """协商阶段枚举"""
    INIT = "INIT"
    CFP = "CFP"
    BIDDING = "BIDDING"
    NEGOTIATE = "NEGOTIATE"
    FINALIZING = "FINALIZING"
    FINALIZED = "FINALIZED"


# ==================== 事件结构生成 ====================

def create_negotiation_event(
    event_type: str,
    session_id: str,
    from_agent: str,
    to_agent: str,
    phase: str,
    proposal: Optional[Dict[str, Any]] = None,
    utility: Optional[Dict[str, float]] = None,
    route_preview: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    创建标准化协商事件

    Args:
        event_type: CFP | PROPOSE | COUNTER | ACCEPT | REJECT
        session_id: 任务编号
        from_agent: 发送方
        to_agent: 接收方
        phase: 当前阶段
        proposal: 提案内容 {price, eta, extraStops, ...}
        utility: 效用值 {dispatcher, vehicle, ...}
        route_preview: 路线预览 {vehicleId, coordinates}
        extra: 额外补充字段

    Returns:
        结构化事件字典
    """
    event = {
        "eventId": str(uuid.uuid4()),
        "sessionId": session_id,
        "timestamp": int(time.time() * 1000),
        "eventType": event_type,
        "fromAgent": from_agent,
        "toAgent": to_agent,
        "phase": phase,
        "proposal": proposal or {},
        "utility": utility or {},
        "routePreview": route_preview or {},
    }
    if extra:
        event.update(extra)
    return event


# ==================== 事件总线 ====================

class NegotiationEventBus:
    """
    协商事件总线（单例模式）

    职责:
    - 收集协商过程中产生的所有事件
    - 为 WebSocket 提供实时事件推送（通过注册的回调）
    - 生成完整的事件日志供后续保存
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        # sessionId -> [events]
        self._session_logs: Dict[str, List[Dict[str, Any]]] = {}
        # 外部 WebSocket 回调
        self._subscribers: List[Callable[[Dict[str, Any]], Awaitable[None]]] = []
        logger.info("[事件总线] 初始化完成")

    def subscribe(self, callback: Callable[[Dict[str, Any]], Awaitable[None]]):
        """注册外部回调（如 WebSocket 推送）"""
        self._subscribers.append(callback)
        logger.info(f"[事件总线] 注册回调 {callback.__name__}, 当前共 {len(self._subscribers)} 个")

    def unsubscribe(self, callback: Callable[[Dict[str, Any]], Awaitable[None]]):
        """取消注册外部回调"""
        if callback in self._subscribers:
            self._subscribers.remove(callback)
            logger.info(f"[事件总线] 移除回调 {callback.__name__}")

    async def publish(self, session_id: str, event: Dict[str, Any]):
        """
        发布协商事件

        1. 存入该 session 的事件日志
        2. 通知所有注册的回调（WebSocket 推送）

        Args:
            session_id: 任务/会话编号
            event: 事件字典（应由 create_negotiation_event 生成）
        """
        # 确保 eventId 存在
        if "eventId" not in event:
            event["eventId"] = str(uuid.uuid4())

        # 存入日志
        if session_id not in self._session_logs:
            self._session_logs[session_id] = []
        self._session_logs[session_id].append(event)

        logger.info(
            f"[事件总线] 发布事件 [{event.get('eventType')}] "
            f"session={session_id}, {event.get('fromAgent')}->{event.get('toAgent')}"
        )

        # 通知所有订阅者
        for callback in self._subscribers:
            try:
                await callback(event)
            except Exception as e:
                logger.warning(f"[事件总线] 回调执行失败: {e}")

    def get_session_log(self, session_id: str) -> List[Dict[str, Any]]:
        """获取指定会话的完整事件日志"""
        return self._session_logs.get(session_id, [])

    def get_all_sessions(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取所有会话的事件日志"""
        return dict(self._session_logs)

    def clear_session(self, session_id: str):
        """清空指定会话的事件日志"""
        if session_id in self._session_logs:
            del self._session_logs[session_id]

    def clear_all(self):
        """清空所有事件日志"""
        self._session_logs.clear()


# ==================== 便利辅助函数 ====================

def build_route_preview(
    vehicle_id: str,
    coordinates: List[List[float]],
    color: str = "#FF5733",
) -> Dict[str, Any]:
    """
    构建 routePreview 字段

    Args:
        vehicle_id: 车辆/路线标识
        coordinates: [[lng, lat], ...]
        color: 预览颜色

    Returns:
        routePreview 字典
    """
    return {
        "vehicleId": vehicle_id,
        "coordinates": coordinates,
        "color": color,
        "opacity": 0.6,
        "dashArray": "10, 10",
    }


# 全局单例
event_bus = NegotiationEventBus()
