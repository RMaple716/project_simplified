"""
交通推荐智能体
"""
import time
import uuid
from typing import Dict, Any, List, Optional
from .base_agent import BaseAgent
from src.services.navigation_service import navigation_service

class TransportAgent(BaseAgent):
    """交通推荐智能体"""

    def __init__(self):
        super().__init__(
            agent_id="transport_agent_001",
            name="交通规划助手",
            description="为用户提供交通方案推荐"
        )

    def get_capabilities(self) -> List[str]:
        return [
            "交通方案推荐",
            "路线规划",
            "票价查询",
            "时刻表查询"
        ]

    async def execute(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行交通推荐任务"""
        import os
        import logging

        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)

        start_time = time.time()
        task_id = task_data.get("task_id", f"trans_{uuid.uuid4().hex[:8]}")

        logger.info(f"[Transport] 开始执行任务 {task_id}")

        # 提取任务参数
        from_location = task_data.get("from_location", {})
        to_location = task_data.get("to_location", {})
        mode_preference = task_data.get("mode_preference", "driving")  # walking/transit/driving

        logger.info(f"[Transport] 任务参数 - 起点: {from_location}, 终点: {to_location}, 模式: {mode_preference}")

        # 如果没有配置API密钥，返回模拟数据
        if not os.getenv("AMAP_API_KEY"):
            logger.warning("[Transport] 未配置API密钥，返回模拟数据")
            return self._get_mock_data(task_id, from_location, to_location, start_time, None)

        # 获取起点和终点的坐标或名称
        from_name = from_location.get("name", "")
        to_name = to_location.get("name", "")
        from_coords = from_location.get("coords", "")
        to_coords = to_location.get("coords", "")

        # 如果没有提供坐标，尝试通过地址获取坐标
        if not from_coords and from_name:
            logger.info(f"[Transport] 正在获取起点坐标: {from_name}")
            from_coords = await navigation_service.geocode(from_name)
            logger.info(f"[Transport] 起点坐标: {from_coords}")
        if not to_coords and to_name:
            logger.info(f"[Transport] 正在获取终点坐标: {to_name}")
            to_coords = await navigation_service.geocode(to_name)
            logger.info(f"[Transport] 终点坐标: {to_coords}")

        # 优先使用坐标，如果没有则使用名称
        origin = from_coords if from_coords else from_name
        destination = to_coords if to_coords else to_name

        # 如果无法获取坐标，返回模拟数据
        if not origin or not destination:
            logger.warning(f"[Transport] 无法获取坐标 - 起点: {origin}, 终点: {destination}")
            return self._get_mock_data(task_id, from_location, to_location, start_time, "无法获取地址坐标")

        # 调用导航API
        try:
            logger.info(f"[Transport] 调用导航API - 起点: {origin}, 终点: {destination}, 模式: {mode_preference}")
            nav_result = await navigation_service.get_direction(
                origin=origin,
                destination=destination,
                mode=mode_preference
            )
            logger.info(f"[Transport] API返回结果: {nav_result}")

            if nav_result['status'] == 'success':
                route_data = nav_result['data']

                # 构建交通方案
                transport_option = {
                    "transport_id": f"trans_{uuid.uuid4().hex[:8]}",
                    "type": mode_preference,
                    "from": from_name,
                    "to": to_name,
                    "distance": route_data['distance'],
                    "distance_text": navigation_service.format_distance(route_data['distance']),
                    "duration": route_data['duration'],
                    "duration_text": navigation_service.format_duration(route_data['duration']),
                    "steps": route_data['steps'],
                    "polyline": route_data.get('polyline', '')
                }

                processing_time = (time.time() - start_time) * 1000

                return {
                    "task_id": task_id,
                    "status": "success",
                    "data": {
                        "items": [transport_option],
                    },
                    "metadata": {
                        "processing_time_ms": processing_time,
                        "source": "api_generated",
                        "model_used": "amap_navigation",
                        "over_budget": False
                    },
                    "error_message": None
                }
            else:
                # API调用失败，返回模拟数据
                return self._get_mock_data(task_id, from_location, to_location, start_time, nav_result.get('message', '未知错误'))

        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            return {
                "task_id": task_id,
                "status": "failed",
                "data": {"items": []},
                "metadata": {
                    "processing_time_ms": processing_time,
                    "source": "api_generated",
                    "model_used": "amap_navigation",
                    "over_budget": False
                },
                "error_message": str(e)
            }

    def _get_mock_data(self, task_id: str, from_location: Dict[str, Any], 
                       to_location: Dict[str, Any], start_time: float, 
                       error_msg: Optional[str] = None) -> Dict[str, Any]:
        """返回模拟数据"""
        from_name = from_location.get("name", "起点")
        to_name = to_location.get("name", "终点")

        mock_option = {
            "transport_id": f"trans_{uuid.uuid4().hex[:8]}",
            "type": "driving",
            "from": from_name,
            "to": to_name,
            "distance": 5000,
            "distance_text": "5.0公里",
            "duration": 900,
            "duration_text": "15分钟",
            "steps": [
                {
                    "instruction": f"从{from_name}出发",
                    "distance": 5000,
                    "duration": 900,
                    "polyline": ""
                }
            ],
            "polyline": ""
        }

        processing_time = (time.time() - start_time) * 1000

        return {
            "task_id": task_id,
            "status": "success",
            "data": {
                "items": [mock_option]
            },
            "metadata": {
                "processing_time_ms": processing_time,
                "source": "mock_data",
                "model_used": None,
                "over_budget": False
            },
            "error_message": error_msg
        }
