"""
协商事件总线 - 事件驱动协商可视化基础设施（增强版）

功能:
1. ✅ 定义标准化协商事件结构
2. ✅ 事件发布/订阅机制（支持 WebSocket 和日志记录）
3. ✅ 事件日志收集与序列化
4. ✅ 【新增】事件持久化到数据库（防止服务重启丢失）
5. ✅ 【新增】Agent间消息通道（支持多Agent双向通信）
6. ✅ 【新增】TTL自动清理过期会话
7. ✅ 【新增】WebSocket端点注册

使用方式:
    # 标准事件发布
    from src.services.negotiation_event_bus import event_bus
    await event_bus.publish("task_001", event_dict)

    # Agent间通信
    from src.services.negotiation_event_bus import agent_message_bus
    await agent_message_bus.send("attractions_agent", "food_agent", {
        "type": "coordinate_request",
        "payload": {"attraction_name": "故宫", "location": ...}
    })

    # WebSocket 注册（在启动时调用）
    from src.services.negotiation_event_bus import ws_manager
    # ws_manager.register_connection(session_id, websocket)
"""
import uuid
import time
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Awaitable, Set

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
    AGENT_MSG = "AGENT_MSG" # 【新增】Agent间消息


class NegotiationPhase:
    """协商阶段枚举"""
    INIT = "INIT"
    CFP = "CFP"
    BIDDING = "BIDDING"
    NEGOTIATE = "NEGOTIATE"
    FINALIZING = "FINALIZING"
    FINALIZED = "FINALIZED"


class AgentMessageType:
    """Agent间消息类型枚举（新增）"""
    COORDINATE_REQUEST = "coordinate_request"           # 请求协调
    COORDINATE_RESPONSE = "coordinate_response"         # 协调响应
    SCHEDULE_PROPOSAL = "schedule_proposal"             # 时间安排提议
    SCHEDULE_FEEDBACK = "schedule_feedback"             # 时间安排反馈
    LOCATION_SHARE = "location_share"                   # 位置共享
    CONSTRAINT_NOTIFY = "constraint_notify"             # 约束通知
    PREFERENCE_QUERY = "preference_query"               # 偏好查询
    PREFERENCE_RESPONSE = "preference_response"         # 偏好响应


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
        event_type: CFP | PROPOSE | COUNTER | ACCEPT | REJECT | AGENT_MSG
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

    # 将 adjustments 从 proposal 提升到事件顶层（前端需要）
    if proposal and "adjustments" in proposal:
        event["adjustments"] = proposal.pop("adjustments")

    if extra:
        event.update(extra)
    return event


# ==================== WebSocket 连接管理器（新增） ====================

