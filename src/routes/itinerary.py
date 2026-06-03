"""行程相关路由"""
import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from src.database import get_db
from src.models.response import success_response, error_response
from src.models.request import ItineraryCreateRequest, ItineraryUpdateRequest
from src.services.database_service import ItineraryService

router = APIRouter(prefix="/api/v1/itinerary", tags=["行程"])

@router.post("/create")
async def create_itinerary(request: ItineraryCreateRequest, db: Session = Depends(get_db)):
    """创建新行程 - 保存到数据库"""
    day_plans_data = [day.model_dump() for day in request.day_plans]
    
    itinerary = ItineraryService.create_itinerary(
        db=db,
        user_id=request.user_id,
        requirement_id=request.requirement_id,
        title=request.title,
        total_budget=request.total_budget,
        day_plans=day_plans_data
    )
    
    return success_response(
        data={
            "itinerary_id": itinerary.itinerary_id,
            "user_id": itinerary.user_id,
            "requirement_id": itinerary.requirement_id,
            "title": itinerary.title,
            "total_budget": itinerary.total_budget,
            "day_plans": itinerary.day_plans,
            "status": itinerary.status,
            "is_favorite": itinerary.is_favorite,
            "created_at": itinerary.created_at.isoformat() if itinerary.created_at else None,
            "updated_at": itinerary.updated_at.isoformat() if itinerary.updated_at else None
        },
        msg="行程创建成功"
    )

@router.get("/{itinerary_id}")
async def get_itinerary(itinerary_id: str, db: Session = Depends(get_db)):
    """获取行程详情 - 从数据库查询"""
    itinerary = ItineraryService.get_itinerary(db, itinerary_id)
    
    if not itinerary:
        return error_response(code=404, msg="行程不存在")
    
    # 确保day_plans是有效的JSON数组
    day_plans = itinerary.day_plans if isinstance(itinerary.day_plans, list) else []
    
    # 为每个day_plan添加必要的字段
    for day_plan in day_plans:
        # 确保attractions字段存在
        if "attractions" not in day_plan:
            day_plan["attractions"] = []
        # 确保meals字段存在
        if "meals" not in day_plan:
            day_plan["meals"] = []
        # 确保transport字段存在
        if "transport" not in day_plan:
            day_plan["transport"] = None
        # 确保hotel字段存在
        if "hotel" not in day_plan:
            day_plan["hotel"] = None
        # 确保weather字段存在
        if "weather" not in day_plan:
            day_plan["weather"] = None
        # 确保notes字段存在
        if "notes" not in day_plan:
            day_plan["notes"] = ""
    
    # 获取关联的需求信息以获取城市名称和旅行天数
    from src.models.db_models import UserRequirement
    requirement = db.query(UserRequirement).filter(UserRequirement.requirement_id == itinerary.requirement_id).first()
    city_name = requirement.requirement_data.get("city_name", "") if requirement else ""
    travel_days = requirement.requirement_data.get("travel_days", 1) if requirement else 1

    return success_response(
        data={
            "itinerary_id": itinerary.itinerary_id,
            "user_id": itinerary.user_id,
            "requirement_id": itinerary.requirement_id,
            "title": itinerary.title,
            "city_name": city_name,
            "travel_days": travel_days,
            "total_budget": itinerary.total_budget,
            "actual_cost": itinerary.actual_cost,
            "day_plans": day_plans,
            "status": itinerary.status,
            "is_favorite": itinerary.is_favorite,
            "created_at": itinerary.created_at.isoformat() if itinerary.created_at else None,
            "updated_at": itinerary.updated_at.isoformat() if itinerary.updated_at else None
        },
        msg="获取成功"
    )

@router.put("/{itinerary_id}")
async def update_itinerary(itinerary_id: str, request: ItineraryUpdateRequest, db: Session = Depends(get_db)):
    """更新行程信息 - 保存到数据库"""
    updates = {}
    
    if request.title is not None:
        updates["title"] = request.title
    
    if request.day_plans is not None:
        # day_plans已经是字典数组,直接使用
        updates["day_plans"] = request.day_plans
    
    if request.status is not None:
        updates["status"] = request.status
    
    if request.total_budget is not None:
        updates["total_budget"] = request.total_budget
    
    itinerary = ItineraryService.update_itinerary(db, itinerary_id, updates)
    
    if not itinerary:
        return error_response(code=404, msg="行程不存在")
    
    return success_response(
        data={
            "itinerary_id": itinerary.itinerary_id,
            "title": itinerary.title,
            "status": itinerary.status,
            "day_plans": itinerary.day_plans,
            "updated_at": itinerary.updated_at.isoformat() if itinerary.updated_at else None
        },
        msg="行程更新成功"
    )

@router.delete("/{itinerary_id}")
async def delete_itinerary(itinerary_id: str, db: Session = Depends(get_db)):
    """删除行程 - 从数据库删除"""
    success = ItineraryService.delete_itinerary(db, itinerary_id)
    
    if not success:
        return error_response(code=404, msg="行程不存在")
    
    return success_response(data={"deleted": True}, msg="行程删除成功")

@router.get("/user/{user_id}")
async def get_user_itineraries(
    user_id: str, 
    db: Session = Depends(get_db),
    is_favorite: Optional[bool] = Query(None, description="是否只查询收藏的行程")
):
    """获取用户的行程列表 - 从数据库查询"""
    itineraries = ItineraryService.get_user_itineraries(db, user_id, is_favorite)
    
    itinerary_list = [{
        "itinerary_id": itin.itinerary_id,
        "user_id": itin.user_id,
        "title": itin.title,
        "total_budget": itin.total_budget,
        "actual_cost": itin.actual_cost,
        "status": itin.status,
        "is_favorite": itin.is_favorite,
        "created_at": itin.created_at.isoformat() if itin.created_at else None,
        "updated_at": itin.updated_at.isoformat() if itin.updated_at else None
    } for itin in itineraries]
    
    return success_response(
        data={"total": len(itinerary_list), "itineraries": itinerary_list}, 
        msg="获取成功"
    )

@router.post("/{itinerary_id}/favorite")
async def toggle_favorite(itinerary_id: str, db: Session = Depends(get_db)):
    """切换行程收藏状态 - ⭐ 新增功能"""
    itinerary = ItineraryService.toggle_favorite(db, itinerary_id)
    
    if not itinerary:
        return error_response(code=404, msg="行程不存在")
    
    return success_response(
        data={
            "itinerary_id": itinerary.itinerary_id,
            "is_favorite": itinerary.is_favorite
        },
        msg=f"行程已{'收藏' if itinerary.is_favorite else '取消收藏'}"
    )

@router.post("/{itinerary_id}/save")
async def save_itinerary(itinerary_id: str, db: Session = Depends(get_db)):
    """保存行程为草稿 - ⭐ 新增功能"""
    itinerary = ItineraryService.update_itinerary(db, itinerary_id, {"status": "saved"})
    
    if not itinerary:
        return error_response(code=404, msg="行程不存在")
    
    return success_response(
        data={"itinerary_id": itinerary_id, "status": "saved"},
        msg="行程保存成功"
    )

@router.post("/{itinerary_id}/publish")
async def publish_itinerary(itinerary_id: str, db: Session = Depends(get_db)):
    """发布行程 - ⭐ 新增功能"""
    itinerary = ItineraryService.update_itinerary(db, itinerary_id, {"status": "published"})
    
    if not itinerary:
        return error_response(code=404, msg="行程不存在")
    
    return success_response(
        data={"itinerary_id": itinerary_id, "status": "published"},
        msg="行程发布成功"
    )