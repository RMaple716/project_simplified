"""
自然语言处理相关路由
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from src.models.response import success_response, error_response
from src.services.travel_extractor import TravelExtractor
from src.services.nlp_agent_service import nlp_agent_service  # 新增：导入智能提取服务

router = APIRouter(prefix="/api/v1/nlp", tags=["自然语言处理"])

class NLPRequest(BaseModel):
    text: str
    cities: Optional[list] = None
    attractions: Optional[list] = None

class NLPResponse(BaseModel):
    city: Optional[str]
    attraction: Optional[str]
    budget: Optional[int]
    transport: Optional[str]
    depart_time: Optional[str]
    people: Optional[int]
    travel_days: Optional[int]  # ✅ 新增出行天数字段

class NLPAgentRequest(BaseModel):
    """智能提取请求"""
    text: str

class NLPAgentResponse(BaseModel):
    """智能提取响应"""
    city: Optional[str] = None
    attraction: Optional[str] = None
    budget: Optional[int] = None
    transport: Optional[str] = None
    depart_time: Optional[str] = None
    people: Optional[int] = None
    travel_days: Optional[int] = None
    preferences: Optional[list] = []
    travel_type: Optional[str] = None


@router.post("/extract", response_model=dict)
async def extract_travel_info(request: NLPRequest):
    """
    从自然语言中提取旅游需求信息（传统正则方式）

    参数:
    - text: 用户输入的自然语言描述
    - cities: 可选的城市白名单
    - attractions: 可选的景点白名单

    返回:
    - city: 目的地城市
    - attraction: 景点
    - budget: 预算
    - transport: 交通方式
    - depart_time: 出发时间
    - people: 人数
    """
    try:
        # 初始化提取器
        extractor = TravelExtractor(
            cities=request.cities,
            attractions=request.attractions
        )

        # 提取信息
        result = extractor.extract(request.text)

        return success_response(
            data=result,
            msg="提取成功"
        )
    except Exception as e:
        return error_response(
            code=500,
            msg=f"提取失败: {str(e)}"
        )


@router.post("/extract-agent", response_model=dict)
async def extract_travel_info_by_agent(request: NLPAgentRequest):
    """
    使用AI智能体从自然语言中提取旅游需求信息（大模型方式）

    相比传统正则提取，智能体方式能更好地理解复杂、模糊的自然语言表达，
    提取更准确的字段信息。

    参数:
    - text: 用户输入的自然语言描述

    返回:
    - city: 目的地城市
    - attraction: 景点
    - budget: 预算（数字）
    - transport: 交通方式
    - depart_time: 出发时间
    - people: 人数
    - travel_days: 出行天数
    - preferences: 偏好列表
    - travel_type: 出行类型
    """
    try:
        if not request.text or not request.text.strip():
            return error_response(code=400, msg="请输入旅游需求描述")

        result = await nlp_agent_service.extract_travel_info(request.text)

        return success_response(
            data=result,
            msg="智能提取成功"
        )
    except ValueError as e:
        return error_response(code=422, msg=str(e))
    except Exception as e:
        return error_response(
            code=500,
            msg=f"智能提取失败: {str(e)}"
        )

