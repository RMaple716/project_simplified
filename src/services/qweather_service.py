"""
和风天气 API 服务

功能：
- 城市搜索（通过和风天气API）
- 实时天气查询
- 预报天气查询（3d / 7d / 10d / 15d / 30d）

使用方式：
- 需要配置 QWEATHER_API_KEY 和 QWEATHER_API_HOST 环境变量
- 或通过构造函数传入
"""
import logging
import os
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)


class QWeatherService:
    """和风天气API服务类"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_host: Optional[str] = None,
        timeout: float = 10.0,
    ):
        """
        初始化和风天气服务

        API Key 和 Host 采用以下优先级：
        1. 构造函数传入（api_key, api_host）
        2. 环境变量（QWEATHER_API_KEY, QWEATHER_API_HOST）
        3. 硬编码默认值（见下方代码）

        Args:
            api_key: 和风天气 API Key
            api_host: 和风天气独立 API Host
                      例如: n22pg8hrhd.re.qweatherapi.com（无 https:// 前缀）
            timeout: 请求超时时间（秒）
        """
        # ===== 🔧 硬编码配置（可按需修改） =====
        self.api_key = (
            api_key
            or os.getenv("QWEATHER_API_KEY")
            or "ab25b0b204e14235ad11a5e592699a98"
        )
        raw_host = (
            api_host
            or os.getenv("QWEATHER_API_HOST")
            or "n22pg8hrhd.re.qweatherapi.com"
        )
        # ========================================

        # 确保 api_host 没有 https:// 前缀
        self.api_host = raw_host.replace("https://", "").replace("http://", "")
        self.timeout = timeout

        if not self.api_key:
            logger.warning("QWeather API Key 未配置")

    async def _request(
        self,
        path: str,
        params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        发起 HTTPS 请求到和风天气 API

        Args:
            path: API 路径，如 /geo/v2/city/lookup
            params: 查询参数

        Returns:
            解析后的 JSON 响应
        """
        if not self.api_key:
            return {"code": "401", "error": "API Key 未配置"}

        request_params = dict(params or {})
        request_params["key"] = self.api_key

        url = f"https://{self.api_host}{path}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=request_params)
                response.raise_for_status()

                # httpx 会自动解压 gzip/deflate 响应体（默认行为），
                # 所以 response.content / response.text 已经是解压后的数据。
                # 直接调用 response.json() 解析 JSON 即可，无需手动解压。
                return response.json()

        except httpx.TimeoutException:
            logger.error(f"请求超时: {url}")
            return {"code": "504", "error": "请求超时"}
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP 错误: {e.response.status_code} - {url}")
            return {"code": str(e.response.status_code), "error": f"HTTP 错误: {e.response.status_code}"}
        except Exception as e:
            logger.error(f"请求失败: {e}")
            return {"code": "500", "error": f"请求失败: {e}"}

    async def city_lookup(
        self,
        location: str,
        adm: Optional[str] = None,
        number: int = 10,
    ) -> Dict[str, Any]:
        """
        城市搜索

        和风天气城市查询 API:
        - 旧地址路径: /v2/city/lookup
        - 独立 API Host 路径: /geo/v2/city/lookup

        Args:
            location: 城市名、地址坐标（经度,纬度）、IP、行政区划ID
            adm: 父级行政区划（可选）
            number: 返回数量，默认 10，最多 20

        Returns:
            {
                "code": "200",
                "location": [
                    {
                        "name": "北京",
                        "id": "110000",
                        "lat": "39.90499",
                        "lon": "116.40529",
                        "adm2": "北京",
                        "adm1": "北京市",
                        "country": "中国",
                        "tz": "Asia/Shanghai",
                        "utcOffset": "+08:00",
                        "isDst": "0",
                        "type": "city",
                        "rank": "11",
                        "fxLink": "https://www.qweather.com/weather/beijing-110000.html"
                    }
                ],
                "refer": { ... }
            }
        """
        params = {"location": location, "number": str(number)}
        if adm:
            params["adm"] = adm
        return await self._request("/geo/v2/city/lookup", params)

    async def weather_now(self, location: str) -> Dict[str, Any]:
        """
        获取实时天气

        API: /v7/weather/now

        Args:
            location: 城市 Location ID（通过 city_lookup 获取）

        Returns:
            {
                "code": "200",
                "now": {
                    "obsTime": "2025-01-15T10:00+08:00",
                    "temp": "20",
                    "feelsLike": "18",
                    "icon": "101",
                    "text": "多云",
                    "wind360": "180",
                    "windDir": "南风",
                    "windScale": "3",
                    "windSpeed": "15",
                    "humidity": "30",
                    "precip": "0.0",
                    "pressure": "1020",
                    "vis": "10",
                    "cloud": "60",
                    "dew": "-2"
                },
                "refer": { ... }
            }
        """
        return await self._request("/v7/weather/now", {"location": location})

    async def weather_forecast(
        self,
        location: str,
        days: str = "7d",
    ) -> Dict[str, Any]:
        """
        获取天气预报

        API: /v7/weather/{days}d
        days 可选: 3d, 7d（免费）, 10d, 15d, 30d（付费）

        Args:
            location: 城市 Location ID
            days: 预报天数，可选 3d / 7d / 10d / 15d / 30d

        Returns:
            {
                "code": "200",
                "daily": [
                    {
                        "fxDate": "2025-01-15",
                        "sunrise": "07:35",
                        "sunset": "17:15",
                        "moonrise": "19:52",
                        "moonset": "08:52",
                        "moonPhase": "满月",
                        "moonPhaseIcon": "804",
                        "tempMax": "22",
                        "tempMin": "10",
                        "iconDay": "101",
                        "textDay": "多云",
                        "iconNight": "151",
                        "textNight": "晴",
                        "wind360Day": "180",
                        "windDirDay": "南风",
                        "windScaleDay": "3",
                        "windSpeedDay": "15",
                        "wind360Night": "180",
                        "windDirNight": "南风",
                        "windScaleNight": "3",
                        "windSpeedNight": "15",
                        "humidity": "30",
                        "precip": "0.0",
                        "pressure": "1020",
                        "vis": "10",
                        "cloud": "60",
                        "uvIndex": "3"
                    },
                    ...
                ],
                "refer": { ... }
            }
        """
        # 验证 days 参数
        valid_days = ["3d", "7d", "10d", "15d", "30d"]
        if days not in valid_days:
            days = "7d"
        return await self._request(f"/v7/weather/{days}", {"location": location})

    async def weather_hourly(
        self,
        location: str,
        hours: str = "24h",
    ) -> Dict[str, Any]:
        """
        获取逐小时天气

        API: /v7/weather/{hours}h
        hours 可选: 24h, 72h, 168h

        Args:
            location: 城市 Location ID
            hours: 小时数，可选 24h / 72h / 168h

        Returns:
            {
                "code": "200",
                "hourly": [
                    {
                        "fxTime": "2025-01-15T11:00+08:00",
                        "temp": "20",
                        "icon": "101",
                        "text": "多云",
                        "wind360": "180",
                        "windDir": "南风",
                        "windScale": "3",
                        "windSpeed": "15",
                        "humidity": "30",
                        "precip": "0.0",
                        "pop": "10",
                        "pressure": "1020",
                        "cloud": "60",
                        "dew": "-2"
                    },
                    ...
                ],
                "refer": { ... }
            }
        """
        valid_hours = ["24h", "72h", "168h"]
        if hours not in valid_hours:
            hours = "24h"
        return await self._request(f"/v7/weather/{hours}h", {"location": location})


# 全局单例
qweather_service = QWeatherService()
