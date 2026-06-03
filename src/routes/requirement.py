"""用户需求相关路由"""
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from src.database import get_db
from src.models.response import success_response, error_response
from src.models.request import (
    RequirementSubmitRequest, RequirementSubmitResponse,
    RequirementParseRequest, RequirementParseResponse, ParsedKeywords
)
from src.services.database_service import RequirementService
from src.models.db_models import User
router = APIRouter(prefix="/api/v1/requirement", tags=["用户需求"])

@router.post("/submit")
async def submit_requirement(request: RequirementSubmitRequest, db: Session = Depends(get_db)):
    """提交用户需求 - 保存到数据库"""
    requirement_data = request.requirement.model_dump()

    # 🔥 处理 user_id：如果不存在则自动创建用户
    user_id = request.user_id or "anonymous"
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        user = User(
            user_id=user_id,
            username=user_id,
            email=f"{user_id}@travel-planner.com",
            password_hash="",
            is_active=True,
        )
        db.add(user)
        db.commit()
    
    # 创建需求记录
    requirement = RequirementService.create_requirement(
        db=db,
        user_id=user_id,
        requirement_data=requirement_data
    )
    
    return success_response(
        data=RequirementSubmitResponse(
            requirement_id=str(requirement.requirement_id),
            status=str(requirement.status)
        ).model_dump(),
        msg="需求提交成功"
    )

@router.post("/parse")
async def parse_requirement(request: RequirementParseRequest, db: Session = Depends(get_db)):
    """解析用户需求 - 从数据库读取并更新状态"""
    # 从数据库查询需求
    requirement = RequirementService.get_requirement(db, request.requirement_id)
    
    if not requirement:
        return error_response(code=404, msg="需求不存在")
    
    # 提取需求数据
    req_data = requirement.requirement_data
    
    # 解析关键词（这里简化处理，实际可以调用NLP服务）
    keywords = ParsedKeywords(
        city_name=req_data.get("city_name", ""),
        travel_days=req_data.get("travel_days", 1),
        total_budget=req_data.get("total_budget"),
        travel_type=req_data.get("travel_type"),
        preferences=req_data.get("preferences", [])
    )
    
    # 更新需求状态为已解析
    RequirementService.update_requirement_status(
        db=db,
        requirement_id=request.requirement_id,
        status="parsed",
        parsed_keywords=keywords.model_dump()
    )
    
    return success_response(
        data=RequirementParseResponse(
            requirement_id=request.requirement_id, 
            parsed=True, 
            keywords=keywords
        ).model_dump(),
        msg="需求解析成功"
    )

@router.get("/{requirement_id}")
async def get_requirement(requirement_id: str, db: Session = Depends(get_db)):
    """获取需求详情 - 从数据库查询"""
    requirement = RequirementService.get_requirement(db, requirement_id)
    
    if not requirement:
        return error_response(code=404, msg="需求不存在")
    
    return success_response(
        data={
            "requirement_id": requirement.requirement_id,
            "user_id": requirement.user_id,
            "requirement": requirement.requirement_data,
            "status": requirement.status,
            "parsed_keywords": requirement.parsed_keywords,
            "created_at": requirement.created_at.isoformat() if requirement.created_at is not None else None,
            "updated_at": requirement.updated_at.isoformat() if requirement.updated_at is not None else None
        },
        msg="获取成功"
    )