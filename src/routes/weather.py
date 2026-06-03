"""
天气相关路由
"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional
from src.models.response import success_response, error_response
from src.services.weather_service import weather_service

router = APIRouter(prefix="/api/v1/weather", tags=["天气服务"])

class WeatherRequest(BaseModel):
    city: str

@router.get("/current")
async def get_current_weather(city: str = Query(..., description="城市名称或adcode")):
    """
    获取实时天气

    参数:
    - city: 城市名称或adcode

    返回:
    - province: 省份
    - city: 城市
    - adcode: 行政区划代码
    - weather: 天气现象
    - temperature: 实时气温
    - winddirection: 风向
    - windpower: 风力
    - humidity: 湿度
    - reporttime: 数据发布时间
    """
    try:
        result = await weather_service.get_current_weather(city)
        if result['status'] == 'success':
            return success_response(
                data=result['data'],
                msg="获取成功"
            )
        else:
            return error_response(
                code=400,
                msg=result.get('message', '获取天气信息失败')
            )
    except Exception as e:
        return error_response(
            code=500,
            msg=f"服务错误: {str(e)}"
        )

@router.get("/forecast")
async def get_weather_forecast(city: str = Query(..., description="城市名称或adcode")):
    """
    获取天气预报

    参数:
    - city: 城市名称或adcode

    返回:
    - city: 城市
    - adcode: 行政区划代码
    - province: 省份
    - reporttime: 数据发布时间
    - casts: 预报数据列表
        - date: 日期
        - week: 星期
        - dayweather: 白天天气现象
        - nightweather: 晚上天气现象
        - daytemp: 白天温度
        - nighttemp: 晚上温度
        - daywind: 白天风向
        - nightwind: 晚上风向
        - daypower: 白天风力
        - nightpower: 晚上风力
    """
    try:
        result = await weather_service.get_forecast(city)
        if result['status'] == 'success':
            return success_response(
                data=result['data'],
                msg="获取成功"
            )
        else:
            return error_response(
                code=400,
                msg=result.get('message', '获取天气预报失败')
            )
    except Exception as e:
        return error_response(
            code=500,
            msg=f"服务错误: {str(e)}"
        )
