"""智能体相关路由"""
from fastapi import APIRouter
from src.models.response import success_response
from src.models.request import (
    AttractionsAgentRequest, AttractionsAgentResponse,
    TransportAgentRequest, TransportAgentResponse,
    HotelAgentRequest, HotelAgentResponse,
    FoodAgentRequest, FoodAgentResponse
)
from src.agents import (
    AttractionsAgent,
    TransportAgent,
    HotelAgent,
    FoodAgent
)

router = APIRouter(prefix="/api/v1/agent", tags=["智能体"])

# 初始化智能体
attractions_agent = AttractionsAgent()
transport_agent = TransportAgent()
hotel_agent = HotelAgent()
food_agent = FoodAgent()

@router.post("/attractions")
async def attractions_agent_endpoint(request: AttractionsAgentRequest):
    """景点推荐智能体"""
    import uuid
    task_data = request.model_dump()
    task_data["task_id"] = f"attr_{uuid.uuid4().hex[:8]}"

    result = await attractions_agent.execute(task_data)
    if result["status"] == "success":
        return success_response(
            data=AttractionsAgentResponse(attractions=result["data"]["items"]).model_dump(),
            msg="景点推荐成功"
        )
    else:
        return success_response(
            data=AttractionsAgentResponse(attractions=[]).model_dump(),
            msg=f"景点推荐失败: {result.get('error_message', '未知错误')}"
        )

@router.post("/transport")
async def transport_agent_endpoint(request: TransportAgentRequest):
    """交通推荐智能体"""
    import uuid
    task_data = request.model_dump()
    task_data["task_id"] = f"trans_{uuid.uuid4().hex[:8]}"

    result = await transport_agent.execute(task_data)
    if result["status"] == "success":
        return success_response(
            data=TransportAgentResponse(transport_options=result["data"]["items"]).model_dump(),
            msg="交通推荐成功"
        )
    else:
        return success_response(
            data=TransportAgentResponse(transport_options=[]).model_dump(),
            msg=f"交通推荐失败: {result.get('error_message', '未知错误')}"
        )

@router.post("/hotel")
async def hotel_agent_endpoint(request: HotelAgentRequest):
    """住宿推荐智能体"""
    import uuid
    task_data = request.model_dump()
    task_data["task_id"] = f"hotel_{uuid.uuid4().hex[:8]}"

    result = await hotel_agent.execute(task_data)
    if result["status"] == "success":
        return success_response(
            data=HotelAgentResponse(hotels=result["data"]["items"]).model_dump(),
            msg="住宿推荐成功"
        )
    else:
        return success_response(
            data=HotelAgentResponse(hotels=[]).model_dump(),
            msg=f"住宿推荐失败: {result.get('error_message', '未知错误')}"
        )

@router.post("/food")
async def food_agent_endpoint(request: FoodAgentRequest):
    """美食推荐智能体"""
    import uuid
    task_data = request.model_dump()
    task_data["task_id"] = f"food_{uuid.uuid4().hex[:8]}"

    result = await food_agent.execute(task_data)
    if result["status"] == "success":
        return success_response(
            data=FoodAgentResponse(restaurants=result["data"]["items"]).model_dump(),
            msg="美食推荐成功"
        )
    else:
        return success_response(
            data=FoodAgentResponse(restaurants=[]).model_dump(),
            msg=f"美食推荐失败: {result.get('error_message', '未知错误')}"
        )