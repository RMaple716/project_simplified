"""
高德地图导航API服务

集成了数据库缓存 + 全局QPS限速器，避免QPS超限。
调用方法（geocode / get_direction）流程：
  1. 先查数据库缓存，命中直接返回
  2. 缓存未命中 → 通过全局限速器获取令牌 → 请求高德API → 写入缓存
"""
import httpx
from typing import Dict, Any, Optional, List
import os
import asyncio
from collections import defaultdict

from src.services.amap_cache_service import get_cached_response, set_cached_response
from src.services.rate_limiter import amap_rate_limiter


class NavigationService:
    """高德地图导航API服务类"""

    def __init__(self, api_key: Optional[str] = None, min_interval: float = 1.5):
        """
        初始化导航服务

        Args:
            api_key: 高德地图API密钥,如果不提供则从环境变量AMAP_API_KEY读取
            min_interval: 最小查询间隔(秒),默认1秒
        """
        self.api_key = api_key or os.getenv('AMAP_API_KEY', '')
        self.private_key = os.getenv('AMAP_PRIVATE_KEY', '')
        self.base_url = "https://restapi.amap.com/v3"
        self.min_interval = min_interval
        self.last_query_time = defaultdict(float)
        self.query_lock = defaultdict(asyncio.Lock)

    async def geocode(self, address: str) -> Optional[str]:
        """
        将地址转换为经纬度坐标（优先使用缓存，通过全局限速器控制QPS）

        Args:
            address: 地址字符串

        Returns:
            坐标字符串，格式为 "经度,纬度"，如果失败返回 None
        """
        import logging
        logger = logging.getLogger(__name__)

        if not self.api_key:
            logger.warning("[Navigation] 未配置API密钥")
            return None

        cache_params = {"address": address}

        # ========== 1. 先查缓存 ==========
        cached = get_cached_response("geocode", cache_params)
        if cached is not None:
            if isinstance(cached, dict) and cached.get("status") == "1":
                geocodes = cached.get("geocodes", [])
                if geocodes:
                    location = geocodes[0].get("location", "")
                    if location:
                        logger.info(f"[Navigation] 缓存命中 - 地址: {address} -> 坐标: {location}")
                        return location
            logger.info(f"[Navigation] 缓存命中但数据无效，忽略缓存")

        url = f"{self.base_url}/geocode/geo"
        params = {
            'key': self.api_key,
            'address': address
        }
        if self.private_key:
            params['sig'] = self._generate_sig(params)

        try:
            logger.info(f"[Navigation] 调用地理编码API - 地址: {address}")

            # ========== 2. 通过全局限速器控制QPS ==========
            async with amap_rate_limiter:
                async with httpx.AsyncClient() as client:
                    response = await client.get(url, params=params, timeout=10.0)
                    response.raise_for_status()
                    data = response.json()
                    logger.info(f"[Navigation] 地理编码API返回: {data}")

            # ========== 3. 写入缓存 ==========
            if data.get('status') == '1':
                set_cached_response("geocode", cache_params, data)

            if data.get('status') == '1' and data.get('geocodes'):
                location = data['geocodes'][0].get('location', '')
                logger.info(f"[Navigation] 获取到坐标: {location}")
                return location
            logger.warning(f"[Navigation] 地理编码失败 - 状态: {data.get('status')}, 信息: {data.get('info', '未知错误')}")
            return None
        except Exception as e:
            logger.error(f"[Navigation] 地理编码异常: {str(e)}")
            return None

    async def get_direction(
        self,
        origin: str,
        destination: str,
        mode: str = 'driving'
    ) -> Dict[str, Any]:
        """
        获取导航路线（优先使用缓存，通过全局限速器控制QPS）

        Args:
            origin: 起点地址或坐标
            destination: 终点地址或坐标
            mode: 导航模式
                - walking: 步行
                - driving: 驾车
                - transit: 公交
                - bicycling: 骑行

        Returns:
            导航信息字典
        """
        import logging
        logger = logging.getLogger(__name__)

        if not self.api_key:
            logger.warning("[Navigation] 未配置API密钥")
            return {
                'status': 'error',
                'message': '未配置高德地图API密钥'
            }

        logger.info(f"[Navigation] 调用导航API - 起点: {origin}, 终点: {destination}, 模式: {mode}")

        cache_params = {"origin": origin, "destination": destination, "mode": mode}

        # ========== 1. 先查缓存 ==========
        cached = get_cached_response("direction", cache_params)
        if cached is not None:
            if isinstance(cached, dict) and cached.get("status") == "1":
                logger.info(f"[Navigation] 缓存命中路线数据")
                route_data = self._parse_route_data(cached, mode)
                return {
                    'status': 'success',
                    'data': route_data
                }
            logger.info(f"[Navigation] 缓存命中但数据无效，忽略缓存")

        # ========== 2. 缓存未命中 → 请求API ==========
        # 按相同key的频率控制（保留原有限速作为补充）
        query_key = f"{origin}_{destination}_{mode}"
        async with self.query_lock[query_key]:
            current_time = asyncio.get_event_loop().time()
            last_time = self.last_query_time[query_key]
            elapsed = current_time - last_time

            if elapsed < self.min_interval:
                wait_time = self.min_interval - elapsed
                await asyncio.sleep(wait_time)

            self.last_query_time[query_key] = asyncio.get_event_loop().time()

        # 根据模式选择API
        if mode == 'walking':
            url = f"{self.base_url}/direction/walking"
        elif mode == 'driving':
            url = f"{self.base_url}/direction/driving"
        elif mode == 'transit':
            url = f"{self.base_url}/direction/transit/integrated"
        elif mode == 'bicycling':
            url = f"{self.base_url}/direction/bicycling"
        else:
            return {
                'status': 'error',
                'message': f'不支持的导航模式: {mode}'
            }

        params = {
            'key': self.api_key,
            'origin': origin,
            'destination': destination
        }
        if self.private_key:
            params['sig'] = self._generate_sig(params)

        try:
            logger.info(f"[Navigation] 请求URL: {url}")
            logger.info(f"[Navigation] 请求参数: {params}")

            # ====== 通过全局限速器获取令牌后再请求 ======
            async with amap_rate_limiter:
                async with httpx.AsyncClient() as client:
                    response = await client.get(url, params=params, timeout=10.0)
                    response.raise_for_status()
                    data = response.json()
                    logger.info(f"[Navigation] 导航API返回: {data}")

            # ====== QPS超限自动重试（通过限速器重试）======
            if data.get('infocode') == '10021':  # CUQPS_HAS_EXCEEDED_THE_LIMIT
                logger.warning(f"[Navigation] QPS超限，通过限速器等待后重试...")
                await asyncio.sleep(2.0)
                async with amap_rate_limiter:
                    async with httpx.AsyncClient() as client2:
                        response2 = await client2.get(url, params=params, timeout=10.0)
                        response2.raise_for_status()
                        data = response2.json()
                        logger.info(f"[Navigation] 重试后API返回: {data}")
                        if data.get('infocode') == '10021':
                            logger.warning(f"[Navigation] QPS再次超限，等待3秒后最后一次重试...")
                            await asyncio.sleep(3.0)
                            async with amap_rate_limiter:
                                async with httpx.AsyncClient() as client3:
                                    response3 = await client3.get(url, params=params, timeout=10.0)
                                    response3.raise_for_status()
                                    data = response3.json()
                                    logger.info(f"[Navigation] 第二次重试后API返回: {data}")

            # ========== 3. 写入缓存 ==========
            if data.get('status') == '1':
                set_cached_response("direction", cache_params, data)

            if data.get('status') == '1':
                route_data = self._parse_route_data(data, mode)
                logger.info(f"[Navigation] 解析后的路线数据: {route_data}")
                return {
                    'status': 'success',
                    'data': route_data
                }
            else:
                logger.warning(f"[Navigation] 导航API返回错误 - 状态: {data.get('status')}, 信息: {data.get('info', '获取导航信息失败')}")
                return {
                    'status': 'error',
                    'message': data.get('info', '获取导航信息失败')
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

    def _parse_route_data(self, data: Dict[str, Any], mode: str) -> Dict[str, Any]:
        """
        解析路线数据
        """
        route_info = {
            'mode': mode,
            'distance': 0,
            'duration': 0,
            'steps': [],
            'polyline': '',
            'transits': []
        }

        def _safe_int(value, default=0):
            if value is None:
                return default
            try:
                return int(float(str(value)))
            except (ValueError, TypeError):
                return default

        def _safe_float_str(value, default=''):
            if value is None:
                return default
            try:
                return float(str(value))
            except (ValueError, TypeError):
                return default

        if mode in ['walking', 'driving', 'bicycling']:
            route = data.get('route', {})
            paths = route.get('paths', [])
            if paths:
                path = paths[0]
                route_info['distance'] = _safe_int(path.get('distance', 0))
                route_info['duration'] = _safe_int(path.get('duration', 0))
                route_info['polyline'] = path.get('polyline', '')
                steps = path.get('steps', [])
                for step in steps:
                    route_info['steps'].append({
                        'instruction': step.get('instruction', ''),
                        'distance': _safe_int(step.get('distance', 0)),
                        'duration': _safe_int(step.get('duration', 0)),
                        'polyline': step.get('polyline', ''),
                        'road': step.get('road', ''),
                        'action': step.get('action', ''),
                        'assistant_action': step.get('assistant_action', '')
                    })
        elif mode == 'transit':
            route = data.get('route', {})
            transits = route.get('transits', [])
            if transits:
                transit = transits[0]
                route_info['distance'] = _safe_int(transit.get('distance', 0))
                route_info['duration'] = _safe_int(transit.get('duration', 0))
                all_transits = []
                for t in transits:
                    all_transits.append({
                        'cost': _safe_float_str(t.get('cost', 0)),
                        'duration': _safe_int(t.get('duration', 0)),
                        'walking_distance': _safe_int(t.get('walking_distance', 0)),
                        'distance': _safe_int(t.get('distance', 0)),
                    })
                segments = transit.get('segments', [])
                for seg_idx, segment in enumerate(segments):
                    walking = segment.get('walking', {})
                    walking_steps = walking.get('steps', [])
                    walking_distance = _safe_int(walking.get('distance', 0))
                    if walking and walking_distance > 0:
                        walking_polylines = []
                        for ws in walking_steps:
                            wp = ws.get('polyline', '')
                            if wp:
                                walking_polylines.append(wp)
                        route_info['steps'].append({
                            'type': 'walking',
                            'instruction': f"步行{walking_distance}米",
                            'distance': walking_distance,
                            'duration': _safe_int(walking.get('duration', 0)),
                            'polyline': ';'.join(walking_polylines) if walking_polylines else '',
                            'seg_steps': [
                                {
                                    'instruction': ws.get('instruction', ''),
                                    'distance': _safe_int(ws.get('distance', 0)),
                                    'polyline': ws.get('polyline', ''),
                                    'road': ws.get('road', ''),
                                    'action': ws.get('action', ''),
                                    'assistant_action': ws.get('assistant_action', '')
                                }
                                for ws in walking_steps
                            ]
                        })
                    bus = segment.get('bus', {})
                    buslines = bus.get('buslines', [])
                    if buslines:
                        for busline in buslines:
                            route_info['steps'].append({
                                'type': busline.get('type', 'bus'),
                                'instruction': f"乘坐{busline.get('name', '')}",
                                'name': busline.get('name', ''),
                                'distance': _safe_int(busline.get('distance', 0)),
                                'duration': _safe_int(busline.get('duration', 0)),
                                'departure_stop': busline.get('departure_stop', {}).get('name', ''),
                                'arrival_stop': busline.get('arrival_stop', {}).get('name', ''),
                                'departure_location': busline.get('departure_stop', {}).get('location', ''),
                                'arrival_location': busline.get('arrival_stop', {}).get('location', ''),
                                'via_num': _safe_int(busline.get('via_num', 0)),
                                'via_stops': [
                                    {'name': vs.get('name', ''), 'location': vs.get('location', '')}
                                    for vs in busline.get('via_stops', [])
                                ],
                                'start_time': busline.get('start_time', ''),
                                'end_time': busline.get('end_time', ''),
                                'polyline': busline.get('polyline', '')
                            })
                    entrance = segment.get('entrance', {})
                    if entrance and entrance.get('name'):
                        route_info['steps'].append({
                            'type': 'entrance',
                            'instruction': f"从{entrance.get('name', '')}进站",
                            'name': entrance.get('name', ''),
                            'location': entrance.get('location', ''),
                            'polyline': ''
                        })
                    exit_info = segment.get('exit', {})
                    if exit_info and exit_info.get('name'):
                        route_info['steps'].append({
                            'type': 'exit',
                            'instruction': f"从{exit_info.get('name', '')}出站",
                            'name': exit_info.get('name', ''),
                            'location': exit_info.get('location', ''),
                            'polyline': ''
                        })
                route_info['transits'] = all_transits
                # 拼接公交模式的完整 polyline（从各 busline 的 polyline 拼接）
                all_transit_polylines = []
                for step in route_info['steps']:
                    if step.get('polyline'):
                        all_transit_polylines.append(step['polyline'])
                if all_transit_polylines:
                    route_info['polyline'] = ';'.join(all_transit_polylines)
        return route_info
    def _generate_sig(self, params: Dict[str, str]) -> str:
        """
        生成高德API签名（sig）
        
        规则：
        1. 按参数名升序排列
        2. 拼接成 key1=value1&key2=value2 格式
        3. 末尾直接拼接私钥
        4. 计算MD5（32位小写）
        """
        import hashlib
        if not self.private_key:
            return ''
        # 过滤掉 sig 本身，按 key 排序
        sorted_keys = sorted(k for k in params.keys() if k != 'sig')
        query = '&'.join(f'{k}={params[k]}' for k in sorted_keys)
        raw = query + self.private_key
        sig = hashlib.md5(raw.encode('utf-8')).hexdigest()
        return sig

    def format_distance(self, distance: int) -> str:
        """
        格式化距离

        Args:
            distance: 距离（米）

        Returns:
            格式化后的距离字符串
        """
        if distance >= 1000:
            return f"{distance / 1000:.1f}公里"
        return f"{distance}米"

    def format_duration(self, duration: int) -> str:
        """
        格式化时长

        Args:
            duration: 时长（秒）

        Returns:
            格式化后的时长字符串
        """
        hours = duration // 3600
        minutes = (duration % 3600) // 60

        if hours > 0:
            return f"{hours}小时{minutes}分钟"
        return f"{minutes}分钟"


    
# 创建全局实例
navigation_service = NavigationService()


