"""
WebSocket 路由 - 协商事件实时推送

功能:
1. 为前端提供协商事件的实时 WebSocket 推送
2. 支持按 sessionId 订阅事件流
3. 支持 Agent间消息的实时转发

使用方式（前端）:
    const ws = new WebSocket(`ws://localhost:9092/api/v1/ws/negotiation?session_id=task_001`);
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        // data.eventType: CFP | PROPOSE | COUNTER | ACCEPT | REJECT | FINALIZED | AGENT_MSG
        // data.fromAgent, data.toAgent, data.proposal, ...
    };

依赖:
    - FastAPI WebSocket
    - src.services.negotiation_event_bus (event_bus, ws_manager)
"""
import json
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from src.services.negotiation_event_bus import event_bus, ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ws", tags=["WebSocket"])


@router.websocket("/negotiation")
async def negotiation_websocket(
    websocket: WebSocket,
    session_id: Optional[str] = Query(None, description="会话ID，不指定则接收所有事件"),
):
    """
    WebSocket 端点 - 协商事件实时推送

    连接方式:
        ws://host:port/api/v1/ws/negotiation?session_id=task_001

    参数:
        session_id: 可选，指定要监听的会话ID。如果不指定，则接收所有会话的事件。

    推送事件格式:
        {
            "eventId": "uuid",
            "sessionId": "task_001",
            "timestamp": 1712345678000,
            "eventType": "PROPOSE",
            "fromAgent": "attractions_agent",
            "toAgent": "dispatcher",
            "phase": "NEGOTIATE",
            "proposal": {...},
            "utility": {...},
            "routePreview": {...}
        }

    Agent间消息格式:
        {
            "eventType": "AGENT_MSG",
            "fromAgent": "attractions_agent",
            "toAgent": "food_agent",
            "type": "coordinate_request",
            "payload": {...}
        }
    """
    await websocket.accept()
    logger.info(f"[WebSocket] 新连接: session_id={session_id}")

    # 注册 WebSocket 连接
    if session_id:
        ws_manager.register_connection(session_id, websocket)
    else:
        # 没有 session_id 时，注册到全局监听
        ws_manager.register_connection("__global__", websocket)

    # 注册一个全局回调，用于推送到此 WebSocket
    async def push_to_ws(event: dict):
        try:
            # 如果指定了 session_id，只推送该 session 的事件
            if session_id and event.get("sessionId") != session_id:
                return
            await websocket.send_json(event)
        except Exception:
            pass

    ws_manager.register_global_callback(push_to_ws)

    try:
        while True:
            # 接收前端消息（例如：协商确认、手动调整指令等）
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type", "")

                if msg_type == "ping":
                    # 心跳响应
                    await websocket.send_json({"type": "pong"})

                elif msg_type == "subscribe":
                    # 动态订阅某个 session
                    new_session_id = message.get("session_id")
                    if new_session_id:
                        if session_id:
                            ws_manager.unregister_connection(session_id, websocket)
                        ws_manager.register_connection(new_session_id, websocket)
                        session_id = new_session_id
                        await websocket.send_json({
                            "type": "subscribed",
                            "session_id": session_id
                        })

                elif msg_type == "agent_reply":
                    # 【新增】前端模拟Agent回复（测试/调试用）
                    # 实际生产环境中，此消息应由Agent自身发出
                    from_agent = message.get("from_agent", "")
                    to_agent = message.get("to_agent", "")
                    reply_payload = message.get("payload", {})
                    reply_type = message.get("msg_type", "coordinate_response")

                    if from_agent and to_agent:
                        from src.services.negotiation_event_bus import (
                            create_agent_message,
                            agent_message_bus,
                            create_negotiation_event,
                            NegotiationEventType,
                            NegotiationPhase,
                        )
                        # 同时发布为协商事件和 Agent 消息
                        agent_msg = create_agent_message(
                            from_agent=from_agent,
                            to_agent=to_agent,
                            msg_type=reply_type,
                            payload=reply_payload,
                            session_id=session_id or "default",
                        )
                        await event_bus.publish(
                            session_id or "default",
                            create_negotiation_event(
                                event_type=NegotiationEventType.AGENT_MSG,
                                session_id=session_id or "default",
                                from_agent=from_agent,
                                to_agent=to_agent,
                                phase=NegotiationPhase.NEGOTIATE,
                                proposal=reply_payload,
                                extra={"agentMsgType": reply_type},
                            )
                        )

                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"未知消息类型: {msg_type}"
                    })

            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "消息格式错误，需要JSON"
                })

    except WebSocketDisconnect:
        logger.info(f"[WebSocket] 断开连接: session_id={session_id}")
    except Exception as e:
        logger.warning(f"[WebSocket] 异常: {e}")
    finally:
        # 清理连接
        if session_id:
            ws_manager.unregister_connection(session_id, websocket)
        else:
            ws_manager.unregister_connection("__global__", websocket)
        # 清理全局回调查
        ws_manager._global_callbacks.remove(push_to_ws)


@router.websocket("/agent/{agent_id}")
async def agent_websocket(websocket: WebSocket, agent_id: str):
    """
    WebSocket 端点 - Agent间通信（供Agent使用）

    允许Agent通过WebSocket实时接收和发送消息。
    每个Agent连接后可以接收发给自己的消息，也可以发送消息给其他Agent。

    连接方式:
        ws://host:port/api/v1/ws/agent/attractions_agent
    """
    await websocket.accept()
    logger.info(f"[Agent WS] {agent_id} 已连接")

    from src.services.negotiation_event_bus import agent_message_bus, event_bus

    # 为这个Agent注册消息处理器
    async def agent_message_handler(message: dict) -> Optional[dict]:
        """当有其他Agent发消息给此Agent时，通过WebSocket转发"""
        try:
            await websocket.send_json({
                "type": "agent_message",
                "message": message
            })
            # 等待Agent的响应（超时30秒）
            try:
                response = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )
                response_data = json.loads(response)
                if response_data.get("type") == "agent_reply":
                    return response_data.get("payload", {})
            except asyncio.TimeoutError:
                logger.warning(f"[Agent WS] {agent_id} 响应超时")
            except json.JSONDecodeError:
                pass
        except Exception as e:
            logger.warning(f"[Agent WS] {agent_id} 处理消息失败: {e}")
        return None

    import asyncio
    agent_message_bus.register_handler(agent_id, agent_message_handler)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type", "")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

                elif msg_type == "send":
                    # Agent主动发送消息给另一个Agent
                    to_agent = message.get("to_agent", "")
                    msg_content = message.get("message", {})
                    session_id = message.get("session_id", "default")

                    if to_agent:
                        response = await agent_message_bus.send(
                            from_agent=agent_id,
                            to_agent=to_agent,
                            message=msg_content,
                            session_id=session_id,
                        )
                        await websocket.send_json({
                            "type": "send_result",
                            "to_agent": to_agent,
                            "response": response
                        })

                elif msg_type == "broadcast":
                    # Agent广播消息给所有其他Agent
                    msg_content = message.get("message", {})
                    session_id = message.get("session_id", "default")
                    responses = await agent_message_bus.broadcast(
                        from_agent=agent_id,
                        message=msg_content,
                        session_id=session_id,
                    )
                    await websocket.send_json({
                        "type": "broadcast_result",
                        "responses": responses
                    })

            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "消息格式错误"})

    except WebSocketDisconnect:
        logger.info(f"[Agent WS] {agent_id} 断开连接")
    except Exception as e:
        logger.warning(f"[Agent WS] {agent_id} 异常: {e}")
    finally:
        agent_message_bus.unregister_handler(agent_id, agent_message_handler)
