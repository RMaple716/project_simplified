"""健康检查路由"""
from fastapi import APIRouter
from src.models.response import success_response

router = APIRouter(prefix="/api/v1", tags=["健康检查"])

@router.get("/health")
async def health_check():
    return success_response(
        data={"status": "healthy", "service": "travel-planner-backend"},
        msg="服务运行正常"
    )