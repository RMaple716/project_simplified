"""
高德地图天气API服务
"""
import httpx
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import os
import asyncio
from collections import defaultdict

class WeatherService:
    """高德地图天气API服务类"""

    def __init__(self, api_key: Optional[str] = None, min_interval: float = 2.0):
        """
        初始化天气服务

        Args:
            api_key: 高德地图API密钥,如果不提供则从环境变量AMAP_API_KEY读取
            min_interval: 最小查询间隔(秒),默认2秒
        """
        self.api_key = api_key or os.getenv('AMAP_API_KEY', '')
        self.base_url = "https://restapi.amap.com/v3"
        self.min_interval = min_interval
        self.last_query_time = defaultdict(float)
        self.query_lock = defaultdict(asyncio.Lock)

    async def get_weather(self, city: str, extensions: str = 'base') -> Dict[str, Any]:
        """
        获取天气信息

        Args:
            city: 城市名称或adcode
            extensions: 天气类型
                - base: 实况天气
                - all: 预报天气

        Returns:
            天气信息字典
        """
        if not self.api_key:
            return {
                'status': 'error',
                'message': '未配置高德地图API密钥'
            }

        # 频率控制:检查距离上次查询的时间
        query_key = f"{city}_{extensions}"
        async with self.query_lock[query_key]:
            current_time = asyncio.get_event_loop().time()
            last_time = self.last_query_time[query_key]
            elapsed = current_time - last_time

            if elapsed < self.min_interval:
                wait_time = self.min_interval - elapsed
                await asyncio.sleep(wait_time)

            self.last_query_time[query_key] = asyncio.get_event_loop().time()

        url = f"{self.base_url}/weather/weatherInfo"
        params = {
            'key': self.api_key,
            'city': city,
            'extensions': extensions
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()

                if data.get('status') == '1':
                    return {
                        'status': 'success',
                        'data': data.get('lives', []) if extensions == 'base' else data.get('forecasts', [])
                    }
                else:
                    return {
                        'status': 'error',
                        'message': data.get('info', '获取天气信息失败')
                    }

        except httpx.TimeoutException:
            return {
                'status': 'error',
                'message': '请求超时'
            }
        except httpx.HTTPError as e:
            return {
                'status': 'error',
                'message': f'HTTP错误: {str(e)}'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'未知错误: {str(e)}'
            }

    async def get_current_weather(self, city: str) -> Dict[str, Any]:
        """
        获取实时天气

        Args:
            city: 城市名称或adcode

        Returns:
            实时天气信息
        """
        result = await self.get_weather(city, extensions='base')
        if result['status'] == 'success' and result['data']:
            weather = result['data'][0]
            return {
                'status': 'success',
                'data': {
                    'province': weather.get('province'),
                    'city': weather.get('city'),
                    'adcode': weather.get('adcode'),
                    'weather': weather.get('weather'),
                    'temperature': weather.get('temperature'),
                    'winddirection': weather.get('winddirection'),
                    'windpower': weather.get('windpower'),
                    'humidity': weather.get('humidity'),
                    'reporttime': weather.get('reporttime'),
                    # 添加更多详细信息
                    'temperature_float': float(weather.get('temperature', 0)),
                    'humidity_float': float(weather.get('humidity', 0)),
                    'windpower_level': int(weather.get('windpower', '0').replace('≤', '').replace('级', '')),
                    'weather_code': self._get_weather_code(weather.get('weather', '')),
                    'is_night': self._is_night_time(weather.get('reporttime', '')),
                    'weather_description': self._get_weather_description(weather.get('weather', '')),
                    'travel_suggestion': self._get_travel_suggestion(weather.get('weather', ''), float(weather.get('temperature', 0)))
                }
            }
        return result

    async def get_forecast(self, city: str) -> Dict[str, Any]:
        """
        获取天气预报

        Args:
            city: 城市名称或adcode

        Returns:
            预报天气信息
        """
        result = await self.get_weather(city, extensions='all')
        if result['status'] == 'success' and result['data']:
            forecast = result['data'][0]
            # 转换预报数据格式
            casts = []
            for cast in forecast.get('casts', []):
                day_temp = float(cast.get('daytemp', 0))
                night_temp = float(cast.get('nighttemp', 0))
                day_weather = cast.get('dayweather', '')
                night_weather = cast.get('nightweather', '')

                casts.append({
                    'date': cast.get('date'),
                    'week': cast.get('week'),
                    'dayweather': day_weather,
                    'nightweather': night_weather,
                    'daytemp': cast.get('daytemp'),
                    'nighttemp': cast.get('nighttemp'),
                    'daytemp_float': day_temp,
                    'nighttemp_float': night_temp,
                    'daywind': cast.get('daywind'),
                    'nightwind': cast.get('nightwind'),
                    'daypower': cast.get('daypower'),
                    'nightpower': cast.get('nightpower'),
                    'daypower_level': int(cast.get('daypower', '0').replace('-', ' ').split()[0]),
                    'nightpower_level': int(cast.get('nightpower', '0').replace('-', ' ').split()[0]),
                    'weather_code': self._get_weather_code(day_weather),
                    'day_weather_description': self._get_weather_description(day_weather),
                    'night_weather_description': self._get_weather_description(night_weather),
                    'temperature_range': f"{night_temp}°C ~ {day_temp}°C",
                    'day_travel_suggestion': self._get_travel_suggestion(day_weather, day_temp),
                    'night_travel_suggestion': self._get_travel_suggestion(night_weather, night_temp),
                    'is_suitable_for_outdoor': self._is_suitable_for_outdoor(day_weather, day_temp)
                })

            return {
                'status': 'success',
                'data': {
                    'city': forecast.get('city'),
                    'adcode': forecast.get('adcode'),
                    'province': forecast.get('province'),
                    'reporttime': forecast.get('reporttime'),
                    'casts': casts
                }
            }
        return result

    def _get_weather_code(self, weather: str) -> str:
        """
        获取天气代码

        Args:
            weather: 天气描述

        Returns:
            天气代码
        """
        weather_map = {
            '晴': 'sunny',
            '多云': 'cloudy',
            '阴': 'overcast',
            '雨': 'rainy',
            '雪': 'snowy',
            '雾': 'foggy',
            '霾': 'hazy',
            '沙尘': 'dusty',
            '小雨': 'light_rain',
            '中雨': 'moderate_rain',
            '大雨': 'heavy_rain',
            '暴雨': 'storm',
            '小雪': 'light_snow',
            '中雪': 'moderate_snow',
            '大雪': 'heavy_snow'
        }

        for key, code in weather_map.items():
            if key in weather:
                return code
        return 'unknown'

    def _is_night_time(self, reporttime: str) -> bool:
        """
        判断是否为夜间

        Args:
            reporttime: 报告时间

        Returns:
            是否为夜间
        """
        try:
            hour = int(reporttime.split(' ')[1].split(':')[0])
            return hour >= 19 or hour < 6
        except:
            return False

    def _get_weather_description(self, weather: str) -> str:
        """
        获取天气详细描述

        Args:
            weather: 天气描述

        Returns:
            天气详细描述
        """
        descriptions = {
            '晴': '天气晴朗,阳光充足',
            '多云': '云量较多,阳光时有时无',
            '阴': '天空阴暗,无阳光',
            '小雨': '雨势较小,出行需带伞',
            '中雨': '雨势中等,注意防滑',
            '大雨': '雨势较大,建议室内活动',
            '暴雨': '雨势极大,避免外出',
            '小雪': '雪量较小,注意保暖',
            '中雪': '雪量中等,路面湿滑',
            '大雪': '雪量较大,谨慎出行',
            '雾': '能见度低,注意安全',
            '霾': '空气质量差,建议佩戴口罩',
            '沙尘': '空气质量差,避免户外活动'
        }

        for key, desc in descriptions.items():
            if key in weather:
                return desc
        return '天气正常,适合出行'

    def _get_travel_suggestion(self, weather: str, temperature: float) -> str:
        """
        获取出行建议

        Args:
            weather: 天气描述
            temperature: 温度

        Returns:
            出行建议
        """
        suggestions = []

        # 温度建议
        if temperature < 0:
            suggestions.append('气温极低,注意保暖')
        elif temperature < 10:
            suggestions.append('气温较低,建议穿厚外套')
        elif temperature < 20:
            suggestions.append('气温适中,建议穿薄外套')
        elif temperature < 30:
            suggestions.append('气温适宜,穿着舒适')
        else:
            suggestions.append('气温较高,注意防暑')

        # 天气建议
        if '雨' in weather:
            if '暴雨' in weather:
                suggestions.append('暴雨天气,避免外出')
            elif '大雨' in weather:
                suggestions.append('大雨天气,建议室内活动')
            else:
                suggestions.append('雨天出行,记得带伞')
        elif '雪' in weather:
            suggestions.append('雪天路滑,注意安全')
        elif '雾' in weather or '霾' in weather:
            suggestions.append('能见度低,注意交通安全')
        elif '沙尘' in weather:
            suggestions.append('空气质量差,避免户外活动')
        elif '晴' in weather:
            suggestions.append('天气晴朗,适合户外活动')

        return '; '.join(suggestions) if suggestions else '天气良好,适合出行'

    def _is_suitable_for_outdoor(self, weather: str, temperature: float) -> bool:
        """
        判断是否适合户外活动

        Args:
            weather: 天气描述
            temperature: 温度

        Returns:
            是否适合户外活动
        """
        # 温度检查
        if temperature < -10 or temperature > 40:
            return False

        # 天气检查
        if '暴雨' in weather or '暴雪' in weather or '沙尘' in weather:
            return False

        if '霾' in weather:
            return False

        # 大雨大雪不适合户外活动
        if '大雨' in weather or '大雪' in weather:
            return False

        return True

    async def get_weather_by_date(self, city: str, date: datetime) -> Dict[str, Any]:
        """
        获取指定日期的天气

        Args:
            city: 城市名称或adcode
            date: 目标日期

        Returns:
            指定日期的天气信息
        """
        result = await self.get_forecast(city)
        if result['status'] == 'success':
            target_date = date.strftime('%Y-%m-%d')
            for cast in result['data']['casts']:
                if cast['date'] == target_date:
                    return {
                        'status': 'success',
                        'data': cast
                    }
            return {
                'status': 'error',
                'message': '未找到指定日期的天气预报'
            }
        return result

# 创建全局实例
weather_service = WeatherService()
