"""
和风天气 API 路由（精简版）

作为纯代理层转发请求到和风天气独立 API Host，
API Key 和 Host 已硬编码在后端服务层。

接口：
- GET /api/v1/qweather/city/lookup?location=北京
- GET /api/v1/qweather/weather/now?location=110000
- GET /api/v1/qweather/weather/forecast?location=110000&days=7d
- GET /api/v1/qweather/weather/hourly?location=110000&hours=24h
"""
import logging
from fastapi import APIRouter, Query
from typing import Optional

from src.models.response import success_response, error_response
from src.services.qweather_service import qweather_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/qweather", tags=["和风天气"])


@router.get("/city/lookup")
async def city_lookup(
    location: str = Query(..., description="城市名、地址坐标、IP 或 行政区划ID"),
    adm: Optional[str] = Query(None, description="父级行政区划（可选）"),
):
    """搜索城市，和风天气原始响应"""
    try:
        result = await qweather_service.city_lookup(location, adm=adm)
        logger.info(f"和风天气城市搜索 [{location}]: code={result.get('code')}, location数量={len(result.get('location', []))}")
        if result.get("code") == "200":
            return success_response(data=result.get("location", []), msg="获取成功")
        return error_response(code=400, msg=f"城市搜索失败: {result.get('code')}")
    except Exception as e:
        logger.error(f"城市搜索失败: {e}")
        return error_response(code=500, msg=f"城市搜索失败: {str(e)}")


@router.get("/weather/now")
async def weather_now(
    location: str = Query(..., description="城市 Location ID"),
):
    """获取实时天气，和风天气原始响应"""
    try:
        result = await qweather_service.weather_now(location)
        if result.get("code") == "200":
            return success_response(data=result.get("now", {}), msg="获取成功")
        return error_response(code=400, msg=f"获取实时天气失败: {result.get('code')}")
    except Exception as e:
        logger.error(f"获取实时天气失败: {e}")
        return error_response(code=500, msg=f"获取实时天气失败: {str(e)}")


@router.get("/weather/forecast")
async def weather_forecast(
    location: str = Query(..., description="城市 Location ID"),
    days: str = Query("7d", description="预报天数: 3d / 7d / 10d / 15d / 30d"),
):
    """获取天气预报，和风天气原始响应"""
    try:
        result = await qweather_service.weather_forecast(location, days)
        logger.info(f"和风天气预报查询 [location={location}, days={days}]: code={result.get('code')}, daily数量={len(result.get('daily', []))}")
        if result.get("code") == "200":
            return success_response(data=result.get("daily", []), msg="获取成功")
        return error_response(code=400, msg=f"获取预报失败: {result.get('code')}")
    except Exception as e:
        logger.error(f"获取天气预报失败: {e}")
        return error_response(code=500, msg=f"获取天气预报失败: {str(e)}")


@router.get("/weather/hourly")
async def weather_hourly(
    location: str = Query(..., description="城市 Location ID"),
    hours: str = Query("24h", description="预报小时: 24h / 72h / 168h"),
):
    """获取逐小时预报，和风天气原始响应"""
    try:
        result = await qweather_service.weather_hourly(location, hours)
        if result.get("code") == "200":
            return success_response(data=result.get("hourly", []), msg="获取成功")
        return error_response(code=400, msg=f"获取逐小时预报失败: {result.get('code')}")
    except Exception as e:
        logger.error(f"获取逐小时预报失败: {e}")
        return error_response(code=500, msg=f"获取逐小时预报失败: {str(e)}")