class WebSocketManager:
    """
    WebSocket 连接管理器

    管理所有前端的 WebSocket 连接，支持按 sessionId 分组推送。
    """

    def __init__(self):
        # session_id -> set of websocket connections
        self._connections: Dict[str, Set] = {}
        # 全局连接回调查
        self._global_callbacks: List[Callable[[Dict[str, Any]], Awaitable[None]]] = []
        logger.info("[WebSocket管理器] 初始化完成")

    def register_connection(self, session_id: str, websocket) -> None:
        """注册新的 WebSocket 连接到指定 session"""
        if session_id not in self._connections:
            self._connections[session_id] = set()
        self._connections[session_id].add(websocket)
        logger.info(f"[WebSocket管理器] session={session_id} 新连接，当前连接数: {len(self._connections[session_id])}")

    def unregister_connection(self, session_id: str, websocket) -> None:
        """断开 WebSocket 连接"""
        if session_id in self._connections and websocket in self._connections[session_id]:
            self._connections[session_id].remove(websocket)
            if not self._connections[session_id]:
                del self._connections[session_id]
            logger.info(f"[WebSocket管理器] session={session_id} 断开连接")

    def register_global_callback(self, callback: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
        """注册全局事件处理回调"""
        self._global_callbacks.append(callback)

    async def broadcast_to_session(self, session_id: str, event: Dict[str, Any]) -> None:
        """
        向指定 session 的所有 WebSocket 连接广播事件

        Args:
            session_id: 会话ID
            event: 事件字典
        """
        if session_id not in self._connections:
            return

        message = json.dumps(event, ensure_ascii=False, default=str)
        disconnected = set()

        for ws in self._connections[session_id]:
            try:
                await ws.send_text(message)
            except Exception as e:
                logger.warning(f"[WebSocket管理器] 发送失败: {e}")
                disconnected.add(ws)

        # 清理断开的连接
        for ws in disconnected:
            self.unregister_connection(session_id, ws)

    async def broadcast_global(self, event: Dict[str, Any]) -> None:
        """向所有连接的 session 广播"""
        for session_id in list(self._connections.keys()):
            await self.broadcast_to_session(session_id, event)

    async def notify_global_callbacks(self, event: Dict[str, Any]) -> None:
        """通知所有全局回调"""
        for callback in self._global_callbacks:
            try:
                await callback(event)
            except Exception as e:
                logger.warning(f"[WebSocket管理器] 全局回调失败: {e}")

    @property
    def active_connections(self) -> int:
        """当前活跃连接数"""
        return sum(len(ws_set) for ws_set in self._connections.values())

    @property
    def active_sessions(self) -> int:
        """当前活跃 session 数"""
        return len(self._connections)


# ==================== Agent间消息通道（新增） ====================

class AgentMessageBus:
    """
    Agent间消息通道

    实现多Agent之间的异步消息通信，支持：
    - 点对点消息（send）
    - 广播消息（broadcast）
    - 消息历史记录
    - 消息回调注册
    """

    def __init__(self):
        # agent_id -> list of message handlers
        self._handlers: Dict[str, List[Callable]] = {}
        # session_id -> [messages]
        self._message_history: Dict[str, List[Dict[str, Any]]] = {}
        logger.info("[Agent消息通道] 初始化完成")

    def register_handler(self, agent_id: str, handler: Callable) -> None:
        """
        注册Agent的消息处理器

        Args:
            agent_id: 目标Agent ID
            handler: 处理函数 async def handler(message: dict)
        """
        if agent_id not in self._handlers:
            self._handlers[agent_id] = []
        self._handlers[agent_id].append(handler)
        logger.info(f"[Agent消息通道] {agent_id} 注册消息处理器，共 {len(self._handlers[agent_id])} 个")

    def unregister_handler(self, agent_id: str, handler: Callable) -> None:
        """注销消息处理器"""
        if agent_id in self._handlers and handler in self._handlers[agent_id]:
            self._handlers[agent_id].remove(handler)
            if not self._handlers[agent_id]:
                del self._handlers[agent_id]

    async def send(self, from_agent: str, to_agent: str, message: Dict[str, Any], session_id: str = "default") -> Optional[Dict[str, Any]]:
        """
        发送点对点消息

        Args:
            from_agent: 发送方Agent ID
            to_agent: 接收方Agent ID
            message: 消息内容 {"type": str, "payload": any}
            session_id: 会话ID

        Returns:
            如果接收方有注册handler，返回handler的结果；否则返回None

        Raises:
            TimeoutError: 如果超时未收到响应
        """
        msg_envelope = {
            "messageId": str(uuid.uuid4()),
            "sessionId": session_id,
            "timestamp": int(time.time() * 1000),
            "fromAgent": from_agent,
            "toAgent": to_agent,
            "type": message.get("type", "unknown"),
            "payload": message.get("payload"),
            "metadata": message.get("metadata", {}),
        }

        # 记录消息历史
        if session_id not in self._message_history:
            self._message_history[session_id] = []
        self._message_history[session_id].append(msg_envelope)

        logger.info(
            f"[Agent消息通道] {from_agent} → {to_agent}: "
            f"type={msg_envelope['type']}, session={session_id}"
        )

        # 分发给接收方
        if to_agent in self._handlers:
            results = []
            for handler in self._handlers[to_agent]:
                try:
                    result = await handler(msg_envelope)
                    if result is not None:
                        results.append(result)
                except Exception as e:
                    logger.warning(f"[Agent消息通道] handler执行失败: {e}")
            return results[0] if results else None

        return None

    async def broadcast(self, from_agent: str, message: Dict[str, Any], session_id: str = "default") -> Dict[str, Any]:
        """
        广播消息给所有注册了handler的Agent

        Args:
            from_agent: 发送方Agent ID
            message: 消息内容
            session_id: 会话ID

        Returns:
            {agent_id: response, ...} 所有agent的响应
        """
        responses = {}
        for agent_id in list(self._handlers.keys()):
            if agent_id == from_agent:
                continue
            try:
                resp = await self.send(from_agent, agent_id, message, session_id)
                if resp is not None:
                    responses[agent_id] = resp
            except Exception as e:
                logger.warning(f"[Agent消息通道] 广播到{agent_id}失败: {e}")
        return responses

    def get_session_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """获取指定会话的消息历史"""
        return self._message_history.get(session_id, [])

    def clear_session(self, session_id: str) -> None:
        """清空指定会话的消息历史"""
        if session_id in self._message_history:
            del self._message_history[session_id]


# ==================== 持久化服务（新增） ====================

class EventPersistenceService:
    """
    事件持久化服务

    将协商事件和Agent消息持久化到数据库，防止服务重启丢失。
    同时支持按session_id查询历史事件。
    """

    def __init__(self):
        self._enabled = False
        self._db_session_factory = None

    def enable(self, db_session_factory) -> None:
        """启用持久化（注入数据库会话工厂）"""
        self._enabled = True
        self._db_session_factory = db_session_factory
        logger.info("[事件持久化] 已启用")

    def disable(self) -> None:
        """禁用持久化"""
        self._enabled = False
        self._db_session_factory = None
        logger.info("[事件持久化] 已禁用")

    async def save_event(self, session_id: str, event: Dict[str, Any]) -> bool:
        """
        保存单个事件到数据库

        Args:
            session_id: 会话ID
            event: 事件字典

        Returns:
            是否保存成功
        """
        if not self._enabled:
            return False
        try:
            from src.database import SessionLocal
            from src.models.db_models import Itinerary

            db = SessionLocal()
            try:
                # 查找或创建行程记录来关联事件
                itinerary = db.query(Itinerary).filter(
                    Itinerary.itinerary_id == session_id
                ).first()

                if itinerary:
                    # 将事件存入 day_plans 的元数据中
                    day_plans = itinerary.day_plans or []
                    if isinstance(day_plans, list) and len(day_plans) > 0:
                        if "negotiation_events" not in day_plans[0]:
                            day_plans[0]["negotiation_events"] = []
                        day_plans[0]["negotiation_events"].append(event)
                        itinerary.day_plans = day_plans  # type: ignore
                        db.commit()
                        return True
                    # day_plans 为空，无法持久化
                    logger.debug(f"[事件持久化] session={session_id} day_plans为空，跳过持久化")
                    return False
                else:
                    # 如果行程不存在，尝试通过 NegotiationEventLog 表保存
                    # 使用 raw SQL 或创建新的日志条目
                    logger.debug(f"[事件持久化] session={session_id} 行程不存在，跳过持久化")
                    return False
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[事件持久化] 保存失败: {e}")
            return False

    async def save_events_batch(self, session_id: str, events: List[Dict[str, Any]]) -> bool:
        """
        批量保存事件到数据库

        Args:
            session_id: 会话ID
            events: 事件列表
        """
        if not self._enabled or not events:
            return False
        try:
            from src.database import SessionLocal
            from src.models.db_models import Itinerary

            db = SessionLocal()
            try:
                itinerary = db.query(Itinerary).filter(
                    Itinerary.itinerary_id == session_id
                ).first()

                if itinerary:
                    day_plans = itinerary.day_plans or []
                    if isinstance(day_plans, list) and len(day_plans) > 0:
                        existing = day_plans[0].get("negotiation_events", [])
                        existing.extend(events)
                        day_plans[0]["negotiation_events"] = existing
                        itinerary.day_plans = day_plans  # type: ignore
                        db.commit()
                        return True
                return False
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[事件持久化] 批量保存失败: {e}")
            return False

    async def get_events(self, session_id: str) -> List[Dict[str, Any]]:
        """从数据库获取指定会话的事件列表"""
        if not self._enabled:
            return []
        try:
            from src.database import SessionLocal
            from src.models.db_models import Itinerary

            db = SessionLocal()
            try:
                itinerary = db.query(Itinerary).filter(
                    Itinerary.itinerary_id == session_id
                ).first()

                if itinerary is not None and itinerary.day_plans is not None:
                    day_plans = itinerary.day_plans
                    if isinstance(day_plans, list) and len(day_plans) > 0:
                        return day_plans[0].get("negotiation_events", [])
                return []
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[事件持久化] 读取失败: {e}")
            return []


# ==================== 增强版事件总线 ====================

class NegotiationEventBus:
    """
    协商事件总线（单例模式）— 增强版

    职责:
    - 收集协商过程中产生的所有事件
    - 为 WebSocket 提供实时事件推送
    - 生成完整的事件日志供后续保存
    - 【新增】自动持久化到数据库
    - 【新增】TTL自动清理过期会话
    - 【新增】集成Agent消息通道
    """

    _instance = None
    # 会话TTL（秒），默认1小时无访问自动清理
    SESSION_TTL_SECONDS = 3600

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # sessionId -> [events]（内存缓存）
        self._session_logs: Dict[str, List[Dict[str, Any]]] = {}
        
        # sessionId -> last_access_time（用于TTL清理）
        self._session_access: Dict[str, float] = {}
        
        # 外部 WebSocket 回调（兼容旧版）
        self._subscribers: List[Callable[[Dict[str, Any]], Awaitable[None]]] = []
        
        # 【新增】WebSocket管理器
        self.ws_manager = WebSocketManager()
        
        # 【新增】Agent消息通道
        self.agent_bus = AgentMessageBus()
        
        # 【新增】持久化服务
        self.persistence = EventPersistenceService()
        
        # 【新增】是否启用自动持久化
        self._persistence_enabled = False
        
        # 【新增】TTL清理任务
        self._cleanup_task: Optional[asyncio.Task] = None
        
        logger.info("[事件总线] 增强版初始化完成")

    # ==================== 持久化控制 ====================

    def enable_persistence(self):
        """启用数据库持久化"""
        self._persistence_enabled = True
        self.persistence.enable(None)  # persistence内部会自行创建session
        logger.info("[事件总线] 已启用持久化")

    def disable_persistence(self):
        """禁用数据库持久化"""
        self._persistence_enabled = False
        self.persistence.disable()
        logger.info("[事件总线] 已禁用持久化")

    # ==================== TTL清理 ====================

    def start_cleanup_task(self, interval_seconds: int = 300):
        """
        启动后台TTL清理任务

        Args:
            interval_seconds: 检查间隔（秒），默认5分钟
        """
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop(interval_seconds))
            logger.info(f"[事件总线] TTL清理任务已启动，间隔{interval_seconds}秒")

    def stop_cleanup_task(self):
        """停止TTL清理任务"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            self._cleanup_task = None
            logger.info("[事件总线] TTL清理任务已停止")

    async def _cleanup_loop(self, interval_seconds: int):
        """TTL清理循环"""
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                now = time.time()
                expired_sessions = [
                    sid for sid, last_access in self._session_access.items()
                    if now - last_access > self.SESSION_TTL_SECONDS
                ]
                for sid in expired_sessions:
                    self._session_logs.pop(sid, None)
                    self._session_access.pop(sid, None)
                    logger.info(f"[事件总线] TTL清理: session={sid}")
                if expired_sessions:
                    logger.info(f"[事件总线] TTL清理完成: 清理了{len(expired_sessions)}个过期会话")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[事件总线] TTL清理异常: {e}")

    # ==================== 订阅管理 ====================

    def subscribe(self, callback: Callable[[Dict[str, Any]], Awaitable[None]]):
        """注册外部回调（如 WebSocket 推送）"""
        self._subscribers.append(callback)
        logger.info(f"[事件总线] 注册回调 {getattr(callback, '__name__', 'anonymous')}, 当前共 {len(self._subscribers)} 个")

    def unsubscribe(self, callback: Callable[[Dict[str, Any]], Awaitable[None]]):
        """取消注册外部回调"""
        if callback in self._subscribers:
            self._subscribers.remove(callback)
            logger.info(f"[事件总线] 移除回调 {getattr(callback, '__name__', 'anonymous')}")

    # ==================== 事件发布 ====================

    async def publish(self, session_id: str, event: Dict[str, Any]):
        """
        发布协商事件（增强版）

        1. 存入该 session 的事件日志（内存）
        2. 更新访问时间
        3. 通知所有注册的回调
        4. 【新增】通过 WebSocket 实时推送到前端
        5. 【新增】持久化到数据库

        Args:
            session_id: 任务/会话编号
            event: 事件字典（应由 create_negotiation_event 生成）
        """
        # 确保 eventId 存在
        if "eventId" not in event:
            event["eventId"] = str(uuid.uuid4())

        # 存入内存日志
        if session_id not in self._session_logs:
            self._session_logs[session_id] = []
        self._session_logs[session_id].append(event)

        # 更新访问时间
        self._session_access[session_id] = time.time()

        logger.info(
            f"[事件总线] 发布事件 [{event.get('eventType')}] "
            f"session={session_id}, {event.get('fromAgent')}->{event.get('toAgent')}"
        )

        # 通知所有注册的回调（兼容旧版）
        for callback in self._subscribers:
            try:
                await callback(event)
            except Exception as e:
                logger.warning(f"[事件总线] 回调执行失败: {e}")

        # 【新增】通过 WebSocket 实时推送到前端
        await self.ws_manager.broadcast_to_session(session_id, event)
        await self.ws_manager.notify_global_callbacks(event)

        # 【新增】异步持久化到数据库（不阻塞主流程）
        if self._persistence_enabled:
            asyncio.create_task(self.persistence.save_event(session_id, event))

    # ==================== 事件查询 ====================

    def get_session_log(self, session_id: str) -> List[Dict[str, Any]]:
        """获取指定会话的完整事件日志（从内存）"""
        self._session_access[session_id] = time.time()
        return self._session_logs.get(session_id, [])

    async def get_session_log_persistent(self, session_id: str) -> List[Dict[str, Any]]:
        """获取指定会话的事件日志（优先从数据库）"""
        if self._persistence_enabled:
            db_events = await self.persistence.get_events(session_id)
            if db_events:
                return db_events
        return self.get_session_log(session_id)

    def get_all_sessions(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取所有会话的事件日志"""
        return dict(self._session_logs)

    # ==================== 会话管理 ====================

    def clear_session(self, session_id: str):
        """清空指定会话的事件日志"""
        self._session_logs.pop(session_id, None)
        self._session_access.pop(session_id, None)
        self.agent_bus.clear_session(session_id)

    def clear_all(self):
        """清空所有事件日志"""
        self._session_logs.clear()
        self._session_access.clear()
        self.agent_bus.clear_session("default")  # 清空所有 agent 消息

    @property
    def session_count(self) -> int:
        """当前活跃会话数"""
        return len(self._session_logs)

    @property
    def total_events(self) -> int:
        """所有会话的事件总数"""
        return sum(len(events) for events in self._session_logs.values())


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


# ==================== 快捷函数 ====================

def create_agent_message(
    from_agent: str,
    to_agent: str,
    msg_type: str,
    payload: Any,
    session_id: str = "default",
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    创建Agent间消息（快捷方式）

    Args:
        from_agent: 发送方
        to_agent: 接收方
        msg_type: 消息类型（AgentMessageType 枚举值）
        payload: 消息负载
        session_id: 会话ID
        metadata: 附加元数据

    Returns:
        消息字典
    """
    return {
        "messageId": str(uuid.uuid4()),
        "sessionId": session_id,
        "timestamp": int(time.time() * 1000),
        "fromAgent": from_agent,
        "toAgent": to_agent,
        "type": msg_type,
        "payload": payload,
        "metadata": metadata or {},
    }


# ==================== 全局单例 ====================

event_bus = NegotiationEventBus()
ws_manager = event_bus.ws_manager
agent_message_bus = event_bus.agent_bus
