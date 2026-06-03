"""行程整合相关路由 - 将各智能体输出拼接为每日行程"""
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from fastapi import APIRouter
from src.models.response import success_response, error_response

router = APIRouter(prefix="/api/v1/integration", tags=["行程整合"])


# ============== 核心整合逻辑 ==============

def calculate_route_optimization(attractions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    基础路线优化算法：根据景点位置排序，避免折返
    
    Args:
        attractions: 景点列表，每个景点包含 location {lat, lng}
    
    Returns:
        优化后的景点列表（按地理位置就近排序）
    """
    if not attractions or len(attractions) <= 1:
        return attractions
    
    # 过滤掉非字典类型的元素
    valid_attractions = [a for a in attractions if isinstance(a, dict)]
    
    # 简化版：按纬度排序（实际应使用更复杂的路径规划算法）
    sorted_attractions = sorted(
        valid_attractions, 
        key=lambda x: x.get("location", {}).get("lat", 0) if isinstance(x.get("location"), dict) else 0
    )
    
    return sorted_attractions


def estimate_transport_time(from_loc: Dict, to_loc: Dict) -> int:
    """
    估算两点之间的交通时间（分钟）
    根据坐标计算直线距离来估算
    
    Args:
        from_loc: 起点 {name, lat, lng}
        to_loc: 终点 {name, lat, lng}
    
    Returns:
        预计交通时间（分钟）
    """
    import math
    
    if not from_loc or not to_loc:
        return 30  # 默认30分钟
    
    # 如果两个地点都有坐标，计算直线距离
    if isinstance(from_loc, dict) and isinstance(to_loc, dict):
        from_lat = from_loc.get("lat", 0)
        from_lng = from_loc.get("lng", 0)
        to_lat = to_loc.get("lat", 0)
        to_lng = to_loc.get("lng", 0)

        if all(v is not None for v in [from_lat, from_lng, to_lat, to_lng]):
            # 简化版 Haversine 公式计算两点距离
            R = 6371  # 地球半径 km
            dlat = math.radians(float(to_lat) - float(from_lat))
            dlng = math.radians(float(to_lng) - float(from_lng))
            a = math.sin(dlat/2)**2 + math.cos(math.radians(float(from_lat))) * math.cos(math.radians(float(to_lat))) * math.sin(dlng/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            distance_km = R * c
            
            # 按公交速度（20km/h）估算时间
            estimated_minutes = int((distance_km / 20) * 60)
            return max(estimated_minutes, 5)  # 至少5分钟
    
    # 没有坐标时，根据名称做简单判断
    if isinstance(from_loc, str):
        from_name = from_loc
    else:
        from_name = from_loc.get("name", "") if from_loc else ""

    if isinstance(to_loc, str):
        to_name = to_loc
    else:
        to_name = to_loc.get("name", "") if to_loc else ""
    
    if from_name == to_name or from_name in to_name or to_name in from_name:
        return 15
    
    return 30

def integrate_agent_results_to_daily_plans(
    agent_results: Dict[str, Any],
    structured_requirement: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    将各智能体的输出整合为每日行程
    
    Args:
        agent_results: {
            "attraction": {"attractions": [...]},
            "accommodation": {"hotels": [...]},
            "food": {"restaurants": [...]},
            "transport": {"transport_options": [...]}
        }
        structured_requirement: 结构化需求对象
    
    Returns:
        day_plans列表，每个元素包含:
        - day: 第几天
        - date: 日期字符串
        - attractions: 当天景点列表
        - meals: 当天餐饮列表
        - transport: 交通信息
        - hotel: 住宿信息（仅第一天或换酒店时）
        - daily_cost: 当日总花费
    """
        # 提取基本信息
    travel_days = structured_requirement.get("travel_days", 1)
    travel_date_str = structured_requirement.get("travel_date", datetime.now().strftime("%Y-%m-%d"))
    traveler_count = structured_requirement.get("traveler_count", 1)
    city_name = structured_requirement.get("city_name", "")
    
    # 解析起始日期
    try:
        start_date = datetime.strptime(travel_date_str, "%Y-%m-%d")
    except:
        start_date = datetime.now()
    
    # 提取各智能体数据
    attractions_data = agent_results.get("attraction", {}).get("attractions", [])
    hotels_data = agent_results.get("accommodation", {}).get("hotels", [])
    restaurants_data = agent_results.get("food", {}).get("restaurants", [])
    transport_data = agent_results.get("transport", {}).get("transport_options", [])
    # 也支持直接从 items 中读取（兼容transport_agent原始返回格式）
    if not transport_data:
        transport_data = agent_results.get("transport", {}).get("items", [])

    # ========== 统一标准化所有 location 字段为 {lat, lng} 对象格式 ==========
    def _normalize_location(item: dict) -> None:
        """将 item 中的 location 统一转为 {lat, lng} 对象格式"""
        if not isinstance(item, dict):
            return
        loc = item.get("location")
        if loc is None:
            # 尝试从 address 猜坐标（无法猜，留空）
            return
        if isinstance(loc, str):
            # 字符串格式 "lat,lng" 或纯地址
            if "," in loc and len(loc.split(",")) == 2:
                try:
                    parts = loc.split(",")
                    lat, lng = float(parts[0].strip()), float(parts[1].strip())
                    item["location"] = {"lat": lat, "lng": lng}
                except (ValueError, TypeError):
                    # 无法解析为数字，把字符串当地址处理
                    if not item.get("address"):
                        item["address"] = loc
                    item["location"] = None
            else:
                # 纯地址字符串，挪到 address 字段
                if not item.get("address"):
                    item["address"] = loc
                item["location"] = None
        elif isinstance(loc, dict):
            # 已经是 dict，确保有 lat/lng 键
            if "lat" not in loc and "latitude" in loc:
                loc["lat"] = loc.pop("latitude")
            if "lng" not in loc and "longitude" in loc:
                loc["lng"] = loc.pop("longitude")
            if "lon" in loc and "lng" not in loc:
                loc["lng"] = loc.pop("lon")
            # 确保 lat/lng 是数字
            for key in ("lat", "lng"):
                if key in loc and not isinstance(loc[key], (int, float)):
                    try:
                        loc[key] = float(loc[key])
                    except (ValueError, TypeError):
                        loc[key] = 0

    for attraction in attractions_data:
        _normalize_location(attraction)
    for hotel in hotels_data:
        _normalize_location(hotel)
    for restaurant in restaurants_data:
        _normalize_location(restaurant)
    for transport in transport_data:
        _normalize_location(transport)


    # 为景点数据添加city_name字段
    for attraction in attractions_data:
        if "city_name" not in attraction:
            attraction["city_name"] = city_name

    # 为酒店数据添加city_name字段
    for hotel in hotels_data:
        if "city_name" not in hotel:
            hotel["city_name"] = city_name

    # 为餐厅数据添加city_name字段
    for restaurant in restaurants_data:
        if "city_name" not in restaurant:
            restaurant["city_name"] = city_name
    
    # 对景点进行路线优化
    optimized_attractions = calculate_route_optimization(attractions_data)
    
        # 按时间段分组景点（morning/afternoon/evening）
    morning_attractions = [a for a in optimized_attractions if isinstance(a, dict) and a.get("visit_time_slot") == "morning"]
    afternoon_attractions = [a for a in optimized_attractions if isinstance(a, dict) and a.get("visit_time_slot") == "afternoon"]
    evening_attractions = [a for a in optimized_attractions if isinstance(a, dict) and a.get("visit_time_slot") == "evening"]
    
    total_slots = travel_days * 3  # 每天3个时间段
    total_attractions = len(morning_attractions) + len(afternoon_attractions) + len(evening_attractions)
    
    # 如果景点总数 <= 时间段总数，按正常分配
    # 否则按比例压缩
    attractions_per_day = {
        "morning": max(1, len(morning_attractions) // travel_days) if morning_attractions else 0,
        "afternoon": max(1, len(afternoon_attractions) // travel_days) if afternoon_attractions else 0,
        "evening": max(1, len(evening_attractions) // travel_days) if evening_attractions else 0
    }
    
    # 防止索引越界：确保总分配数不超过实际景点数
    def cap_indices(slot_attractions, per_day):
        if per_day == 0:
            return 0
        total_needed = per_day * travel_days
        if total_needed > len(slot_attractions):
            return max(1, len(slot_attractions) // travel_days)
        return per_day
    
    attraction_indices = {
        "morning": 0,
        "afternoon": 0,
        "evening": 0
    }
    
    day_plans = []
    
    for day in range(1, travel_days + 1):
        # 计算当天日期
        current_date = start_date + timedelta(days=day - 1)
        date_str = current_date.strftime("%Y-%m-%d")
        
        # 分配当天的景点（按时间段分配，避免时间冲突）
        day_attractions = []
        
        # 上午景点（09:00-11:30）
        for i in range(attractions_per_day["morning"]):
            if attraction_indices["morning"] < len(morning_attractions):
                attraction = morning_attractions[attraction_indices["morning"]].copy()
                attraction["visit_time"] = "上午"
                attraction["start_time"] = "09:00"
                attraction["end_time"] = "11:30"
                attraction["visit_duration"] = "2.5小时"
                day_attractions.append(attraction)
                attraction_indices["morning"] += 1
        
        # 下午景点（14:00-16:30）
        for i in range(attractions_per_day["afternoon"]):
            if attraction_indices["afternoon"] < len(afternoon_attractions):
                attraction = afternoon_attractions[attraction_indices["afternoon"]].copy()
                attraction["visit_time"] = "下午"
                attraction["start_time"] = "14:00"
                attraction["end_time"] = "16:30"
                attraction["visit_duration"] = "2.5小时"
                day_attractions.append(attraction)
                attraction_indices["afternoon"] += 1
        
        # 晚上景点（18:30-20:00）
        for i in range(attractions_per_day["evening"]):
            if attraction_indices["evening"] < len(evening_attractions):
                attraction = evening_attractions[attraction_indices["evening"]].copy()
                attraction["visit_time"] = "晚上"
                attraction["start_time"] = "18:30"
                attraction["end_time"] = "20:00"
                attraction["visit_duration"] = "1.5小时"
                day_attractions.append(attraction)
                attraction_indices["evening"] += 1
        
        # 安排餐饮（早中晚三餐，时间与景点错开）
        day_meals = []
        meal_schedule = [
            {"meal_type": "breakfast", "meal_time": "早上", "time": "07:30", "duration": "30分钟"},
            {"meal_type": "lunch", "meal_time": "中午", "time": "12:00", "duration": "1小时"},
            {"meal_type": "dinner", "meal_time": "晚上", "time": "17:00", "duration": "1小时"}
        ]
        
        for meal_idx, meal_info in enumerate(meal_schedule):
            # 从餐厅列表中选择一个（简化：循环选择）
            if restaurants_data:
                # 使用取模运算确保索引不越界
                restaurant_index = ((day - 1) * 3 + meal_idx) % len(restaurants_data)
                restaurant = restaurants_data[restaurant_index].copy()
                restaurant["meal_type"] = meal_info["meal_type"]
                restaurant["meal_time"] = meal_info["meal_time"]
                restaurant["time"] = meal_info["time"]
                restaurant["start_time"] = meal_info["time"]
                restaurant["duration"] = meal_info["duration"]
                
                # 设置结束时间
                if meal_info["meal_type"] == "breakfast":
                    restaurant["end_time"] = "08:00"
                elif meal_info["meal_type"] == "lunch":
                    restaurant["end_time"] = "13:00"
                else:  # dinner
                    restaurant["end_time"] = "18:00"
                
                day_meals.append(restaurant)
        
        # 添加交通信息（景点之间）
        day_transport = None
        if len(day_attractions) >= 2:
            # 计算第一个景点到第二个景点的交通
            from_attr = day_attractions[0]
            to_attr = day_attractions[1]
            
            transport_time = estimate_transport_time(
                from_attr.get("location", {}),
                to_attr.get("location", {})
            )
            
            from_loc = from_attr.get("location", {})
            to_loc = to_attr.get("location", {})
            has_from_coords = isinstance(from_loc, dict) and from_loc.get("lat") is not None and from_loc.get("lng") is not None
            has_to_coords = isinstance(to_loc, dict) and to_loc.get("lat") is not None and to_loc.get("lng") is not None
            
            # 根据估算的交通时间推算距离（公交平均速度20km/h）
            estimated_distance_m = int((transport_time / 60) * 20000)
            estimated_distance_km = estimated_distance_m / 1000
            
                        # 如果有坐标，生成一条直线 polyline（供前端地图直接绘制）
            polyline_str = ""
            if has_from_coords and has_to_coords:
                # 在两个坐标之间取10个插值点，生成高德格式的 polyline
                steps_count = 10
                lat_step = (to_loc["lat"] - from_loc["lat"]) / steps_count
                lng_step = (to_loc["lng"] - from_loc["lng"]) / steps_count
                points = []
                for i in range(steps_count + 1):
                    points.append(f"{from_loc['lng'] + lng_step * i},{from_loc['lat'] + lat_step * i}")
                polyline_str = ";".join(points)
            
            # 生成简要步骤
            steps = []
            if from_attr.get("name") and to_attr.get("name"):
                steps.append({
                    "instruction": f"从{from_attr['name']}出发",
                    "distance": estimated_distance_m,
                    "duration": transport_time * 60,
                    "polyline": polyline_str
                })
                steps.append({
                    "instruction": f"到达{to_attr['name']}",
                    "distance": 0,
                    "duration": 0,
                    "polyline": ""
                })
            
                        # 生成高德格式的 polyline 直线路径（lng1,lat1;lng2,lat2;...）
            polyline_str = ""
            if has_from_coords and has_to_coords:
                interpolate_count = 10
                lat_step = (to_loc["lat"] - from_loc["lat"]) / interpolate_count
                lng_step = (to_loc["lng"] - from_loc["lng"]) / interpolate_count
                points = []
                for i in range(interpolate_count + 1):
                    points.append(f"{from_loc['lng'] + lng_step * i},{from_loc['lat'] + lat_step * i}")
                polyline_str = ";".join(points)
            
            # 生成简要步骤（供前端文字导航显示）
            steps = []
            if from_attr.get("name") and to_attr.get("name"):
                steps.append({
                    "instruction": f"从{from_attr['name']}出发",
                    "distance": estimated_distance_m,
                    "duration": transport_time * 60,
                    "polyline": polyline_str
                })
                steps.append({
                    "instruction": f"到达{to_attr['name']}",
                    "distance": 0,
                    "duration": 0,
                    "polyline": ""
                })
            
            # 直接根据景点坐标生成交通信息
            day_transport = {
                "transport_id": f"trans_{uuid.uuid4().hex[:8]}",
                "from": from_attr.get("name", ""),
                "to": to_attr.get("name", ""),
                "type": "transit",
                "duration": transport_time,
                "duration_text": f"{transport_time}分钟",
                "distance": estimated_distance_m,
                "distance_text": f"{estimated_distance_km:.1f}公里",
                "price": 5.0,
                "departure_time": "11:30",
                "steps": steps,
                "polyline": polyline_str,
                "from_location": from_loc if has_from_coords else {},
                "to_location": to_loc if has_to_coords else {}
            }
            # 如果 transport_data 中有精确匹配的交通数据，则用来覆盖
            if transport_data:
                for transport in transport_data:
                    transport_from = transport.get("from", "")
                    transport_to = transport.get("to", "")
                    from_name = from_attr.get("name", "")
                    to_name = to_attr.get("name", "")
                    if transport_from == from_name and transport_to == to_name:
                        merged = transport.copy()
                        # 确保坐标信息不被覆盖
                        if not merged.get("from_location") or merged.get("from_location") == {}:
                            merged["from_location"] = from_loc if has_from_coords else {}
                        if not merged.get("to_location") or merged.get("to_location") == {}:
                            merged["to_location"] = to_loc if has_to_coords else {}
                        day_transport = merged
                        break
        # 添加住宿信息（仅第一天或需要换酒店时）
        day_hotel = None
        if day == 1 and hotels_data:
            day_hotel = hotels_data[0].copy()
            day_hotel["check_in_date"] = date_str
        
        # 计算当日花费
        daily_cost = 0
        for attr in day_attractions:
            daily_cost += attr.get("ticket_price", 0) * traveler_count
        for meal in day_meals:
            daily_cost += meal.get("avg_price", 0) * traveler_count
        if day_transport:
            daily_cost += day_transport.get("price", 0) * traveler_count
        if day_hotel:
            daily_cost += day_hotel.get("price_per_night", 0)
        
        # 构建当日行程
        day_plan = {
            "day": day,
            "date": date_str,
            "attractions": day_attractions,
            "meals": day_meals,
            "transport": day_transport,
            "hotel": day_hotel,
            "daily_cost": round(daily_cost, 2),
            "notes": f"第{day}天行程安排"
        }
        
        day_plans.append(day_plan)
    
    return day_plans


# ============== API 路由 ==============

@router.post("/combine")
async def combine_itinerary(request_data: Dict[str, Any]):
    """
    行程整合接口：将各智能体的输出拼接为每日行程
    
    请求参数:
    {
        "task_id": "xxx",
        "agent_results": {
            "attraction": {"attractions": [...]},
            "accommodation": {"hotels": [...]},
            "food": {"restaurants": [...]},
            "transport": {"transport_options": [...]}
        },
        "structured_requirement": {...}
    }
    
    响应:
    {
        "code": 200,
        "msg": "行程整合成功",
        "data": {
            "task_id": "xxx",
            "day_plans": [...],
            "validation": {...}
        }
    }
    """
    # 1. 提取参数
    task_id = request_data.get("task_id")
    agent_results = request_data.get("agent_results")
    structured_req = request_data.get("structured_requirement")
    
    if not agent_results or not structured_req:
        return error_response(code=400, msg="缺少必要参数：agent_results 或 structured_requirement")
    
    # 验证必填字段
    required_fields = ["city_name", "travel_days", "travel_date", "traveler_count"]
    for field in required_fields:
        if field not in structured_req:
            return error_response(code=400, msg=f"结构化需求缺少必填字段：{field}")
    
    # 2. 整合为每日行程
    try:
        day_plans = integrate_agent_results_to_daily_plans(agent_results, structured_req)
        
         # 3. 调用校验接口
        from src.routes.validate import check_itinerary_conflicts
        validation_result = check_itinerary_conflicts(day_plans, structured_req)

        # =====  4. 如果有严重冲突，自动触发协商修复 =====
        has_error = any(c.get("severity") == "error" for c in validation_result.get("conflicts", []))
        negotiation_result = None
        if has_error:
            try:
                from src.services.negotiation_service import negotiate_and_fix
                # 收集备选数据
                backup = {
                    "attractions": agent_results.get("attraction", {}).get("attractions", [])
                }
                negotiation_result = await negotiate_and_fix(
                    day_plans=day_plans,
                    structured_requirement=structured_req,
                    backup_data=backup,
                    max_iterations=5
                )
                day_plans = negotiation_result["day_plans"]
                validation_result = negotiation_result["validation"]
            except Exception as e:
                print(f"[Integration] 协商修复失败，使用原行程: {e}")

        # ===== 5. 如果启用真实路线优化 =====
        # （可以在请求参数中增加 use_real_traffic 字段来控制）
        if request_data.get("use_real_traffic") and request_data.get("optimize_route"):
            try:
                from src.services.negotiation_service import optimize_real_route
                for i, plan in enumerate(day_plans):
                    day_plans[i] = await optimize_real_route(plan, mode="transit")
            except Exception as e:
                print(f"[Integration] 真实路线优化失败: {e}")

        # ===== 6. 汇总总花费 =====
        total_cost = sum(dp.get("daily_cost", 0) for dp in day_plans)

        # ===== 7. 返回结果 =====
        return success_response(
            data={
                "day_plans": day_plans,
                "validation": validation_result,
                "total_cost": total_cost,
                "negotiation": {
                    "applied": negotiation_result is not None,
                    "iteration_count": (negotiation_result or {}).get("iteration_count", 0),
                    "fully_resolved": (negotiation_result or {}).get("fully_resolved", True),
                    "log": (negotiation_result or {}).get("negotiation_log", [])
                } if negotiation_result else None
            },
            msg="行程整合成功"
        )
    except Exception as e:
        return error_response(code=500, msg=f"行程整合失败: {str(e)}")


@router.post("/optimize-route")
async def optimize_route(request_data: Dict[str, Any]):
    """
    路线优化接口：对给定景点列表进行路径优化
    
    请求参数:
    {
        "attractions": [
            {"name": "故宫", "location": {"lat": 39.916, "lng": 116.397}},
            ...
        ]
    }
    """
    attractions = request_data.get("attractions", [])
    
    if not attractions:
        return error_response(code=400, msg="缺少景点数据")
    
    try:
        optimized = calculate_route_optimization(attractions)
        return success_response(
            data={"optimized_attractions": optimized},
            msg="路线优化完成"
        )
    except Exception as e:
        return error_response(code=500, msg=f"路线优化失败: {str(e)}")
