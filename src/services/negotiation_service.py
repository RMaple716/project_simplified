"""
协商智能体服务 - 协调层核心引擎

功能:
1. 冲突检测后的自动协商修复（5种策略）
2. 多轮迭代优化（修复→校验→再修复→再校验）
3. 接入高德地图API的真实路线优化（贪心最近邻算法）

使用方式:
    from src.services.negotiation_service import full_negotiation_pipeline

    result = await full_negotiation_pipeline(
        agent_results=agent_results,
        structured_requirement=structured_req,
        optimize_route=True,
        use_real_traffic=False  # 设为True需配置AMAP_API_KEY
    )
"""
import copy
import math
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ==================== 1. 时间工具函数 ====================

def parse_time_to_minutes(time_str: str) -> int:
    """解析时间字符串为分钟数（0点起）"""
    time_slots = {
        "morning": 540, "afternoon": 840, "evening": 1080,
        "上午": 540, "中午": 720, "下午": 840, "晚上": 1080,
    }
    if not time_str:
        return 540
    lower = time_str.lower()
    if lower in time_slots:
        return time_slots[lower]
    try:
        parts = time_str.split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except:
        pass
    return 540


def minutes_to_time_str(minutes: int) -> str:
    """将分钟数转换为 HH:MM 格式"""
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def parse_duration_to_minutes(dur: str) -> int:
    """解析时长字符串为分钟数"""
    if not dur:
        return 120
    if "-" in dur and "小时" in dur:
        try:
            parts = dur.replace("小时", "").split("-")
            return int((float(parts[0]) + float(parts[1])) / 2 * 60)
        except:
            pass
    if "小时" in dur:
        try:
            return int(float(dur.replace("小时", "")) * 60)
        except:
            pass
    if "分钟" in dur:
        try:
            return int(dur.replace("分钟", ""))
        except:
            pass
    return 120


def check_overlap(s1: int, e1: int, s2: int, e2: int) -> bool:
    """两个时间区间是否重叠"""
    return s1 < e2 and s2 < e1


# ==================== 2. 交通时间查询 ====================

