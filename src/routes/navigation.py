"""
导航路线查询路由 - 直接调用高德地图导航API，返回路线数据
"""
from typing import Dict, Any, Optional
from fastapi import APIRouter
from src.models.response import success_response, error_response
from src.services.navigation_service import NavigationService

router = APIRouter(prefix="/api/v1/navigation", tags=["导航路线"])

# 创建导航服务实例
navigation_service = NavigationService()


@router.post("/direction")
async def get_direction(request_data: Dict[str, Any]):
    """
    查询两点之间的导航路线
    
    请求参数:
    {
        "origin": "116.397,39.908" 或 "天安门广场",  # 起点坐标或地址
        "destination": "116.570,39.911" 或 "故宫博物院",  # 终点坐标或地址
        "mode": "driving",  # 导航模式: walking/driving/transit/bicycling
        "origin_name": "起点名称(可选)",  # 起点显示名称
        "destination_name": "终点名称(可选)"  # 终点显示名称
    }
    
    响应:
    {
        "code": 200,
        "msg": "success",
        "data": {
            "mode": "driving",
            "from": "起点名称",
            "to": "终点名称",
            "distance": 5000,
            "distance_text": "5.0公里",
            "duration": 900,
            "duration_text": "15分钟",
            "steps": [
                {
                    "instruction": "沿长安街行驶...",
                    "distance": 5000,
                    "duration": 900,
                    "polyline": "..."
                }
            ],
            "polyline": "..."  # 路线编码，可用于前端绘制路线
        }
    }
    """
    import logging
    logger = logging.getLogger(__name__)

    # 提取参数
    origin = request_data.get("origin")
    destination = request_data.get("destination")
    mode = request_data.get("mode", "driving")
    origin_name = request_data.get("origin_name", "")
    destination_name = request_data.get("destination_name", "")

    if not origin or not destination:
        return error_response(code=400, msg="缺少必要参数: origin 和 destination")

    try:
        logger.info(f"[Navigation API] 查询导航 - 起点: {origin}, 终点: {destination}, 模式: {mode}")

        result = await navigation_service.get_direction(
            origin=origin,
            destination=destination,
            mode=mode
        )

        if result["status"] == "success":
            route_data = result["data"]
            return success_response(
                data={
                    "mode": mode,
                    "from": origin_name or origin,
                    "to": destination_name or destination,
                    "distance": route_data.get("distance", 0),
                    "distance_text": navigation_service.format_distance(route_data.get("distance", 0)),
                    "duration": route_data.get("duration", 0),
                    "duration_text": navigation_service.format_duration(route_data.get("duration", 0)),
                    "steps": route_data.get("steps", []),
                    "polyline": route_data.get("polyline", "")
                },
                msg="导航路线查询成功"
            )
        else:
            return error_response(code=500, msg=result.get("message", "导航查询失败"))

    except Exception as e:
        logger.error(f"[Navigation API] 导航查询异常: {str(e)}")
        return error_response(code=500, msg=f"导航查询异常: {str(e)}")


@router.post("/geocode")
async def geocode(request_data: Dict[str, Any]):
    """
    地理编码：将地址转换为经纬度坐标
    
    请求参数:
    {
        "address": "天安门广场"
    }
    
    响应:
    {
        "code": 200,
        "data": {
            "address": "天安门广场",
            "location": "116.397,39.908"
        }
    }
    """
    address = request_data.get("address")

    if not address:
        return error_response(code=400, msg="缺少必要参数: address")

    try:
        location = await navigation_service.geocode(address)
        if location:
            return success_response(
                data={
                    "address": address,
                    "location": location
                },
                msg="地理编码成功"
            )
        else:
            return error_response(code=500, msg="地理编码失败，无法获取坐标")
    except Exception as e:
        return error_response(code=500, msg=f"地理编码异常: {str(e)}")
