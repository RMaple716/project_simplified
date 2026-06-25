"""任务分发相关路由"""
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from src.database import get_db
from src.models.response import success_response, error_response
from src.models.request import TaskDispatchRequest, TaskDispatchResponse, TaskInfo, TaskStatusResponse
from src.services.database_service import TaskService, RequirementService

router = APIRouter(prefix="/api/v1/task", tags=["任务分发"])
requirements_store = {}  # 用于存储需求信息，实际应从数据库获取

# ============== 任务分解核心逻辑 ==============

def calculate_budget_allocation(total_budget: float, travel_days: int, traveler_count: int) -> Dict[str, float]:
    """
    根据总预算自动分摊到各子类预算
    分摊算法：住宿占30%，餐饮25%，交通15%，门票20%，其他10%
    """
    if not total_budget:
        # 如果未指定总预算，按每人每天500元估算
        total_budget = traveler_count * travel_days * 500

    return {
        "accommodation_budget": round(total_budget * 0.30, 2),
        "food_budget": round(total_budget * 0.25, 2),
        "transport_budget": round(total_budget * 0.15, 2),
        "ticket_budget": round(total_budget * 0.20, 2),
        "other_budget": round(total_budget * 0.10, 2)
    }


def decompose_to_subtasks(requirement_id: str, structured_requirement: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    将结构化需求拆分为各智能体的子任务

    Args:
        requirement_id: 需求ID
        structured_requirement: 结构化需求对象

    Returns:
        子任务列表
    """
    # 提取基本信息
    city_name = str(structured_requirement.get("city_name", ""))
    travel_days = int(structured_requirement.get("travel_days", 1) or 1)
    total_budget = float(structured_requirement.get("total_budget", 0) or 0)
    travel_date = str(structured_requirement.get("travel_date", ""))
    traveler_count = int(structured_requirement.get("traveler_count", 1) or 1)
    preferences = list(structured_requirement.get("preferences", []))
    dislikes = list(structured_requirement.get("dislikes", []))

    # 计算预算分配
    budget_allocation = calculate_budget_allocation(total_budget, travel_days, traveler_count)

    # 如果用户指定了具体预算，则使用用户的值
    accommodation_budget = structured_requirement.get("accommodation_budget") or budget_allocation["accommodation_budget"]
    food_budget = structured_requirement.get("food_budget") or budget_allocation["food_budget"]
    transport_budget = structured_requirement.get("transport_budget") or budget_allocation["transport_budget"]
    ticket_budget = structured_requirement.get("ticket_budget") or budget_allocation["ticket_budget"]

    subtasks = []

    # 1. 景点智能体子任务
    attraction_subtask_id = str(uuid.uuid4())
    attraction_params = {
        "city_name": city_name,
        "travel_days": travel_days,
        "preferences": preferences,
        "dislikes": dislikes,
        "ticket_budget": ticket_budget,
        "traveler_count": traveler_count,
        "travel_date": travel_date  # 添加旅行日期，用于获取天气信息
    }
    subtasks.append({
        "subtask_id": attraction_subtask_id,
        "agent_type": "attraction",
        "parameters": attraction_params,
        "status": "pending",
        "result": None
    })

    # 2. 住宿智能体子任务
    accommodation_subtask_id = str(uuid.uuid4())
    # 计算入住和退房日期
    check_in_date = travel_date if travel_date else datetime.now().strftime("%Y-%m-%d")
    check_out_date = (datetime.strptime(check_in_date, "%Y-%m-%d") + timedelta(days=int(travel_days))).strftime("%Y-%m-%d")

    accommodation_params = {
        "city_name": city_name,
        "check_in_date": check_in_date,
        "check_out_date": check_out_date,
        "nights": travel_days,
        "budget_per_night": round(accommodation_budget / travel_days, 2) if travel_days > 0 else accommodation_budget,
        "location_preference": "靠近景点" if preferences else None,
        "traveler_count": traveler_count
    }
    subtasks.append({
        "subtask_id": accommodation_subtask_id,
        "agent_type": "accommodation",
        "parameters": accommodation_params,
        "status": "pending",
        "result": None
    })

    # 3. 美食智能体子任务
    food_subtask_id = str(uuid.uuid4())
    food_params = {
        "city_name": city_name,
        "travel_days": travel_days,
        "preferences": preferences,
        "budget_per_person": round(food_budget / (travel_days * traveler_count), 2) if travel_days > 0 and traveler_count > 0 else food_budget,
        "traveler_count": traveler_count
    }
    subtasks.append({
        "subtask_id": food_subtask_id,
        "agent_type": "food",
        "parameters": food_params,
        "status": "pending",
        "result": None
    })

    # 4. 交通智能体子任务
    transport_subtask_id = str(uuid.uuid4())
    transport_params = {
        "city_name": city_name,
        "travel_days": travel_days,
        "budget": transport_budget,
        "mode_preference": "transit",
        "from_location": {"name": f""},
        "to_location": {"name": f""}
    }
    subtasks.append({
        "subtask_id": transport_subtask_id,
        "agent_type": "transport",
        "parameters": transport_params,
        "status": "pending",
        "result": None
    })

    return subtasks


# ============== API 路由 ==============

@router.post("/decompose")
async def decompose_task(request_data: Dict[str, Any], background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    任务分解接口：将结构化需求拆分为各智能体的子任务

    请求参数:
    {
        "requirement_id": "req_xxx",
        "structured_requirement": { ... }
    }
    """
    requirement_id = request_data.get("requirement_id")
    structured_requirement = request_data.get("structured_requirement")

    if not requirement_id or not structured_requirement:
        return error_response(code=400, msg="缺少必要参数：requirement_id 或 structured_requirement")

    print(f"[DECOMPOSE DEBUG] 收到 structured_requirement: travel_days={structured_requirement.get('travel_days')} (type={type(structured_requirement.get('travel_days')).__name__}), city_name={structured_requirement.get('city_name')}, budget={structured_requirement.get('total_budget')}, date={structured_requirement.get('travel_date')}")
    print(f"[DECOMPOSE DEBUG] 完整 structured_requirement: {json.dumps(structured_requirement, ensure_ascii=False, default=str)}")

    # 验证需求是否存在
    requirement = RequirementService.get_requirement(db, requirement_id)
    if not requirement:
        return error_response(code=404, msg="需求不存在")

    # 验证必填字段
    required_fields = ["city_name", "travel_days", "total_budget", "travel_date", "traveler_count"]
    for field in required_fields:
        if field not in structured_requirement:
            return error_response(code=400, msg=f"缺少必填字段：{field}")

    # 执行业务规则验证
    travel_days = int(structured_requirement.get("travel_days", 0) or 0)
    traveler_count = int(structured_requirement.get("traveler_count", 0) or 0)
    total_budget = float(structured_requirement.get("total_budget", 0) or 0)

    if travel_days < 1 or travel_days > 30:
        return error_response(code=400001, msg="出行天数必须在1-30天之间")

    if traveler_count < 1 or traveler_count > 20:
        return error_response(code=400, msg="出行人数必须在1-20人之间")

    min_budget = traveler_count * 100
    if total_budget < min_budget:
        return error_response(code=400002, msg=f"预算过低，至少需要每人每天100元（最低{min_budget}元）")

    # 执行任务分解
    subtasks = decompose_to_subtasks(requirement_id, structured_requirement)

    # 保存需求信息到requirements_store
    real_user_id = requirement.user_id if requirement else "anonymous"
    requirements_store[requirement_id] = {
        "user_id": real_user_id,
        "city_name": structured_requirement.get("city_name", ""),
        "travel_days": int(structured_requirement.get("travel_days", 1) or 1),
        "total_budget": float(structured_requirement.get("total_budget", 0) or 0),
        "travel_date": structured_requirement.get("travel_date", ""),
        "traveler_count": int(structured_requirement.get("traveler_count", 1) or 1),
        "preferences": structured_requirement.get("preferences", []),
    }

    # 生成任务批次ID
    batch_id = str(uuid.uuid4())

    # 批量创建子任务到数据库
    tasks = TaskService.create_batch_tasks(
        db=db,
        batch_id=batch_id,
        requirement_id=requirement_id,
        subtasks=subtasks
    )

    # 构建响应数据
    tasks_info = [TaskInfo(
        task_id=str(task.task_id),
        agent=str(task.agent_type),
        status=str(task.status),
        result=None
    ) for task in tasks]

        # 使用后台任务在独立线程中执行子任务
    from src.database import SessionLocal

    def execute_subtasks_with_db():
        """在线程中创建新事件循环并执行所有子任务"""
        async_db = SessionLocal()
        try:
            import asyncio
            from src.agents import AttractionsAgent, HotelAgent, FoodAgent, TransportAgent

            from src.services.negotiation_event_bus import event_bus, create_negotiation_event, NegotiationEventType, NegotiationPhase

            async def execute_subtasks(db_session: Session):
                """异步执行所有子任务，通过 event_bus 实时推送进度"""
                # ===== 推送任务开始事件 =====
                await event_bus.publish(batch_id, {
                    "eventId": str(uuid.uuid4()),
                    "sessionId": batch_id,
                    "timestamp": int(datetime.now().timestamp() * 1000),
                    "eventType": "TASK_STARTED",
                    "fromAgent": "dispatcher",
                    "toAgent": "frontend",
                    "phase": "EXECUTING",
                    "proposal": {"totalSubTasks": len(subtasks)},
                    "utility": {},
                    "routePreview": {},
                    "subtaskCount": len(subtasks),
                    "agentTypes": [s["agent_type"] for s in subtasks],
                    "cityName": requirements_store.get(requirement_id, {}).get("city_name", ""),
                    "travelDays": requirements_store.get(requirement_id, {}).get("travel_days", 1),
                    "message": f"开始规划行程：共 {len(subtasks)} 个子任务"
                })
                print(f"[任务执行] 开始执行批次任务 {batch_id}")

                try:
                    # 初始化智能体
                    attractions_agent = AttractionsAgent()
                    hotel_agent = HotelAgent()
                    food_agent = FoodAgent()
                    transport_agent = TransportAgent()
                    print(f"[任务执行] 智能体初始化完成")

                    # 执行每个子任务
                    for i, subtask in enumerate(subtasks):
                        task_id_local = subtask["subtask_id"]
                        agent_type = subtask["agent_type"]
                        parameters = subtask["parameters"]

                        agent_label = {
                            "attraction": "景点推荐",
                            "accommodation": "住宿推荐",
                            "food": "美食推荐",
                            "transport": "交通规划"
                        }.get(agent_type, agent_type)

                        print(f"[任务执行] 开始执行子任务 {task_id_local} ({agent_type})")

                        # ===== 推送子任务开始事件 =====
                        await event_bus.publish(batch_id, {
                            "eventId": str(uuid.uuid4()),
                            "sessionId": batch_id,
                            "timestamp": int(datetime.now().timestamp() * 1000),
                            "eventType": "SUB_TASK_STARTED",
                            "fromAgent": "dispatcher",
                            "toAgent": f"{agent_type}_agent",
                            "phase": "EXECUTING",
                            "proposal": {"index": i + 1, "total": len(subtasks)},
                            "utility": {},
                            "routePreview": {},
                            "subtaskIndex": i + 1,
                            "subtaskTotal": len(subtasks),
                            "agentType": agent_type,
                            "agentLabel": agent_label,
                            "message": f"[{i + 1}/{len(subtasks)}] {agent_label}智能体正在执行..."
                        })

                        try:
                            # 根据智能体类型执行相应的任务
                            if agent_type == "attraction":
                                result = await attractions_agent.execute({
                                    "task_id": task_id_local,
                                    **parameters
                                })
                            elif agent_type == "accommodation":
                                result = await hotel_agent.execute({
                                    "task_id": task_id_local,
                                    **parameters
                                })
                            elif agent_type == "food":
                                result = await food_agent.execute({
                                    "task_id": task_id_local,
                                    **parameters
                                })
                            elif agent_type == "transport":
                                # 确保from_location和to_location有name字段
                                from_name = parameters.get("from_location", {}).get("name", f"{parameters.get('city_name', '')}市中心")
                                to_name = parameters.get("to_location", {}).get("name", f"{parameters.get('city_name', '')}机场")
                                
                                transport_params = parameters.copy()
                                transport_params["from_location"] = parameters.get("from_location", {"name": from_name})
                                transport_params["to_location"] = parameters.get("to_location", {"name": to_name})
                                
                                result = await transport_agent.execute({
                                    "task_id": task_id_local,
                                    **transport_params
                                })
                            else:
                                result = {"status": "failed", "error_message": f"未知的智能体类型: {agent_type}"}

                            # 检查result是否为字典类型
                            if not isinstance(result, dict):
                                print(f"[任务执行] 子任务 {task_id_local} 返回结果类型异常: {type(result)}")
                                TaskService.update_task_result(
                                    db=db_session,
                                    task_id=task_id_local,
                                    status="failed",
                                    result={},
                                    error=f"智能体返回结果类型错误: 期望dict, 实际为{type(result).__name__}"
                                )
                                # 推送子任务失败事件
                                await event_bus.publish(batch_id, {
                                    "eventId": str(uuid.uuid4()),
                                    "sessionId": batch_id,
                                    "timestamp": int(datetime.now().timestamp() * 1000),
                                    "eventType": "SUB_TASK_FAILED",
                                    "fromAgent": f"{agent_type}_agent",
                                    "toAgent": "dispatcher",
                                    "phase": "EXECUTING",
                                    "proposal": {},
                                    "utility": {},
                                    "routePreview": {},
                                    "agentType": agent_type,
                                    "agentLabel": agent_label,
                                    "error": f"返回结果类型错误: {type(result).__name__}",
                                    "message": f"❌ {agent_label}智能体执行异常"
                                })
                                continue

                            status = result.get("status", "failed")
                            print(f"[任务执行] 子任务 {task_id_local} 执行结果: {status}")

                            # 更新数据库中的任务状态
                            if status == "success":
                                data = result.get("data", {})
                                if not isinstance(data, dict):
                                    data = {}
                                items = data.get("items", [])

                                task_result = {}
                                item_count = len(items)
                                if agent_type == "attraction":
                                    task_result = {"attractions": items}
                                elif agent_type == "food":
                                    task_result = {"restaurants": items}
                                elif agent_type == "accommodation":
                                    task_result = {"hotels": items}
                                elif agent_type == "transport":
                                    items = data.get("items", [])
                                    item_count = len(items)
                                    task_result = {"transport_options": items, "route_data": data.get("route_data", {})}
                                else:
                                    task_result = data if isinstance(data, dict) else {"data": data}
                                    item_count = 0

                                TaskService.update_task_result(
                                    db=db_session,
                                    task_id=task_id_local,
                                    status="success",
                                    result=task_result,
                                    error=""
                                )

                                # 推送子任务完成事件
                                await event_bus.publish(batch_id, {
                                    "eventId": str(uuid.uuid4()),
                                    "sessionId": batch_id,
                                    "timestamp": int(datetime.now().timestamp() * 1000),
                                    "eventType": "SUB_TASK_COMPLETED",
                                    "fromAgent": f"{agent_type}_agent",
                                    "toAgent": "dispatcher",
                                    "phase": "EXECUTING",
                                    "proposal": {"itemCount": item_count},
                                    "utility": {},
                                    "routePreview": {},
                                    "agentType": agent_type,
                                    "agentLabel": agent_label,
                                    "itemCount": item_count,
                                    "message": f"✅ {agent_label}智能体完成，找到 {item_count} 个推荐项"
                                })
                            else:
                                error_msg = result.get("error_message", "执行失败")
                                print(f"[任务执行] 子任务 {task_id_local} 错误信息: {error_msg}")
                                print(f"[任务执行] 子任务 {task_id_local} 完整返回结果: {result}")
                                TaskService.update_task_result(
                                    db=db_session,
                                    task_id=task_id_local,
                                    status="failed",
                                    result={},
                                    error=error_msg
                                )
                                # 推送子任务失败事件
                                await event_bus.publish(batch_id, {
                                    "eventId": str(uuid.uuid4()),
                                    "sessionId": batch_id,
                                    "timestamp": int(datetime.now().timestamp() * 1000),
                                    "eventType": "SUB_TASK_FAILED",
                                    "fromAgent": f"{agent_type}_agent",
                                    "toAgent": "dispatcher",
                                    "phase": "EXECUTING",
                                    "proposal": {},
                                    "utility": {},
                                    "routePreview": {},
                                    "agentType": agent_type,
                                    "agentLabel": agent_label,
                                    "error": error_msg,
                                    "message": f"❌ {agent_label}智能体执行失败: {error_msg}"
                                })

                        except Exception as e:
                            import traceback
                            print(f"[任务执行] 子任务 {task_id_local} 执行失败: {e}")
                            traceback.print_exc()
                            TaskService.update_task_result(
                                db=db_session,
                                task_id=task_id_local,
                                status="failed",
                                result={},
                                error=str(e)
                            )
                            # 推送子任务异常事件
                            await event_bus.publish(batch_id, {
                                "eventId": str(uuid.uuid4()),
                                "sessionId": batch_id,
                                "timestamp": int(datetime.now().timestamp() * 1000),
                                "eventType": "SUB_TASK_FAILED",
                                "fromAgent": f"{agent_type}_agent",
                                "toAgent": "dispatcher",
                                "phase": "EXECUTING",
                                "proposal": {},
                                "utility": {},
                                "routePreview": {},
                                "agentType": agent_type,
                                "agentLabel": agent_label,
                                "error": str(e),
                                "message": f"❌ {agent_label}智能体异常: {str(e)[:100]}"
                            })

                    # 所有子任务完成，检查是否需要创建行程
                    tasks = TaskService.get_batch_tasks(db_session, batch_id)
                    completed_count = sum(1 for task in tasks if str(task.status) == "success")
                    failed_count = sum(1 for task in tasks if str(task.status) == "failed")

                    print(f"[任务执行] 批次任务 {batch_id} 完成: 成功 {completed_count}, 失败 {failed_count}")

                    # 如果所有子任务完成（无论成败），尝试创建行程
                    # 但只有全部成功才推送协商开始事件
                    if failed_count == 0:
                        # 推送协商开始事件
                        await event_bus.publish(batch_id, {
                            "eventId": str(uuid.uuid4()),
                            "sessionId": batch_id,
                            "timestamp": int(datetime.now().timestamp() * 1000),
                            "eventType": "NEGOTIATION_STARTED",
                            "fromAgent": "dispatcher",
                            "toAgent": "frontend",
                            "phase": "NEGOTIATE",
                            "proposal": {},
                            "utility": {},
                            "routePreview": {},
                            "message": "🔄 所有子任务完成，开始协商优化行程..."
                        })

                        try:
                            from src.services.database_service import ItineraryService
                            from src.routes.integration import integrate_agent_results_to_daily_plans

                            # 收集所有子任务的结果
                            attractions_result = None
                            hotel_result = None
                            food_result = None
                            transport_result = None

                            for task in tasks:
                                if str(task.agent_type) == "attraction" and task.result is not None:
                                    attractions_result = task.result
                                elif str(task.agent_type) == "accommodation" and task.result is not None:
                                    hotel_result = task.result
                                elif str(task.agent_type) == "food" and task.result is not None:
                                    food_result = task.result
                                elif str(task.agent_type) == "transport" and task.result is not None:
                                    transport_result = task.result

                            requirement_data = requirements_store.get(requirement_id, {})
                            city_name = str(requirement_data.get("city_name", ""))
                            travel_days = int(requirement_data.get("travel_days", 1) or 1)
                            total_budget = float(requirement_data.get("total_budget", 0) or 0)
                            travel_date = str(requirement_data.get("travel_date", ""))
                            traveler_count = int(requirement_data.get("traveler_count", 1) or 1)
                            preferences = requirement_data.get("preferences", [])

                            def safe_get(data, key, default=None):
                                if isinstance(data, dict):
                                    return data.get(key, default or ([] if isinstance(default, list) else {}))
                                return default or ([] if isinstance(default, list) else {})

                            attractions_data = safe_get(attractions_result, "attractions", [])
                            hotels_data = safe_get(hotel_result, "hotels", [])
                            restaurants_data = safe_get(food_result, "restaurants", [])
                            transport_options = safe_get(transport_result, "transport_options", [])
                            attractions_data = [a for a in attractions_data if isinstance(a, dict)]
                            hotels_data = [h for h in hotels_data if isinstance(h, dict)]
                            restaurants_data = [r for r in restaurants_data if isinstance(r, dict)]
                            transport_options = [t for t in transport_options if isinstance(t, dict)]

                            agent_results = {
                                "attraction": {"attractions": attractions_data},
                                "accommodation": {"hotels": hotels_data},
                                "food": {"restaurants": restaurants_data},
                                "transport": {"transport_options": transport_options}
                            }

                            print(f"[TASK DEBUG] 创建行程: travel_days={travel_days}, city_name={city_name}, requirement_data={requirement_data}")
                            structured_req = {
                                "city_name": city_name,
                                "travel_days": travel_days,
                                "total_budget": total_budget,
                                "travel_date": travel_date,
                                "traveler_count": traveler_count,
                                "preferences": preferences
                            }

                            day_plans = integrate_agent_results_to_daily_plans(agent_results, structured_req)

                            # ===== 协商修复 + 路线优化 =====
                            negotiation_events_to_save = []
                            try:
                                from src.services.negotiation_service import negotiate_and_fix
                                backup_data = {"attractions": attractions_data}
                                structured_req_with_task = dict(structured_req)
                                structured_req_with_task["task_id"] = batch_id
                                negotiated = await negotiate_and_fix(
                                    day_plans=day_plans,
                                    structured_requirement=structured_req_with_task,
                                    backup_data=backup_data,
                                    max_iterations=5,
                                    optimize_route=True,
                                    use_real_traffic=True
                                )
                                if negotiated["fully_resolved"]:
                                    print(f"[任务执行] ✓ 协商修复成功，{negotiated['iteration_count']}轮完成")
                                else:
                                    print(f"[任务执行] ⚠ 协商修复完成，仍有未解决冲突")
                                day_plans = negotiated["day_plans"]
                                negotiation_events_to_save = negotiated.get("negotiation_events", [])
                            except Exception as e:
                                import traceback
                                print(f"[任务执行] 协商修复异常: {e}")
                                traceback.print_exc()

                            # 持久化协商事件
                            if negotiation_events_to_save and len(day_plans) > 0:
                                if isinstance(day_plans[0], dict):
                                    if "negotiation" not in day_plans[0]:
                                        day_plans[0]["negotiation"] = {}
                                    day_plans[0]["negotiation"]["events"] = negotiation_events_to_save
                                    print(f"[任务执行] 已持久化 {len(negotiation_events_to_save)} 个协商事件到行程数据")

                            # 创建行程
                            itinerary = ItineraryService.create_itinerary(
                                db=db_session,
                                user_id=str(requirement_data.get("user_id", "anonymous")),
                                day_plans=day_plans,
                                title=f"{city_name} {travel_days}日游",
                                total_budget=total_budget,
                                requirement_id=requirement_id
                            )

                            print(f"[任务执行] 行程创建成功: {itinerary.itinerary_id}")

                            # 推送行程创建完成事件
                            await event_bus.publish(batch_id, {
                                "eventId": str(uuid.uuid4()),
                                "sessionId": batch_id,
                                "timestamp": int(datetime.now().timestamp() * 1000),
                                "eventType": "ITINERARY_CREATED",
                                "fromAgent": "dispatcher",
                                "toAgent": "frontend",
                                "phase": "FINALIZED",
                                "proposal": {"itineraryId": itinerary.itinerary_id},
                                "utility": {},
                                "routePreview": {},
                                "itineraryId": itinerary.itinerary_id,
                                "message": f"🎉 行程生成成功！共 {travel_days} 天行程"
                            })

                        except Exception as e:
                            print(f"[任务执行] 创建行程失败: {e}")
                            import traceback
                            traceback.print_exc()

                except Exception as e:
                    print(f"[任务执行] 执行子任务时出错: {e}")
                    import traceback
                    traceback.print_exc()

            # 在新的事件循环中运行（独立线程，不会与主循环冲突）
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            new_loop.run_until_complete(execute_subtasks(async_db))
            new_loop.close()
        finally:
            async_db.close()

    # 添加到后台任务队列
    background_tasks.add_task(execute_subtasks_with_db)

    return success_response(
        data={
            "task_id": batch_id,
            "batch_id": batch_id,
            "requirement_id": requirement_id,
            "subtasks": [t.model_dump() for t in tasks_info]
        },
        msg="任务分解成功"
    )


@router.post("/dispatch")
async def dispatch_tasks(request: TaskDispatchRequest, db: Session = Depends(get_db)):
    """
    旧版任务分发接口（保留兼容）
    """
    batch_id = str(uuid.uuid4())
    subtasks = []

    for agent in request.agents:
        subtasks.append({
            "agent_type": agent,
            "parameters": {}
        })

    tasks = TaskService.create_batch_tasks(
        db=db,
        batch_id=batch_id,
        requirement_id=request.requirement_id,
        subtasks=subtasks
    )

    tasks_info = [TaskInfo(
        task_id=str(task.task_id),
        agent=str(task.agent_type),
        status=str(task.status),
        result=None
    ) for task in tasks]

    return success_response(
        data=TaskDispatchResponse(
            batch_id=batch_id,
            tasks=tasks_info
        ).model_dump(),
        msg="任务分发成功"
    )


@router.get("/{task_id}")
async def get_task_status(task_id: str, db: Session = Depends(get_db)):
    """
    获取任务状态 - 从数据库查询
    """
    # 先尝试作为批次ID查询
    progress_info = TaskService.calculate_batch_progress(db, task_id)

    if progress_info["total"] > 0:
        # 是批次ID，返回总体进度
        # 查询是否有关联的行程
        from src.models.db_models import Itinerary
        itinerary = None
        # 尝试通过requirement_id查找行程
        batch_tasks = TaskService.get_batch_tasks(db, task_id)
        if batch_tasks:
            requirement_id = batch_tasks[0].requirement_id
            itinerary = db.query(Itinerary).filter(Itinerary.requirement_id == requirement_id).first()

        # 从 event_bus 获取协商事件
        negotiation_events = []
        try:
            from src.services.negotiation_event_bus import event_bus
            negotiation_events = event_bus.get_session_log(task_id) or []
        except Exception:
            pass

        return success_response(data={
            "task_id": task_id,
            "status": progress_info["status"],
            "progress": progress_info["progress"],
            "completed": progress_info["completed"],
            "failed": progress_info["failed"],
            "total": progress_info["total"],
            "message": f"已完成 {progress_info['completed']}/{progress_info['total']} 个子任务",
            "itinerary_id": itinerary.itinerary_id if itinerary else None,
            "negotiation_events": negotiation_events,
        }, msg="获取成功")

    # 尝试作为单个任务ID查询
    task = TaskService.get_task(db, task_id)

    if not task:
        return error_response(code=404, msg="任务不存在")

    # 查找关联的行程
    from src.models.db_models import Itinerary
    itinerary = db.query(Itinerary).filter(Itinerary.requirement_id == task.requirement_id).first()

    response_data = TaskStatusResponse(
        task_id=str(task.task_id),
        agent=str(task.agent_type),
        status=str(task.status),
        result=task.result if isinstance(task.result, dict) else None,
        error=str(task.error) if task.error is not None else None
    ).model_dump()

    # 添加行程ID
    if itinerary:
        response_data["itinerary_id"] = itinerary.itinerary_id

    return success_response(data=response_data, msg="获取成功")


@router.post("/update/{task_id}")
async def update_task_result(task_id: str, result_data: Dict[str, Any], db: Session = Depends(get_db)):
    """
    更新任务结果（供智能体调用）- 保存到数据库

    请求参数:
    {
        "status": "success" | "failed",
        "result": { ... },  // 智能体返回的结果
        "error": null | "错误信息"
    }
    """
    # 获取result参数，确保是字典类型
    result_value = result_data.get("result")
    if not isinstance(result_value, dict):
        result_value = {}

    # 获取error参数，确保是字符串类型
    error_value = result_data.get("error")
    if error_value is None:
        error_value = ""
    else:
        error_value = str(error_value)

    task = TaskService.update_task_result(
        db=db,
        task_id=task_id,
        status=result_data.get("status", "success"),
        result=result_value,
        error=error_value
    )

    if not task:
        return error_response(code=404, msg="任务不存在")

    return success_response(
        data={"task_id": task_id, "status": task.status},
        msg="任务结果更新成功"
    )