async def get_real_transport_time(
    from_location:Dict[str, Any],
    to_location: Dict[str, Any],
    mode: str = "transit"
) -> Tuple[int, str]:
    """
    调用高德地图API获取两点间真实交通耗时（替代原有的简化估算）

    Args:
        from_location: {"lat": float, "lng": float}
        to_location: {"lat": float, "lng": float}
        mode: walking/driving/transit

    Returns:
        (duration_minutes, polyline)
    """
    if not from_location or not to_location:
        return (30, "")

    # 提取坐标值，用 get 获取并用 float() 确保类型安全
    from_lat = from_location.get("lat") or from_location.get("latitude")
    from_lng = from_location.get("lng") or from_location.get("longitude") or from_location.get("lon")
    to_lat = to_location.get("lat") or to_location.get("latitude")
    to_lng = to_location.get("lng") or to_location.get("longitude") or to_location.get("lon")

    # 如果任何坐标为 None，提前返回
    if None in (from_lat, from_lng, to_lat, to_lng):
        return (30, "")

    # 显式转换为 float，消除 Pylance 的 "Unknown | None" 类型警告
    assert from_lat is not None and from_lng is not None
    assert to_lat is not None and to_lng is not None
    from_lat_f: float = float(from_lat)
    from_lng_f: float = float(from_lng)
    to_lat_f: float = float(to_lat)
    to_lng_f: float = float(to_lng)

    try:
        from src.services.navigation_service import NavigationService
        nav = NavigationService()
        origin = f"{from_lng_f},{from_lat_f}"
        destination = f"{to_lng_f},{to_lat_f}"
        result = await nav.get_direction(origin, destination, mode=mode)
        if result["status"] == "success":
            data = result["data"]
            duration_seconds = data.get("duration", 0) or 0
            minutes = max(1, duration_seconds // 60)
            polyline = data.get("polyline", "")
            return (minutes, polyline)
    except Exception as e:
        logger.warning(f"[协商] 获取真实交通耗时失败: {e}")

    # fallback: Haversine公式直线距离估算（25km/h公交速度）
    R = 6371
    dlat = math.radians(to_lat_f - from_lat_f)
    dlng = math.radians(to_lng_f - from_lng_f)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(from_lat_f)) * \
        math.cos(math.radians(to_lat_f)) * math.sin(dlng/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    dist_km = R * c
    minutes = max(5, int((dist_km / 25) * 60))
    return (minutes, "")


# ==================== 3. 五大协商修复策略 ====================

def strategy_time_shift(
    day_plan: dict,
    conflict: dict,
    margin: int = 15
) -> Optional[dict]:
    """
    【策略1】时间平移 - 将冲突活动前后偏移，重新编排当天时间线

    工作原理:
      1. 收集当天所有活动（景点、餐饮、交通）
      2. 按原顺序重新分配时间，每个活动之间保留margin分钟间隔
      3. 如果平移后超出22:00则放弃

    Args:
        day_plan: 当日行程
        conflict: 冲突信息 {activities: [name1, name2]}
        margin: 活动间最小间隔（分钟）

    Returns:
        修复后的 day_plan，或 None（无法修复）
    """
    plan = copy.deepcopy(day_plan)
    all_items = []
    conflict_names = set(conflict.get("activities", []))

    # 收集所有活动
    for attr in plan.get("attractions", []):
        all_items.append({"type": "attraction", "data": attr})
    for meal in plan.get("meals", []):
        all_items.append({"type": "meal", "data": meal})
    if plan.get("transport"):
        all_items.append({"type": "transport", "data": plan["transport"]})

    if len(all_items) < 2:
        return None

    # 为每个活动计算起止时间（分钟）
    for item in all_items:
        data = item["data"]
        start_str = data.get("start_time") or data.get("time") or "09:00"
        dur_str = data.get("duration") or data.get("visit_duration") or "2小时"
        start_m = parse_time_to_minutes(start_str)
        dur_m = parse_duration_to_minutes(dur_str)
        data["_start_m"] = start_m
        data["_end_m"] = start_m + dur_m

    # 按原顺序重新分配时间
    current = all_items[0]["data"]["_start_m"]
    for i, item in enumerate(all_items):
        data = item["data"]
        dur_m = data["_end_m"] - data["_start_m"]
        if i > 0:
            current = max(current, all_items[i-1]["data"]["_end_m"] + margin)
        data["_new_start"] = current
        data["_new_end"] = current + dur_m
        current = data["_new_end"]

    # 检查是否超出22:00
    if all_items and all_items[-1]["data"]["_new_end"] > 1320:
        return None

    # 应用新时间到活动数据
    for item in all_items:
        data = item["data"]
        data["start_time"] = minutes_to_time_str(data["_new_start"])
        data["end_time"] = minutes_to_time_str(data["_new_end"])
        # 清理临时字段
        for key in ("_start_m", "_end_m", "_new_start", "_new_end"):
            data.pop(key, None)

    # 重建 day_plan
    plan["attractions"] = [it["data"] for it in all_items if it["type"] == "attraction"]
    plan["meals"] = [it["data"] for it in all_items if it["type"] == "meal"]
    plan["transport"] = next(
        (it["data"] for it in all_items if it["type"] == "transport"), None
    )

    return plan


def strategy_swap_time_slot(day_plan: dict, conflict: dict) -> Optional[dict]:
    """
    【策略2】时段交换 - 交换冲突活动的时间段

    场景示例:
      故宫(09:00-12:00) 与 午餐(11:30-12:30) 冲突
      → 将故宫改为下午(14:00-16:30)，午餐维持11:30
      或者
      → 将午餐推迟到12:30，故宫维持不变

    Args:
        day_plan: 当日行程
        conflict: 冲突信息

    Returns:
        修复后的 day_plan，或 None
    """
    plan = copy.deepcopy(day_plan)
    conflict_names = set(conflict.get("activities", []))

    # 处理景点：交换上午↔下午时间段
    for attr in plan.get("attractions", []):
        name = attr.get("name", "")
        if name in conflict_names:
            current_slot = attr.get("visit_time_slot", "").lower()
            if current_slot in ("morning", "上午"):
                attr["visit_time_slot"] = "afternoon"
                attr["start_time"] = "14:00"
                attr["end_time"] = "16:30"
                attr["visit_time"] = "下午"
                logger.info(f"[协商] 策略2: '{name}' 上午→下午")
            elif current_slot in ("afternoon", "下午"):
                attr["visit_time_slot"] = "morning"
                attr["start_time"] = "09:00"
                attr["end_time"] = "11:30"
                attr["visit_time"] = "上午"
                logger.info(f"[协商] 策略2: '{name}' 下午→上午")

    # 处理餐饮：推迟到安全时间
    for meal in plan.get("meals", []):
        name = meal.get("name", "")
        if name in conflict_names:
            meal_type = meal.get("meal_type", "").lower()
            if meal_type in ("lunch",) or "午餐" in name:
                meal["start_time"] = "12:30"
                meal["end_time"] = "13:30"
                meal["time"] = "12:30"
                logger.info(f"[协商] 策略2: 午餐'{name}' 推迟到12:30")
            elif meal_type in ("dinner",) or "晚餐" in name:
                meal["start_time"] = "17:30"
                meal["end_time"] = "18:30"
                meal["time"] = "17:30"
                logger.info(f"[协商] 策略2: 晚餐'{name}' 推迟到17:30")

    return plan


def strategy_compress_duration(day_plan: dict, conflict: dict) -> Optional[dict]:
    """
    【策略3】时长压缩 - 缩短冲突活动的游览时长

    规则: 仅当原时长>45分钟时才压缩，压缩到45分钟（不低于最低阈值）
    餐饮不压缩（吃饭时间不宜过短）
    """
    plan = copy.deepcopy(day_plan)
    conflict_names = set(conflict.get("activities", []))

    for attr in plan.get("attractions", []):
        name = attr.get("name", "")
        if name in conflict_names:
            dur_str = attr.get("duration") or attr.get("visit_duration") or "2小时"
            dur_m = parse_duration_to_minutes(dur_str)
            if dur_m > 45:
                new_dur = "45分钟"
                attr["duration"] = new_dur
                attr["visit_duration"] = new_dur
                start_s = attr.get("start_time") or attr.get("visit_time") or "09:00"
                start_m = parse_time_to_minutes(start_s)
                attr["end_time"] = minutes_to_time_str(start_m + 45)
                logger.info(f"[协商] 策略3: '{name}' 压缩 {dur_str} → 45分钟")
                return plan

    return None


def strategy_replace_activity(
    day_plan: dict,
    conflict: dict,
    backup_attractions: Optional[List[dict]] = None
) -> Optional[dict]:
    """
    【策略4】活动替换 - 用备选景点替换冲突景点

    需要景点智能体返回了多于所需数量的景点，多出的作为备选。
    替换时保持原时间槽不变。
    """
    if not backup_attractions:
        return None

    plan = copy.deepcopy(day_plan)
    conflict_names = set(conflict.get("activities", []))

    for i, attr in enumerate(plan.get("attractions", [])):
        name = attr.get("name", "")
        if name in conflict_names and backup_attractions:
            replacement = copy.deepcopy(backup_attractions.pop(0))
            replacement["start_time"] = attr.get("start_time", "09:00")
            replacement["end_time"] = attr.get("end_time", "11:30")
            replacement["visit_time"] = attr.get("visit_time", "上午")
            replacement["visit_time_slot"] = attr.get("visit_time_slot", "morning")
            logger.info(f"[协商] 策略4: '{name}' → '{replacement.get('name', '')}'")
            plan["attractions"][i] = replacement
            return plan

    return None


def strategy_cross_day_move(
    day_plans: List[dict],
    conflict: dict
) -> Optional[List[dict]]:
    """
    【策略5】跨天移动 - 将冲突活动移动到另一天（如果有多天行程）

    适用场景: 某天有5个景点装不下，另一天只有1个景点太空
    """
    plans = copy.deepcopy(day_plans)
    if len(plans) <= 1:
        return None

    conflict_names = set(conflict.get("activities", []))

    for day_idx, plan in enumerate(plans):
        for i, attr in enumerate(plan.get("attractions", [])):
            name = attr.get("name", "")
            if name in conflict_names:
                # 找活动最少的一天移动过去
                min_day_idx = min(
                    range(len(plans)),
                    key=lambda x: len(plans[x].get("attractions", []))
                )
                if min_day_idx == day_idx:
                    # 找第二少的
                    sorted_days = sorted(
                        range(len(plans)),
                        key=lambda x: len(plans[x].get("attractions", []))
                    )
                    min_day_idx = sorted_days[1] if len(sorted_days) > 1 else None
                if min_day_idx is not None and min_day_idx != day_idx:
                    moved = plans[day_idx]["attractions"].pop(i)
                    plans[min_day_idx]["attractions"].append(moved)
                    logger.info(
                        f"[协商] 策略5: '{name}' 第{day_idx+1}天 → 第{min_day_idx+1}天"
                    )
                    return plans

    return None


# ==================== 4. 真实路线优化引擎 ====================

async def optimize_real_route(
    day_plan: dict,
    mode: str = "transit"
) -> dict:
    """
    基于真实交通数据的路线优化

    算法: 贪心最近邻（Greedy Nearest Neighbor）
    1. 用高德地图API查询所有景点对间的真实交通耗时，构建耗时矩阵
    2. 从第一个景点出发，每次选择最近的未访问景点
    3. 根据最优顺序更新各景点的起止时间和交通段信息

    Args:
        day_plan: 当日行程
        mode: 交通模式 walking/driving/transit

    Returns:
        优化后的 day_plan
    """
    plan = copy.deepcopy(day_plan)
    attractions = plan.get("attractions", [])
    if len(attractions) <= 1:
        return plan

    n = len(attractions)
    logger.info(f"[协商] 真实路线优化: {n}个景点")

    # 构建耗时矩阵和polyline矩阵
    travel_matrix = [[0] * n for _ in range(n)]
    polyline_matrix = [[""] * n for _ in range(n)]

    for i in range(n):
        for j in range(i + 1, n):
            loc_i = attractions[i].get("location", {})
            loc_j = attractions[j].get("location", {})
            dur, poly = await get_real_transport_time(loc_i, loc_j, mode)
            travel_matrix[i][j] = dur
            travel_matrix[j][i] = dur
            polyline_matrix[i][j] = poly
            polyline_matrix[j][i] = poly
            logger.info(f"[协商]   {attractions[i]['name']}↔{attractions[j]['name']}: {dur}分钟")

    # 贪心最近邻算法
    ordered = [0]
    remaining = set(range(1, n))
    while remaining:
        last = ordered[-1]
        nearest = min(remaining, key=lambda x: travel_matrix[last][x])
        ordered.append(nearest)
        remaining.remove(nearest)

    # 重新排序景点
    new_attractions = [attractions[i] for i in ordered]
    plan["attractions"] = new_attractions

    # 计算总交通耗时
    total_traffic_dur = sum(
        travel_matrix[ordered[i]][ordered[i+1]] for i in range(n-1)
    ) if n >= 2 else 0

    # 更新时间分配（考虑真实交通耗时）
    first_start = parse_time_to_minutes(
        new_attractions[0].get("start_time", "09:00")
    )
    current = first_start

    for i in range(n):
        attr = new_attractions[i]
        dur_str = attr.get("duration") or attr.get("visit_duration") or "2小时"
        dur_m = parse_duration_to_minutes(dur_str)

        attr["start_time"] = minutes_to_time_str(current)
        attr["end_time"] = minutes_to_time_str(current + dur_m)
        hour = current / 60
        attr["visit_time"] = "上午" if hour < 12 else ("下午" if hour < 17 else "晚上")

        # 加上交通时间到下一个景点
        if i < n - 1:
            traffic = travel_matrix[ordered[i]][ordered[i+1]]
            current = current + dur_m + traffic
        else:
            current = current + dur_m

    # 更新交通段信息
    if n >= 2:
        first = new_attractions[0]
        second = new_attractions[1]
        first_loc = first.get("location", {})
        second_loc = second.get("location", {})

        # 收集所有路段的polyline
        all_polylines = []
        for i in range(n - 1):
            p = polyline_matrix[ordered[i]][ordered[i+1]]
            if p:
                all_polylines.append(p)

        plan["transport"] = {
            "transport_id": f"trans_real_{hash(str(ordered)) & 0xffff:04x}",
            "from": first.get("name", ""),
            "to": second.get("name", ""),
            "type": mode,
            "duration": travel_matrix[ordered[0]][ordered[1]],
            "duration_text": f"{travel_matrix[ordered[0]][ordered[1]]}分钟",
            "distance": 0,
            "price": 0,
            "departure_time": first.get("end_time", "11:30"),
            "steps": [],
            "polyline": ";".join(all_polylines) if all_polylines else "",
            "from_location": first_loc,
            "to_location": second_loc,
        }

    logger.info(f"[协商] 路线优化完成, 交通总耗时约{total_traffic_dur}分钟")
    return plan


# ==================== 5. 主协商流程 ====================

async def negotiate_and_fix(
    day_plans: List[dict],
    structured_requirement: dict,
    backup_data: Optional[dict] = None,
    max_iterations: int = 5
) -> dict:
    """
    核心协商流程：多轮迭代的冲突检测→修复→再检测→再修复

    流程:
      循环最多max_iterations次:
        1. 调用 check_itinerary_conflicts 检测冲突
        2. 如果没有严重冲突，终止
        3. 对有冲突的每一天，按优先级尝试 策略1→策略2→...→策略5
        4. 如果本轮没有修复任何冲突，提前终止

    Args:
        day_plans: 每日行程列表
        structured_requirement: 结构化需求
        backup_data: 备选景点数据 {"attractions": [...]}
        max_iterations: 最大迭代次数

    Returns:
        {
            "day_plans": 修复后的行程,
            "negotiation_log": 协商日志,
            "iteration_count": 实际迭代次数,
            "fully_resolved": bool 是否完全解决
        }
    """
    from src.routes.validate import check_itinerary_conflicts

    negotiation_log = []
    backup_attractions = list((backup_data or {}).get("attractions", []))
    current_plans = copy.deepcopy(day_plans)

    for iteration in range(max_iterations):
        logger.info(f"[协商] === 第 {iteration + 1} 轮 ===")

        validation = check_itinerary_conflicts(current_plans, structured_requirement)
        conflicts = validation.get("conflicts", [])
        has_error = any(c.get("severity") == "error" for c in conflicts)

        if not has_error:
            logger.info(f"[协商] ✓ 第{iteration + 1}轮已无严重冲突")
            negotiation_log.append({
                "iteration": iteration + 1,
                "action": "协商完成",
                "remaining_conflicts": len(conflicts),
                "all_resolved": True
            })
            return {
                "day_plans": current_plans,
                "negotiation_log": negotiation_log,
                "iteration_count": iteration + 1,
                "fully_resolved": True,
                "validation": validation
            }

        # 按天分组冲突
        day_conflicts = {}
        for c in conflicts:
            day = c.get("day", 1)
            day_conflicts.setdefault(day, []).append(c)

        any_fixed = False

        for day_num, day_conflict_list in day_conflicts.items():
            day_idx = day_num - 1
            if day_idx < 0 or day_idx >= len(current_plans):
                continue

            # 对每个冲突尝试修复策略（按优先级）
            for conflict in day_conflict_list:
                if not isinstance(conflict, dict):
                    continue
                result = strategy_time_shift(current_plans[day_idx], conflict, margin=15)
                if result:
                    current_plans[day_idx] = result
                    negotiation_log.append({
                        "iteration": iteration + 1, "day": day_num,
                        "action": "时间平移",
                        "target": conflict.get("activities", []),
                        "type": conflict.get("type")
                    })
                    any_fixed = True
                    break

                result = strategy_swap_time_slot(current_plans[day_idx], conflict)
                if result:
                    current_plans[day_idx] = result
                    negotiation_log.append({
                        "iteration": iteration + 1, "day": day_num,
                        "action": "时段交换",
                        "target": conflict.get("activities", []),
                        "type": conflict.get("type")
                    })
                    any_fixed = True
                    break

                result = strategy_compress_duration(current_plans[day_idx], conflict)
                if result:
                    current_plans[day_idx] = result
                    negotiation_log.append({
                        "iteration": iteration + 1, "day": day_num,
                        "action": "时长压缩",
                        "target": conflict.get("activities", []),
                        "type": conflict.get("type")
                    })
                    any_fixed = True
                    break

                if backup_attractions:
                    result = strategy_replace_activity(
                        current_plans[day_idx], conflict, backup_attractions
                    )
                    if result:
                        current_plans[day_idx] = result
                        negotiation_log.append({
                            "iteration": iteration + 1, "day": day_num,
                            "action": "活动替换",
                            "target": conflict.get("activities", []),
                            "type": conflict.get("type")
                        })
                        any_fixed = True
                        break

                # 跨天移动（需要多天）
                if not any_fixed and len(current_plans) > 1:
                    result = strategy_cross_day_move(current_plans, conflict)
                    if result:
                        current_plans = result
                        negotiation_log.append({
                            "iteration": iteration + 1,
                            "action": "跨天移动",
                            "target": conflict.get("activities", []),
                            "type": conflict.get("type")
                        })
                        any_fixed = True

        if not any_fixed:
            logger.warning(f"[协商] 第{iteration + 1}轮无任何修复，提前终止")
            negotiation_log.append({
                "iteration": iteration + 1,
                "action": "提前终止（无有效修复策略）"
            })
            break

        # 验证修复效果
        remaining = len(check_itinerary_conflicts(current_plans, structured_requirement)
                        .get("conflicts", []))
        logger.info(f"[协商] 第{iteration + 1}轮后剩余 {remaining} 个冲突")

    # 最终校验
    final_v = check_itinerary_conflicts(current_plans, structured_requirement)
    final_error = any(c.get("severity") == "error" for c in final_v.get("conflicts", []))

    return {
        "day_plans": current_plans,
        "negotiation_log": negotiation_log,
        "iteration_count": max_iterations,
        "fully_resolved": not final_error,
        "validation": final_v
    }


# ==================== 6. 对外入口 ====================

async def full_negotiation_pipeline(
    agent_results: dict,
    structured_requirement: dict,
    optimize_route: bool = True,
    use_real_traffic: bool = False
) -> dict:
    """
    完整协商流水线（供路由层调用的入口函数）

    流水线:
      第1步: 智能体结果整合为每日行程
      第2步: 路线优化（简版纬度排序 或 真实交通贪心算法）
      第3步: 多轮协商修复冲突
      第4步: 返回最终结果

    Args:
        agent_results: 各智能体返回数据
        structured_requirement: 结构化需求
        optimize_route: 是否做路线优化
        use_real_traffic: 是否使用真实交通数据

    Returns:
        {
            "day_plans": [...],
            "negotiation": {...},
            "route_optimization_applied": bool,
            "final_validation": {...}
        }
    """
    from src.routes.integration import integrate_agent_results_to_daily_plans

    # 第1步：初始整合
    logger.info("[协商] 第1步: 智能体结果整合")
    day_plans = integrate_agent_results_to_daily_plans(
        agent_results, structured_requirement
    )

    # 第2步：路线优化
    route_applied = False
    if optimize_route:
        logger.info("[协商] 第2步: 路线优化")
        for i, plan in enumerate(day_plans):
            if use_real_traffic:
                plan = await optimize_real_route(plan, mode="transit")
            else:
                plan = _simple_route_optimize(plan)
            day_plans[i] = plan
        route_applied = True

    # 第3步：收集备选数据
    backup = _collect_backup_data(agent_results, structured_requirement)

    # 第4步：多轮协商
    logger.info("[协商] 第3步: 多轮协商修复")
    result = await negotiate_and_fix(
        day_plans, structured_requirement, backup, max_iterations=5
    )

    return {
        "day_plans": result["day_plans"],
        "negotiation": {
            "log": result["negotiation_log"],
            "iteration_count": result["iteration_count"],
            "fully_resolved": result["fully_resolved"],
        },
        "route_optimization_applied": route_applied,
        "final_validation": result["validation"]
    }


def _simple_route_optimize(day_plan: dict) -> dict:
    """简版路线优化（按纬度排序，复用原有逻辑）"""
    plan = copy.deepcopy(day_plan)
    attractions = plan.get("attractions", [])
    valid = [a for a in attractions if isinstance(a, dict)]
    plan["attractions"] = sorted(
        valid,
        key=lambda x: x.get("location", {}).get("lat", 0)
        if isinstance(x.get("location"), dict) else 0
    )
    return plan


def _collect_backup_data(agent_results: dict, structured_requirement: dict) -> dict:
    """收集未使用的备选景点数据"""
    attractions = agent_results.get("attraction", {}).get("attractions", [])
    travel_days = structured_requirement.get("travel_days", 1)
    needed = travel_days * 3
    return {
        "attractions": attractions[needed:] if len(attractions) > needed else []
    }