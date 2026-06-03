"""
自然语言处理相关路由
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from src.models.response import success_response, error_response
from src.services.travel_extractor import TravelExtractor

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

@router.post("/extract", response_model=dict)
async def extract_travel_info(request: NLPRequest):
    """
    从自然语言中提取旅游需求信息

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
