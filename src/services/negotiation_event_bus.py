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
    # ===== 任务执行进度事件 =====
    TASK_STARTED = "TASK_STARTED"                # 批次任务开始
    SUB_TASK_STARTED = "SUB_TASK_STARTED"         # 子任务开始执行
    SUB_TASK_COMPLETED = "SUB_TASK_COMPLETED"     # 子任务完成
    SUB_TASK_FAILED = "SUB_TASK_FAILED"           # 子任务失败
    NEGOTIATION_STARTED = "NEGOTIATION_STARTED"   # 协商阶段开始
    ITINERARY_CREATED = "ITINERARY_CREATED"       # 行程已创建


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
        event["extra"] = extra
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
        # 【P2】Agent共享信息池 — 所有Agent可读写
        # session_id -> {"shared_context": {key: value}, ...}
        self._shared_contexts: Dict[str, Dict[str, Any]] = {}
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
        """清空指定会话的消息历史（含共享上下文）"""
        if session_id in self._message_history:
            del self._message_history[session_id]
        self._shared_contexts.pop(session_id, None)

    # ==================== 【P2】共享信息池 ====================

    def get_shared_context(self, session_id: str) -> Dict[str, Any]:
        """
        获取指定会话的共享上下文（读写均通过此对象引用）

        Args:
            session_id: 会话ID

        Returns:
            共享上下文字典（空字典表示未初始化）
        """
        if session_id not in self._shared_contexts:
            self._shared_contexts[session_id] = {}
        return self._shared_contexts[session_id]

    def update_shared_context(self, session_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新指定会话的共享上下文

        Args:
            session_id: 会话ID
            updates: 要更新的键值对

        Returns:
            更新后的共享上下文
        """
        ctx = self.get_shared_context(session_id)
        ctx.update(updates)
        logger.info(f"[Agent消息通道] session={session_id}: 共享上下文已更新, keys={list(updates.keys())}")
        return ctx

    def get_shared_context_value(self, session_id: str, key: str, default: Any = None) -> Any:
        """
        从共享上下文获取指定键的值

        Args:
            session_id: 会话ID
            key: 键名
            default: 默认值

        Returns:
            键对应的值，不存在返回default
        """
        ctx = self.get_shared_context(session_id)
        return ctx.get(key, default)

    def clear_shared_context(self, session_id: str) -> None:
        """清空指定会话的共享上下文"""
        if session_id in self._shared_contexts:
            del self._shared_contexts[session_id]
            logger.info(f"[Agent消息通道] session={session_id}: 共享上下文已清空")

    # ==================== 【改造方案 4.1】Agent间信息共享 ====================

    async def share_agent_info(
        self,
        agent_id: str,
        session_id: str,
        info_type: str,
        info_data: dict,
    ) -> None:
        """
        Agent 向共享信息池写入领域知识（改造方案 4.1.1）

        其他 Agent 可以通过 get_shared_agent_info() 读取。
        写入时会自动通知已订阅该信息类型的所有 Agent。

        Args:
            agent_id: 发送 Agent 的 ID
            session_id: 会话ID
            info_type: 信息类型
                "attractions_info" | "transport_info" | "food_info" | "hotel_info"
            info_data: 领域知识数据
        """
        import time
        ctx = self.get_shared_context(session_id)
        if "agent_shared_info" not in ctx:
            ctx["agent_shared_info"] = {}
        ctx["agent_shared_info"][agent_id] = {
            "type": info_type,
            "data": info_data,
            "timestamp": int(time.time() * 1000),
        }

        # 通知其他 Agent（可选）
        await self.broadcast(
            from_agent=agent_id,
            message={
                "type": AgentMessageType.LOCATION_SHARE,
                "payload": {
                    "action": "info_shared",
                    "info_type": info_type,
                    "summary": f"{agent_id} shared {info_type} info",
                }
            },
            session_id=session_id,
        )

    def get_shared_agent_info(
        self,
        session_id: str,
        agent_id: Optional[str] = None,
        info_type: Optional[str] = None,
    ) -> dict:
        """
        从共享信息池读取 Agent 的领域信息（改造方案 4.1.1）

        Args:
            session_id: 会话ID
            agent_id: Agent ID，None 返回所有 Agent 的信息
            info_type: 信息类型过滤，None 不过滤

        Returns:
            Agent 共享信息字典
        """
        ctx = self.get_shared_context(session_id)
        all_info = ctx.get("agent_shared_info", {})

        if agent_id:
            return all_info.get(agent_id, {})

        if info_type:
            return {
                aid: info for aid, info in all_info.items()
                if info.get("type") == info_type
            }

        return all_info


# ==================== 持久化服务 ====================

class EventPersistenceService:
    """
    事件持久化服务

    将协商事件持久化到 negotiation_event_logs 表。
    支持单个事件保存、批量保存、按 session_id/task_id 查询历史事件。
    所有数据库操作都 try/except 包裹，失败不影响主协商流程。
    """

    def __init__(self):
        self._enabled = False
        self._batch_mode = False
        self._buffer = []

    def enable(self, batch_mode: bool = False) -> None:
        """启用持久化"""
        self._enabled = True
        self._batch_mode = batch_mode
        logger.info(f"[事件持久化] 已启用 (batch_mode={batch_mode})")

    def disable(self) -> None:
        """禁用持久化"""
        self._enabled = False
        self._buffer.clear()
        logger.info("[事件持久化] 已禁用")

    async def _persist_one(self, session_id: str, event: dict) -> bool:
        """将单个事件写入 negotiation_event_logs 表"""
        try:
            from src.database import SessionLocal
            from src.models.db_models import NegotiationEventLog

            db = SessionLocal()
            try:
                extra_fields = {k: v for k, v in event.items()
                                if k not in ("eventId", "sessionId", "timestamp", "eventType",
                                             "fromAgent", "toAgent", "phase", "proposal", "utility",
                                             "routePreview")}
                log_entry = NegotiationEventLog(
                    session_id=session_id,
                    task_id=event.get("task_id") or event.get("sessionId"),
                    event_type=event.get("eventType", ""),
                    phase=event.get("phase", ""),
                    from_agent=event.get("fromAgent"),
                    to_agent=event.get("toAgent"),
                    proposal=json.dumps(event.get("proposal", {}), ensure_ascii=False),
                    utility=json.dumps(event.get("utility", {}), ensure_ascii=False),
                    extra=json.dumps(extra_fields, ensure_ascii=False),
                )
                db.add(log_entry)
                db.commit()
                return True
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[事件持久化] 保存失败（非致命）: {e}")
            return False

    async def save_event(self, session_id: str, event: dict) -> bool:
        """保存单个事件到数据库"""
        if not self._enabled:
            return False
        if self._batch_mode:
            self._buffer.append((session_id, event))
            return True
        return await self._persist_one(session_id, event)

    async def flush_buffer(self) -> int:
        """将缓冲区中的事件批量写入数据库"""
        if not self._buffer:
            return 0
        batch = self._buffer[:]
        self._buffer = []
        success_count = 0
        try:
            from src.database import SessionLocal
            from src.models.db_models import NegotiationEventLog

            db = SessionLocal()
            try:
                entries = []
                for sid, evt in batch:
                    extra_fields = {k: v for k, v in evt.items()
                                    if k not in ("eventId", "sessionId", "timestamp", "eventType",
                                                 "fromAgent", "toAgent", "phase", "proposal", "utility",
                                                 "routePreview")}
                    entries.append(NegotiationEventLog(
                        session_id=sid,
                        task_id=evt.get("task_id") or evt.get("sessionId"),
                        event_type=evt.get("eventType", ""),
                        phase=evt.get("phase", ""),
                        from_agent=evt.get("fromAgent"),
                        to_agent=evt.get("toAgent"),
                        proposal=json.dumps(evt.get("proposal", {}), ensure_ascii=False),
                        utility=json.dumps(evt.get("utility", {}), ensure_ascii=False),
                        extra=json.dumps(extra_fields, ensure_ascii=False),
                    ))
                db.add_all(entries)
                db.commit()
                success_count = len(entries)
                logger.info(f"[事件持久化] 批量写入成功: {success_count} 条")
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[事件持久化] 批量写入失败（非致命）: {e}")
        return success_count

    async def save_events_batch(self, session_id: str, events: list) -> bool:
        """批量保存事件（兼容旧接口）"""
        if not self._enabled or not events:
            return False
        try:
            from src.database import SessionLocal
            from src.models.db_models import NegotiationEventLog

            db = SessionLocal()
            try:
                entries = []
                for evt in events:
                    entries.append(NegotiationEventLog(
                        session_id=session_id,
                        task_id=evt.get("task_id") or evt.get("sessionId"),
                        event_type=evt.get("eventType", ""),
                        phase=evt.get("phase", ""),
                        from_agent=evt.get("fromAgent"),
                        to_agent=evt.get("toAgent"),
                        proposal=json.dumps(evt.get("proposal", {}), ensure_ascii=False),
                        utility=json.dumps(evt.get("utility", {}), ensure_ascii=False),
                        extra=json.dumps(evt.get("extra", {}), ensure_ascii=False),
                    ))
                db.add_all(entries)
                db.commit()
                return True
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[事件持久化] 批量保存失败: {e}")
            return False

    async def get_events(self, session_id: str) -> list:
        """从数据库获取指定会话的事件列表（按时间排序）"""
        if not self._enabled:
            return []
        try:
            from src.database import SessionLocal
            from src.models.db_models import NegotiationEventLog
            from sqlalchemy import select

            db = SessionLocal()
            try:
                stmt = select(NegotiationEventLog).where(
                    NegotiationEventLog.session_id == session_id
                ).order_by(NegotiationEventLog.created_at)
                rows = db.execute(stmt).scalars().all()
                return [r.to_dict() for r in rows]
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[事件持久化] 读取失败: {e}")
            return []

    async def get_events_by_task(self, task_id: str) -> list:
        """按 task_id 获取事件"""
        if not self._enabled:
            return []
        try:
            from src.database import SessionLocal
            from src.models.db_models import NegotiationEventLog
            from sqlalchemy import select

            db = SessionLocal()
            try:
                stmt = select(NegotiationEventLog).where(
                    NegotiationEventLog.task_id == task_id
                ).order_by(NegotiationEventLog.created_at)
                rows = db.execute(stmt).scalars().all()
                return [r.to_dict() for r in rows]
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[事件持久化] 按task_id读取失败: {e}")
            return []

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def buffer_size(self) -> int:
        return len(self._buffer)


# ==================== 缓冲持久化器（批量写入优化） ====================

class BufferedEventPersister:
    """
    带缓冲的事件持久化器

    将事件先积累到缓冲区，达到 batch_size 或 flush_interval 时再批量写入。
    减少数据库写入压力。
    """

    def __init__(self, persistence: EventPersistenceService,
                 flush_interval: float = 5.0, batch_size: int = 20):
        """
        Args:
            persistence: EventPersistenceService 实例
            flush_interval: 最大缓冲时间（秒）
            batch_size: 触发刷入的批量大小
        """
        self.persistence = persistence
        self.flush_interval = flush_interval
        self.batch_size = batch_size
        self._timer = None
        self._loop = None
        logger.info(f"[缓冲持久化] 初始化: flush_interval={flush_interval}s, batch_size={batch_size}")

    async def add(self, session_id: str, event: dict) -> None:
        """添加事件到缓冲区"""
        self.persistence._buffer.append((session_id, event))
        buffer_size = len(self.persistence._buffer)
        if buffer_size >= self.batch_size:
            await self.flush()
        elif self._timer is None:
            self._loop = asyncio.get_event_loop()
            self._timer = self._loop.call_later(
                self.flush_interval,
                lambda: asyncio.ensure_future(self.flush())
            )

    async def flush(self) -> int:
        """强制刷入缓冲区"""
        if self._timer:
            self._timer.cancel()
            self._timer = None
        return await self.persistence.flush_buffer()

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
        
        # 【新增】缓冲持久化器（可选）
        self._buffered_persister = None
        
        logger.info("[事件总线] 增强版初始化完成")

    # ==================== 持久化控制 ====================

    def enable_persistence(self, batch_mode: bool = False):
        """
        启用数据库持久化

        Args:
            batch_mode: 是否启用批量写入模式
        """
        self._persistence_enabled = True
        self.persistence.enable(batch_mode=batch_mode)
        if batch_mode:
            self._buffered_persister = BufferedEventPersister(self.persistence)
        logger.info(f"[事件总线] 已启用持久化 (batch_mode={batch_mode})")

    def disable_persistence(self):
        """禁用数据库持久化"""
        self._persistence_enabled = False
        self.persistence.disable()
        self._buffered_persister = None
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

    def publish_sync(self, session_id: str, event: Dict[str, Any]):
        """
        同步发布协商事件（用于非异步上下文）

        与 publish() 功能相同，但不使用 await。
        适合在同步测试或非异步环境中使用。

        Args:
            session_id: 任务/会话编号
            event: 事件字典
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
            f"[事件总线] 同步发布事件 [{event.get('eventType')}] "
            f"session={session_id}, {event.get('fromAgent')}->{event.get('toAgent')}"
        )

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
            if self._buffered_persister:
                asyncio.ensure_future(self._buffered_persister.add(session_id, event))
            else:
                asyncio.ensure_future(self.persistence.save_event(session_id, event))

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

    async def get_task_events(self, task_id: str) -> List[Dict[str, Any]]:
        """获取指定任务的所有事件（从数据库）"""
        if self._persistence_enabled:
            return await self.persistence.get_events_by_task(task_id)
        return []

    async def flush_persistence(self) -> int:
        """强制刷入持久化缓冲区（批量模式下使用）"""
        if self._buffered_persister:
            return await self._buffered_persister.flush()
        return 0

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
