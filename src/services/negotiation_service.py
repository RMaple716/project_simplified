"""
协商智能体服务 - 协调层核心引擎

功能:
1. 冲突检测后的自动协商修复（8种策略）
2. 多轮迭代优化（修复→校验→再修复→再校验）
3. 接入高德地图API的真实路线优化（贪心最近邻算法）
4. 事件驱动协商可视化（向 NegotiationEventBus 发布结构化事件）
5. 【P1增强】LLM驱动的策略仲裁（当规则化策略全部失败时）
6. 【P1增强】多维效用评估体系（动态计算效用值）
7. 【P1增强】动态策略选择器（根据冲突类型智能选择策略）

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
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple

from src.services.negotiation_event_bus import (
    event_bus,
    create_negotiation_event,
    NegotiationEventType,
    NegotiationPhase,
    build_route_preview,
)

# 【P1增强】动态策略选择器
from src.services.negotiation_strategies import (
    strategy_selector,
    register_default_strategies,
)

# 【P1增强】效用评估体系
from src.services.negotiation_utility import (
    utility_evaluator,
    compute_utility_dict,
)

# 【P1增强】LLM仲裁者
from src.services.negotiation_llm_arbiter import (
    llm_arbiter,
)

logger = logging.getLogger(__name__)


# ==================== 1. 时间工具函数（统一导入自 validate.py） ====================

from src.routes.validate import (
    parse_time_to_minutes as _parse_time_to_minutes,
    parse_duration_to_minutes as _parse_duration_to_minutes,
    format_minutes,
)

# 为保持与 negotiation_service.py 现有调用兼容，使用别名导出
parse_time_to_minutes = _parse_time_to_minutes
parse_duration_to_minutes = _parse_duration_to_minutes


def minutes_to_time_str(minutes: int) -> str:
    """将分钟数转换为 HH:MM 格式"""
    return format_minutes(minutes)


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
        from src.services.navigation_service import navigation_service as nav
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


# ==================== 3. 八大连贯协商修复策略 ====================

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


def strategy_adjust_opening_hours(day_plan: dict, conflict: dict) -> Optional[dict]:
    """
    【策略6】开放时间适配 - 将景点的游览时间平移到开放时段内

    针对 outside_opening_hours 冲突（景点安排在开放时间之外），
    将冲突景点的游览时间段整体移动到景点开放的时段范围内，
    然后联动重排当天其他活动的时间线。

    Args:
        day_plan: 当日行程
        conflict: 冲突信息 {activities: [name]}

    Returns:
        修复后的 day_plan，或 None（无法修复）
    """
    plan = copy.deepcopy(day_plan)
    conflict_names = set(conflict.get("activities", []))
    if not conflict_names:
        return None

    from src.routes.validate import parse_opening_hours

    any_adjusted = False

    for attr in plan.get("attractions", []):
        name = attr.get("name", "")
        if name not in conflict_names:
            continue

        # 解析开放时间
        opening_str = attr.get("opening_hours")
        if not opening_str:
            continue

        open_range = parse_opening_hours(opening_str)
        if not open_range:
            continue

        open_start, open_end = open_range

        # 获取当前游览时间
        start_str = attr.get("start_time") or attr.get("visit_time", "09:00")
        end_str = attr.get("end_time")
        dur_str = attr.get("duration") or attr.get("visit_duration") or "2小时"

        start_m = parse_time_to_minutes(start_str)
        dur_m = parse_duration_to_minutes(dur_str)

        if end_str:
            end_m = parse_time_to_minutes(end_str)
        else:
            end_m = start_m + dur_m

        visit_dur = end_m - start_m

        # 检查是否能完全放进开放时段
        if visit_dur > (open_end - open_start):
            logger.info(
                f"[协商] 策略6: '{name}' 游览时长({visit_dur}分) "
                f"超过开放时段({open_end - open_start}分)，无法修复"
            )
            continue

        # 计算能塞进开放时段的最早/最晚起始时间
        earliest_start = open_start
        latest_start = open_end - visit_dur

        if latest_start < earliest_start:
            continue

        # 新起始时间：尽量靠近原时间，但必须在开放时段内
        new_start = max(earliest_start, min(start_m, latest_start))
        new_end = new_start + visit_dur

        old_start_str = attr.get("start_time", "?")
        old_end_str = attr.get("end_time", "?")
        attr["start_time"] = minutes_to_time_str(new_start)
        attr["end_time"] = minutes_to_time_str(new_end)
        hour_val = new_start / 60
        attr["visit_time"] = "上午" if hour_val < 12 else ("下午" if hour_val < 17 else "晚上")
        if hour_val < 12:
            attr["visit_time_slot"] = "morning"
        elif hour_val < 17:
            attr["visit_time_slot"] = "afternoon"
        else:
            attr["visit_time_slot"] = "evening"

        logger.info(
            f"[协商] 策略6: '{name}' 开放时间适配 "
            f"{old_start_str}-{old_end_str} → "
            f"{minutes_to_time_str(new_start)}-{minutes_to_time_str(new_end)} "
            f"（开放{opening_str}）"
        )
        any_adjusted = True

    if not any_adjusted:
        return None

    # 景点时间调整后，重排当天所有活动的时间线
    all_items = []
    for attr in plan.get("attractions", []):
        all_items.append({"type": "attraction", "data": attr})
    for meal in plan.get("meals", []):
        all_items.append({"type": "meal", "data": meal})
    if plan.get("transport"):
        all_items.append({"type": "transport", "data": plan["transport"]})

    if len(all_items) < 2:
        return plan

    for item in all_items:
        data = item["data"]
        start_s = data.get("start_time") or data.get("time") or "09:00"
        dur_s = data.get("duration") or data.get("visit_duration") or "1小时"
        s_m = parse_time_to_minutes(start_s)
        d_m = parse_duration_to_minutes(dur_s)
        data["_start_m"] = s_m
        data["_end_m"] = s_m + d_m

    # 按原顺序重排，15分钟间隔
    margin = 15
    current = all_items[0]["data"]["_start_m"]
    for i, item in enumerate(all_items):
        data = item["data"]
        dur_m = data["_end_m"] - data["_start_m"]
        if i > 0:
            current = max(current, all_items[i - 1]["data"]["_end_m"] + margin)
        data["_new_start"] = current
        data["_new_end"] = current + dur_m
        current = data["_new_end"]

    if all_items and all_items[-1]["data"]["_new_end"] > 1320:
        return None

    for item in all_items:
        data = item["data"]
        data["start_time"] = minutes_to_time_str(data["_new_start"])
        data["end_time"] = minutes_to_time_str(data["_new_end"])
        for key in ("_start_m", "_end_m", "_new_start", "_new_end"):
            data.pop(key, None)

        plan["attractions"] = [it["data"] for it in all_items]

    return plan


# ==================== 3B. 新增协商修复策略 ====================


def strategy_geo_distance_split(
    day_plans: List[dict],
    conflict: dict,
    structured_requirement: Optional[dict] = None
) -> Optional[List[dict]]:
    """
    【策略9】地理距离拆分 - 将相距过远的景点拆分到不同天

    适用场景: geo_distance 冲突，同一天内相邻景点直线距离超过30km

    策略:
      1. 找出冲突涉及的两个景点中，离当天其他景点更远的那个
      2. 将其移动到景点最少的那一天
      3. 如果没有多天或移动后仍无法解决，则用备选景点替换
    """
    plans = copy.deepcopy(day_plans)
    if len(plans) <= 1:
        return None

    conflict_activities = conflict.get("activities", [])
    if len(conflict_activities) < 2:
        return None

    target_name_a = conflict_activities[0]
    target_name_b = conflict_activities[1]
    day_num = conflict.get("day", 1)
    day_idx = day_num - 1

    if day_idx < 0 or day_idx >= len(plans):
        return None

    day_plan = plans[day_idx]
    attractions = day_plan.get("attractions", [])

    # 找到这两个景点在同一天的索引
    idx_a = None
    idx_b = None
    for i, attr in enumerate(attractions):
        name = attr.get("name", "")
        if name == target_name_a:
            idx_a = i
        elif name == target_name_b:
            idx_b = i

    if idx_a is None or idx_b is None:
        return None

    # 计算这两个景点分别到当天其他所有景点的平均距离
    def _avg_dist_to_others(attr_idx, all_attrs):
        loc_self = all_attrs[attr_idx].get("location") if isinstance(all_attrs[attr_idx].get("location"), dict) else {}
        distances = []
        for j, other in enumerate(all_attrs):
            if j == attr_idx:
                continue
            loc_other = other.get("location") if isinstance(other.get("location"), dict) else {}
            d = _haversine_distance(loc_self, loc_other)
            if d < float("inf"):
                distances.append(d)
        if not distances:
            return float("inf")
        return sum(distances) / len(distances)

    avg_dist_a = _avg_dist_to_others(idx_a, attractions)
    avg_dist_b = _avg_dist_to_others(idx_b, attractions)

    # 选平均距离更大的那个移走（它是"离群点"）
    if avg_dist_a >= avg_dist_b:
        move_idx = idx_a
        move_name = target_name_a
    else:
        move_idx = idx_b
        move_name = target_name_b

    # 找景点最少的天（排除当前天）
    min_day_idx = min(
        (i for i in range(len(plans)) if i != day_idx),
        key=lambda x: len(plans[x].get("attractions", [])),
        default=None
    )
    if min_day_idx is None:
        return None

    # 检查目标天是否已有同名的景点（避免重复）
    target_plan = plans[min_day_idx]
    existing_names = {a.get("name", "") for a in target_plan.get("attractions", [])}
    if move_name in existing_names:
        return None

    # 执行移动
    moved_attr = plans[day_idx]["attractions"].pop(move_idx)
    plans[min_day_idx]["attractions"].append(moved_attr)

    logger.info(
        f"[协商] 策略9(地理距离拆分): '{move_name}' 第{day_num}天 → 第{min_day_idx+1}天 "
        f"(距当天其他景点平均{avg_dist_a if move_idx == idx_a else avg_dist_b:.0f}km)"
    )
    return plans


def strategy_geo_distance_replace(
    day_plan: dict,
    conflict: dict,
    backup_attractions: list
) -> Optional[dict]:
    """
    【策略10】地理距离替换 - 用备选景点替换远距离景点

    适用场景: geo_distance 冲突，但没有多天可供移动时

    策略:
      1. 找出冲突两个景点中离当天其他景点更远的那个
      2. 从备选景点中找一个距离合适的替代
    """
    plan = copy.deepcopy(day_plan)
    conflict_activities = conflict.get("activities", [])
    if len(conflict_activities) < 2:
        return None

    target_name_a = conflict_activities[0]
    target_name_b = conflict_activities[1]
    attractions = plan.get("attractions", [])

    idx_a = None
    idx_b = None
    for i, attr in enumerate(attractions):
        name = attr.get("name", "")
        if name == target_name_a:
            idx_a = i
        elif name == target_name_b:
            idx_b = i

    if idx_a is None or idx_b is None:
        return None

    def _avg_dist_to_others(attr_idx, all_attrs):
        loc_self = all_attrs[attr_idx].get("location") if isinstance(all_attrs[attr_idx].get("location"), dict) else {}
        distances = []
        for j, other in enumerate(all_attrs):
            if j == attr_idx:
                continue
            loc_other = other.get("location") if isinstance(other.get("location"), dict) else {}
            d = _haversine_distance(loc_self, loc_other)
            if d < float("inf"):
                distances.append(d)
        if not distances:
            return float("inf")
        return sum(distances) / len(distances)

    avg_dist_a = _avg_dist_to_others(idx_a, attractions)
    avg_dist_b = _avg_dist_to_others(idx_b, attractions)

    replace_idx = idx_a if avg_dist_a >= avg_dist_b else idx_b
    replace_name = attractions[replace_idx].get("name", "")

    existing_names = {a.get("name", "") for a in attractions}
    if not backup_attractions:
        return None

    other_locs = []
    for j, attr in enumerate(attractions):
        if j == replace_idx:
            continue
        loc = attr.get("location") if isinstance(attr.get("location"), dict) else {}
        if loc.get("lat") is not None and loc.get("lng") is not None:
            other_locs.append((float(loc["lat"]), float(loc["lng"])))

    best_replacement = None
    best_score = float("inf")

    for backup in backup_attractions:
        b_name = backup.get("name", "")
        if b_name in existing_names or b_name == replace_name:
            continue
        b_loc = backup.get("location") if isinstance(backup.get("location"), dict) else {}
        b_lat, b_lng = b_loc.get("lat"), b_loc.get("lng")
        if b_lat is None or b_lng is None:
            continue
        if other_locs:
            center_lat = sum(lat for lat, _ in other_locs) / len(other_locs)
            center_lng = sum(lng for _, lng in other_locs) / len(other_locs)
            dist_to_center = _haversine_distance(
                {"lat": b_lat, "lng": b_lng},
                {"lat": center_lat, "lng": center_lng}
            )
            if dist_to_center < best_score:
                best_score = dist_to_center
                best_replacement = backup

    if best_replacement is None:
        return None

    attractions[replace_idx] = copy.deepcopy(best_replacement)
    attractions[replace_idx].pop("day_index", None)

    logger.info(
        f"[协商] 策略10(地理距离替换): '{replace_name}' → '{best_replacement.get('name', '')}' "
        f"(距中心{best_score:.0f}km)"
    )
    return plan


def strategy_closed_day_resolve(
    day_plans: List[dict],
    conflict: dict,
    structured_requirement: Optional[dict] = None
) -> Optional[List[dict]]:
    """
    【策略7】闭馆日解决 - 将冲突景点移到非闭馆的日期

    针对 closed_day 冲突（景点安排在闭馆日），尝试：
    1. 如果有多天行程，将景点移到没有闭馆冲突的另一天
    2. 如果只有一天，交换当天景点和其他天的景点顺序

    Args:
        day_plans: 多天行程计划
        conflict: 冲突信息 {activities: [name], closed_days: [...], current_weekday: int}
        structured_requirement: 结构化需求（含日期信息）

    Returns:
        修复后的多天行程计划，或 None
    """
    from datetime import datetime, timedelta

    plans = copy.deepcopy(day_plans)
    if len(plans) <= 1:
        return None

    conflict_names = set(conflict.get("activities", []))
    closed_days = conflict.get("closed_days", [])
    current_weekday = conflict.get("current_weekday")

    # 找出冲突景点名称
    conflict_attr_name = None
    for name in conflict_names:
        conflict_attr_name = name
        break

    if not conflict_attr_name:
        return None

    # 找到冲突景点所在的 day_idx 和 index
    source_day_idx = None
    source_attr_idx = None
    for d_idx, plan in enumerate(plans):
        for a_idx, attr in enumerate(plan.get("attractions", [])):
            if isinstance(attr, dict) and attr.get("name") == conflict_attr_name:
                source_day_idx = d_idx
                source_attr_idx = a_idx
                break
        if source_day_idx is not None:
            break

    if source_day_idx is None:
        return None

    # 查找哪些天的日期不是闭馆日
    for target_day_idx in range(len(plans)):
        if target_day_idx == source_day_idx:
            continue

        target_date_str = plans[target_day_idx].get("date", "")
        if not target_date_str or "-" not in str(target_date_str):
            # 如果没有有效日期，尝试移动（无法判断闭馆日，作为兜底）
            moved_attr = plans[source_day_idx]["attractions"].pop(source_attr_idx)
            plans[target_day_idx]["attractions"].append(moved_attr)
            logger.info(
                f"[协商] 策略7: '{conflict_attr_name}' 第{source_day_idx+1}天 → "
                f"第{target_day_idx+1}天（闭馆日规避）"
            )
            return plans

        try:
            dt = datetime.strptime(str(target_date_str), "%Y-%m-%d")
            target_weekday = dt.weekday()
            if target_weekday not in closed_days:
                # 目标天不是闭馆日，移动景点
                moved_attr = plans[source_day_idx]["attractions"].pop(source_attr_idx)
                # 重置时间槽为默认值
                moved_attr["start_time"] = "09:00"
                moved_attr["end_time"] = "11:30"
                moved_attr["visit_time"] = "上午"
                moved_attr["visit_time_slot"] = "morning"
                plans[target_day_idx]["attractions"].append(moved_attr)
                logger.info(
                    f"[协商] 策略7: '{conflict_attr_name}' 第{source_day_idx+1}天 → "
                    f"第{target_day_idx+1}天（避开闭馆日）"
                )
                return plans
        except (ValueError, TypeError):
            continue

    return None


def strategy_transport_split(
    day_plan: dict,
    conflict: dict
) -> Optional[dict]:
    """
    【策略8】交通段拆分 - 将长交通段拆分为两段，中间插入餐饮

    针对 time_overlap 冲突，其中一方是交通（transport）且另一方是餐饮（meal）的情况：
    将交通段拆分为"前段→用餐→后段"，解决时间重叠。

    Args:
        day_plan: 当日行程
        conflict: 冲突信息 {activities: [transport_name, meal_name]}

    Returns:
        修复后的 day_plan，或 None
    """
    plan = copy.deepcopy(day_plan)
    conflict_names = set(conflict.get("activities", []))

    # 找出交通活动和餐饮活动
    transport_data = None
    meal_data = None
    transport_idx = None
    meal_idx = None

    # 检查 transport 字段
    transport = plan.get("transport")
    if isinstance(transport, dict):
        transport_name = f"前往{transport.get('to', '目的地')}"
        if transport_name in conflict_names:
            transport_data = transport

    # 检查 meals 中是哪个在冲突中
    for m_idx, meal in enumerate(plan.get("meals", [])):
        if isinstance(meal, dict) and meal.get("name", "") in conflict_names:
            meal_data = meal
            meal_idx = m_idx
            break

    if not transport_data or not meal_data:
        return None

    # 获取交通起止时间
    t_start_str = transport_data.get("departure_time") or "09:00"
    t_dur = transport_data.get("duration", 60)
    if isinstance(t_dur, str):
        t_dur = parse_duration_to_minutes(t_dur)
    t_start_m = parse_time_to_minutes(t_start_str)
    t_end_m = t_start_m + t_dur

    # 获取餐饮起止时间
    m_start_str = meal_data.get("start_time") or meal_data.get("time") or "12:00"
    m_dur_str = meal_data.get("duration", "1小时")
    m_start_m = parse_time_to_minutes(m_start_str)
    m_dur_m = parse_duration_to_minutes(m_dur_str)
    m_end_m = m_start_m + m_dur_m

    # 计算重叠区域
    overlap_start = max(t_start_m, m_start_m)
    overlap_end = min(t_end_m, m_end_m)

    if overlap_end <= overlap_start:
        return None  # 没有重叠，无需拆分

    # 拆分逻辑：将交通拆分为用餐前段和用餐后段
    # 前段：t_start -> m_start（如果用餐在交通中间开始）
    # 后段：m_end -> t_end（如果用餐在交通中间结束）

    # 方案：将餐饮时间作为交通中的"休息点"
    # 重新安排：前段交通 -> 用餐 -> 后段交通

    # 前段交通时间
    first_leg_dur = max(10, m_start_m - t_start_m)
    # 后段交通时间
    second_leg_dur = max(10, t_end_m - m_end_m)

    # 更新交通信息为首段
    transport_data["departure_time"] = minutes_to_time_str(t_start_m)
    transport_data["duration"] = first_leg_dur
    transport_data["duration_text"] = f"{first_leg_dur}分钟"

    # 添加第二段交通
    second_transport = copy.deepcopy(transport_data)
    second_transport["departure_time"] = minutes_to_time_str(m_end_m)
    second_transport["duration"] = second_leg_dur
    second_transport["duration_text"] = f"{second_leg_dur}分钟"
    second_transport["transport_id"] = transport_data.get("transport_id", "trans_0000") + "_split"

    # 将第二段交通存入 day_plan（作为后续交通）
    plan["next_transport"] = second_transport

    # 确保餐饮时间固定在重叠后的位置
    meal_data["start_time"] = minutes_to_time_str(m_start_m)
    meal_data["time"] = minutes_to_time_str(m_start_m)
    meal_data["end_time"] = minutes_to_time_str(m_end_m)

    logger.info(
        f"[协商] 策略8: 拆分交通 '{transport_data.get('to', '')}' "
        f"({t_start_str}, {t_dur}分) 绕开用餐 '{meal_data.get('name', '')}' "
        f"({minutes_to_time_str(m_start_m)}-{minutes_to_time_str(m_end_m)})"
    )

    return plan


async def optimize_real_route(
    day_plan: dict,
    mode: str = "transit",
    distance_threshold_km: float = 50.0,
    transport_time_threshold_min: int = 90
) -> dict:
    """
    基于真实交通数据的路线优化（增强版）

    改进:
      1. 增加地理聚类检查：计算景点对间距离，对超过阈值的景点对优先触发替换提示
      2. 使用 2-opt 对贪心结果进行后优化，减少总路径长度
      3. 路线优化后立即执行开放时间适配策略，防止优化产生的时间偏移导致新冲突

    Args:
        day_plan: 当日行程
        mode: 交通模式 walking/driving/transit
        distance_threshold_km: 地理距离阈值（km），超过此值标记为远距离
        transport_time_threshold_min: 交通耗时阈值（分钟），超过此值标记警告

    Returns:
        优化后的 day_plan
    """
    plan = copy.deepcopy(day_plan)
    attractions = plan.get("attractions", [])
    if len(attractions) <= 1:
        return plan

    n = len(attractions)
    logger.info(f"[协商] 真实路线优化(增强版): {n}个景点")

    # 构建耗时矩阵和polyline矩阵
    travel_matrix = [[0] * n for _ in range(n)]
    polyline_matrix = [[""] * n for _ in range(n)]
    geo_distance_matrix = [[0.0] * n for _ in range(n)]

    for i in range(n):
        for j in range(i + 1, n):
            loc_i = attractions[i].get("location", {})
            loc_j = attractions[j].get("location", {})
            dur, poly = await get_real_transport_time(loc_i, loc_j, mode)
            travel_matrix[i][j] = dur
            travel_matrix[j][i] = dur
            polyline_matrix[i][j] = poly
            polyline_matrix[j][i] = poly

            # 计算地理直线距离（km）
            geo_dist = _haversine_distance(loc_i, loc_j)
            geo_distance_matrix[i][j] = geo_dist
            geo_distance_matrix[j][i] = geo_dist

            logger.info(f"[协商]   {attractions[i]['name']}↔{attractions[j]['name']}: 交通{dur}分钟, 直线{geo_dist:.1f}km")

    # ---- 地理聚类检查：超过距离阈值的景点对，标记警告 ----
    long_distance_pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            if geo_distance_matrix[i][j] > distance_threshold_km:
                long_distance_pairs.append((attractions[i]['name'], attractions[j]['name'], geo_distance_matrix[i][j]))
                logger.warning(f"[协商]  远距离对: {attractions[i]['name']}↔{attractions[j]['name']}: {geo_distance_matrix[i][j]:.1f}km > {distance_threshold_km}km")

    # ---- 贪心最近邻算法 ----
    ordered = [0]
    remaining = set(range(1, n))
    while remaining:
        last = ordered[-1]
        nearest = min(remaining, key=lambda x: travel_matrix[last][x])
        ordered.append(nearest)
        remaining.remove(nearest)

    # ---- 2-opt 后优化 ----
    def calc_total_distance(order):
        if len(order) < 2:
            return 0
        return sum(travel_matrix[order[i]][order[i+1]] for i in range(len(order)-1))

    def two_opt_improve(order):
        improved = True
        best_order = order[:]
        best_dist = calc_total_distance(best_order)
        iterations = 0
        max_iterations = 50
        while improved and iterations < max_iterations:
            improved = False
            iterations += 1
            for i in range(1, len(best_order) - 2):
                for j in range(i + 1, len(best_order) - 1):
                    new_order = best_order[:i] + best_order[i:j+1][::-1] + best_order[j+1:]
                    new_dist = calc_total_distance(new_order)
                    if new_dist < best_dist:
                        best_order = new_order
                        best_dist = new_dist
                        improved = True
                        break
                if improved:
                    break
        return best_order

    ordered = two_opt_improve(ordered)

    # ---- 模拟退火后优化（进一步减少总路径长度） ----
    def simulated_annealing(order, initial_temp=1000, cooling_rate=0.995, min_temp=1):
        import random
        import math as m
        current_order = order[:]
        current_dist = calc_total_distance(current_order)
        best_order = current_order[:]
        best_dist = current_dist
        temp = initial_temp
        while temp > min_temp:
            # 生成邻域解：随机交换两个位置
            i = random.randint(1, len(current_order) - 2)
            j = random.randint(i + 1, len(current_order) - 1)
            new_order = current_order[:i] + current_order[i:j+1][::-1] + current_order[j+1:]
            new_dist = calc_total_distance(new_order)
            delta = new_dist - current_dist
            if delta < 0 or random.random() < m.exp(-delta / temp):
                current_order = new_order
                current_dist = new_dist
                if current_dist < best_dist:
                    best_order = current_order[:]
                    best_dist = current_dist
            temp *= cooling_rate
        return best_order

    if n >= 4:
        ordered = simulated_annealing(ordered)

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

    # 检查任意路段交通耗时是否超过阈值
    long_distance_segments = []
    for i in range(n - 1):
        leg_dur = travel_matrix[ordered[i]][ordered[i+1]]
        if leg_dur > transport_time_threshold_min:
            long_distance_segments.append({
                "from": new_attractions[i]["name"],
                "to": new_attractions[i+1]["name"],
                "duration": leg_dur,
                "threshold": transport_time_threshold_min,
            })
            logger.warning(f"[协商]  长时间路段: {new_attractions[i]['name']}→{new_attractions[i+1]['name']}: {leg_dur}分钟 > {transport_time_threshold_min}分钟")

    plan["_long_distance_warnings"] = long_distance_segments  # 供前端高亮

    # ---- 路线优化后立即执行开放时间适配，防止时间偏移导致新冲突 ----
    for attr in plan.get("attractions", []):
        opening_str = attr.get("opening_hours")
        if opening_str:
            from src.routes.validate import parse_opening_hours
            open_range = parse_opening_hours(opening_str)
            if open_range:
                open_start, open_end = open_range
                start_str = attr.get("start_time") or attr.get("visit_time", "09:00")
                end_str = attr.get("end_time")
                dur_str = attr.get("duration") or attr.get("visit_duration") or "2小时"
                start_m = parse_time_to_minutes(start_str)
                dur_m = parse_duration_to_minutes(dur_str)
                if end_str:
                    end_m = parse_time_to_minutes(end_str)
                else:
                    end_m = start_m + dur_m
                visit_dur = end_m - start_m
                if visit_dur <= (open_end - open_start):
                    # 如果当前时间不在开放时段内，平移到开放时段
                    if start_m < open_start or end_m > open_end:
                        earliest_start = open_start
                        latest_start = open_end - visit_dur
                        if latest_start >= earliest_start:
                            new_start = max(earliest_start, min(start_m, latest_start))
                            new_end = new_start + visit_dur
                            attr["start_time"] = minutes_to_time_str(new_start)
                            attr["end_time"] = minutes_to_time_str(new_end)
                            hour_val = new_start / 60
                            attr["visit_time"] = "上午" if hour_val < 12 else ("下午" if hour_val < 17 else "晚上")
                            if hour_val < 12:
                                attr["visit_time_slot"] = "morning"
                            elif hour_val < 17:
                                attr["visit_time_slot"] = "afternoon"
                            else:
                                attr["visit_time_slot"] = "evening"
                            logger.info(f"[协商] 路线优化后开放时间适配: '{attr.get('name')}' {start_str}-{end_str or '?'} → {minutes_to_time_str(new_start)}-{minutes_to_time_str(new_end)}")

    logger.info(f"[协商] 路线优化完成(2-opt), 交通总耗时约{total_traffic_dur}分钟")
    return plan


def _haversine_distance(loc1: dict, loc2: dict) -> float:
    """计算两点间的大圆距离（km）"""
    import math
    if not loc1 or not loc2:
        return float('inf')
    lat1 = loc1.get("lat") or loc1.get("latitude", 0)
    lng1 = loc1.get("lng") or loc1.get("longitude") or loc1.get("lon", 0)
    lat2 = loc2.get("lat") or loc2.get("latitude", 0)
    lng2 = loc2.get("lng") or loc2.get("longitude") or loc2.get("lon", 0)
    try:
        lat1, lng1, lat2, lng2 = float(lat1), float(lng1), float(lat2), float(lng2)
    except (TypeError, ValueError):
        return float('inf')
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

# ==================== 5. 调整详情生成工具 ====================

def _build_adjustment_details(plan_before: dict, plan_after: dict, strategy_name: str) -> list:
    """
    对比修复前后的 day_plan，生成详细的调整内容列表

    返回格式:
    [
        {
            "field": "游览时间",
            "item_name": "故宫博物院",
            "before": "09:00-12:00",
            "after": "10:00-13:00",
            "strategy": "时间平移"
        },
        ...
    ]
    """
    details = []

    # ---- 比较景点变化 ----
    before_attrs = {a.get("name", ""): a for a in plan_before.get("attractions", []) if isinstance(a, dict)}
    after_attrs = {a.get("name", ""): a for a in plan_after.get("attractions", []) if isinstance(a, dict)}

    all_names = set(list(before_attrs.keys()) + list(after_attrs.keys()))
    for name in all_names:
        before_attr = before_attrs.get(name)
        after_attr = after_attrs.get(name)

        if not before_attr and after_attr:
            # 新增景点
            details.append({
                "field": "新增景点",
                "item_name": name,
                "before": "无",
                "after": after_attr.get("name", name),
                "strategy": strategy_name,
            })
            continue

        if before_attr and not after_attr:
            # 移除景点
            details.append({
                "field": "移除景点",
                "item_name": name,
                "before": before_attr.get("name", name),
                "after": "已移除",
                "strategy": strategy_name,
            })
            continue

        if not before_attr or not after_attr:
            continue

        # 检查游览时间变化 (start_time / end_time)
        b_start = before_attr.get("start_time") or before_attr.get("visit_time", "")
        a_start = after_attr.get("start_time") or after_attr.get("visit_time", "")
        b_end = before_attr.get("end_time", "")
        a_end = after_attr.get("end_time", "")
        if b_start != a_start or b_end != a_end:
            details.append({
                "field": "游览时间",
                "item_name": name,
                "before": f"{b_start}{'-' + b_end if b_end else ''}",
                "after": f"{a_start}{'-' + a_end if a_end else ''}",
                "strategy": strategy_name,
            })

        # 检查时长变化
        b_dur = before_attr.get("duration") or before_attr.get("visit_duration", "")
        a_dur = after_attr.get("duration") or after_attr.get("visit_duration", "")
        if b_dur != a_dur:
            details.append({
                "field": "游览时长",
                "item_name": name,
                "before": b_dur,
                "after": a_dur,
                "strategy": strategy_name,
            })

        # 检查时间段变化
        b_slot = before_attr.get("visit_time_slot", "")
        a_slot = after_attr.get("visit_time_slot", "")
        if b_slot != a_slot:
            details.append({
                "field": "时间段",
                "item_name": name,
                "before": {"morning": "上午", "afternoon": "下午", "evening": "晚上"}.get(b_slot, b_slot),
                "after": {"morning": "上午", "afternoon": "下午", "evening": "晚上"}.get(a_slot, a_slot),
                "strategy": strategy_name,
            })

    # ---- 比较餐饮变化 ----
    before_meals = {m.get("name", ""): m for m in plan_before.get("meals", []) if isinstance(m, dict)}
    after_meals = {m.get("name", ""): m for m in plan_after.get("meals", []) if isinstance(m, dict)}

    for name, after_meal in after_meals.items():
        before_meal = before_meals.get(name)
        if not before_meal:
            continue
        b_time = before_meal.get("start_time") or before_meal.get("time") or before_meal.get("meal_time", "")
        a_time = after_meal.get("start_time") or after_meal.get("time") or after_meal.get("meal_time", "")
        if b_time != a_time:
            details.append({
                "field": "用餐时间",
                "item_name": name,
                "before": b_time,
                "after": a_time,
                "strategy": strategy_name,
            })

    if not details:
        details.append({
            "field": "调整策略",
            "item_name": "行程",
            "before": "冲突状态",
            "after": f"执行{strategy_name}",
            "strategy": strategy_name,
        })

    return details


# ==================== 6. 主协商流程 ====================

def _global_reshuffle(day_plans: List[dict], structured_requirement: dict) -> None:
    """
    全局重排 - 按地理聚类重新分配景点到各天

    当局部修复策略全部失败时，此函数按景点的地理坐标聚类，
    将相近的景点分配到同一天，跨越距离阈值的景点拆分到不同天。

    Args:
        day_plans: 每日行程列表（就地修改）
        structured_requirement: 结构化需求
    """
    import math

    if len(day_plans) <= 1:
        return

    # 收集所有天的所有景点
    all_attractions = []
    for plan in day_plans:
        for attr in plan.get("attractions", []):
            if isinstance(attr, dict):
                all_attractions.append(copy.deepcopy(attr))

    if not all_attractions:
        return

    # 计算每个景点与其他景点的距离
    def haversine_km(loc1, loc2):
        if not loc1 or not loc2:
            return float('inf')
        lat1 = loc1.get("lat") or loc1.get("latitude", 0)
        lng1 = loc1.get("lng") or loc1.get("longitude") or loc1.get("lon", 0)
        lat2 = loc2.get("lat") or loc2.get("latitude", 0)
        lng2 = loc2.get("lng") or loc2.get("longitude") or loc2.get("lon", 0)
        if not lat1 or not lng1 or not lat2 or not lng2:
            return float('inf')
        try:
            lat1, lng1, lat2, lng2 = float(lat1), float(lng1), float(lat2), float(lng2)
        except (TypeError, ValueError):
            return float('inf')
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

    # 使用简单的聚类：第一个景点作为第1天的锚点，对剩余景点：
    # 如果距离当前天所有景点 < 50km，则归入同一天，否则尝试下一天
    num_days = len(day_plans)
    daily_groups = [[] for _ in range(num_days)]

    for attr in all_attractions:
        loc = attr.get("location", {})
        best_day = 0
        best_score = -float('inf')

        for d_idx in range(num_days):
            if not daily_groups[d_idx]:
                score = 0  # 空天优先分配
            else:
                # 计算与此天所有景点的平均距离
                avg_dist = sum(
                    haversine_km(loc, a.get("location", {}))
                    for a in daily_groups[d_idx]
                ) / len(daily_groups[d_idx])
                score = -avg_dist  # 距离越小得分越高

            # 如果得分更高或天数已满则分配
            if score > best_score or (score == best_score and d_idx < best_day):
                best_score = score
                best_day = d_idx

        # 确保各天景点数均衡
        if len(daily_groups[best_day]) >= len(all_attractions) // num_days + 1:
            for d_idx in range(num_days):
                if len(daily_groups[d_idx]) < len(all_attractions) // num_days:
                    best_day = d_idx
                    break

        daily_groups[best_day].append(attr)

    # 将聚类结果写回 day_plans
    for d_idx in range(num_days):
        if d_idx < len(day_plans):
            day_plans[d_idx]["attractions"] = daily_groups[d_idx]

    logger.info(f"[协商] 全局重排完成: 将{len(all_attractions)}个景点重新分配到{num_days}天")


# ==================== 4B. 组合修复辅助函数 ====================


async def negotiate_and_fix(
    day_plans: List[dict],
    structured_requirement: dict,
    backup_data: Optional[dict] = None,
    max_iterations: int = 5,
    optimize_route: bool = False,
    use_real_traffic: bool = False
) -> dict:
    """
    核心协商流程：多轮迭代的冲突检测→路线优化→修复→再检测→再修复

    流程:
      循环最多max_iterations次:
        1. 调用路线优化（如果启用），优化景点排序并更新时间分配（含2-opt后优化）
        2. 调用 check_itinerary_conflicts 检测冲突
        3. 如果没有严重冲突，终止
        4. 对有冲突的每一天，按优先级尝试 策略1→策略2(开放时间适配)→策略3→策略4→策略5→策略6→组合修复→策略7→策略8→策略9
        5. 如果本轮没有修复任何冲突，先触发全局重排，连续两轮无修复+仍有error再终止

    Args:
        day_plans: 每日行程列表
        structured_requirement: 结构化需求
        backup_data: 备选景点数据 {"attractions": [...]}
        max_iterations: 最大迭代次数
        optimize_route: 是否在每轮迭代开始时执行路线优化
        use_real_traffic: 是否使用真实交通数据（需配置AMAP_API_KEY）

    Returns:
        {
            "day_plans": 修复后的行程,
            "negotiation_log": 协商日志,
            "iteration_count": 实际迭代次数,
            "fully_resolved": bool 是否完全解决
        }
    """
    from src.routes.validate import check_itinerary_conflicts
    from src.services.negotiation_event_bus import agent_message_bus, AgentMessageType
    from src.services.negotiation_utility import compute_utility_dict

    # 【P1增强】记录策略选择器统计信息（第一轮时输出）
    if strategy_selector.registry.strategy_count > 0 and not hasattr(negotiate_and_fix, '_strategies_registered'):
        negotiate_and_fix._strategies_registered = True  # type: ignore
        logger.info(f"[协商] 动态策略选择器已就绪，共{strategy_selector.registry.strategy_count}个策略")

    # 生成唯一 sessionId（复用 taskId 或产生新的）
    session_id = structured_requirement.get("task_id") or str(uuid.uuid4())

    negotiation_log = []
    backup_attractions = list((backup_data or {}).get("attractions", []))
    current_plans = copy.deepcopy(day_plans)

    # 重置连续无修复计数（确保跨多次调用各自独立）
    negotiate_and_fix._no_fix_streak = 0  # type: ignore

    # 发布 CFP 事件（协商开始）
    print(f"[协商诊断] 1. 开始协商，session_id={session_id}")
    print(f"[协商诊断] 2. event_bus 类型: {type(event_bus).__name__}, id: {id(event_bus)}")
    print(f"[协商诊断] 2b. event_bus 版本: {'增强版(含WebSocket+持久化+Agent通信)' if hasattr(event_bus, 'ws_manager') else '旧版'}")
    cfp_event = create_negotiation_event(
        event_type=NegotiationEventType.CFP,
        session_id=session_id,
        from_agent="dispatcher",
        to_agent="all_vehicles",
        phase=NegotiationPhase.CFP,
        proposal={"description": f"开始协商修复行程冲突（共{max_iterations}轮）"},
        utility={"dispatcher": 1.0, "vehicle": 1.0},
    )
    print(f"[协商诊断] 3. CFP事件ID: {cfp_event.get('eventId')}")
    print(f"[协商诊断] 4. 即将发布CFP...")
    await event_bus.publish(session_id, cfp_event)
    print(f"[协商诊断] 5. CFP发布后, event_bus 中 session 数: {len(event_bus._session_logs)}")
    print(f"[协商诊断] 6. 当前 session 事件数: {len(event_bus.get_session_log(session_id))}")

        # ========== 【P1增强】注册默认策略到策略选择器 ==========
    if strategy_selector.registry.strategy_count == 0:
        register_default_strategies(strategy_selector)
        logger.info(f"[协商] 已注册{strategy_selector.registry.strategy_count}个策略到动态策略选择器")

    # ========== 【新增】Agent间通信：开始协商前通知所有Agent ==========
    print(f"[协商诊断] 7. 广播协商开始消息给所有Agent...")
    broadcast_responses = await agent_message_bus.broadcast(
        from_agent="dispatcher",
        message={
            "type": AgentMessageType.COORDINATE_REQUEST,
            "payload": {
                "action": "negotiation_start",
                "session_id": session_id,
                "max_iterations": max_iterations,
                "total_days": len(current_plans),
                "total_attractions": sum(
                    len(p.get("attractions", [])) for p in current_plans
                ),
            }
        },
        session_id=session_id,
    )
    print(f"[协商诊断] 8. Agent广播响应: {list(broadcast_responses.keys()) if broadcast_responses else '无响应'}")
    negotiation_log.append({
        "iteration": 0,
        "action": "广播协商开始",
        "target": "all_agents",
        "responses": list(broadcast_responses.keys()) if broadcast_responses else [],
    })

    for iteration in range(max_iterations):
        logger.info(f"[协商] === 第 {iteration + 1} 轮 ===")

        # === 策略0：每轮迭代开始前执行路线优化 ===
        # 将路线优化融入协商循环中，使得：
        #   1. 优化后的时间分配不会被后续协商策略无意义地覆盖
        #   2. 如果优化产生了新冲突，同一轮就能检测并修复
        #   3. 优化结果（景点排序）可以为后续时间平移等策略提供更好的基础
        if optimize_route:
            for d_idx in range(len(current_plans)):
                plan_before = copy.deepcopy(current_plans[d_idx])
                if use_real_traffic:
                    current_plans[d_idx] = await optimize_real_route(
                        current_plans[d_idx], mode="transit"
                    )
                else:
                    current_plans[d_idx] = _simple_route_optimize(current_plans[d_idx])

            # 收集所有天的 long_distance_warnings 并发布到事件总线
            all_long_distance_warnings = []
            for d_idx, plan in enumerate(current_plans):
                warnings = plan.pop("_long_distance_warnings", None)
                if warnings:
                    for w in warnings:
                        w["day"] = d_idx + 1
                    all_long_distance_warnings.extend(warnings)
            if all_long_distance_warnings:
                route_preview = build_route_preview(vehicle_id="route_opt", coordinates=[])
                route_preview["long_distance_warnings"] = all_long_distance_warnings
                await event_bus.publish(session_id, create_negotiation_event(
                    event_type=NegotiationEventType.COUNTER,
                    session_id=session_id,
                    from_agent="optimizer",
                    to_agent="dispatcher",
                    phase=NegotiationPhase.NEGOTIATE,
                    proposal={
                        "action": "路线优化完成",
                        "long_distance_warnings": all_long_distance_warnings,
                    },
                    extra={"longDistanceWarning": True, "longDistanceSegments": all_long_distance_warnings},
                    utility={"dispatcher": 0.85, "vehicle": 0.8},
                    route_preview=route_preview,
                ))
                logger.info(f"[协商] 发现 {len(all_long_distance_warnings)} 个长距离路段，已发布警告")

        validation = check_itinerary_conflicts(current_plans, structured_requirement)
        conflicts = validation.get("conflicts", [])
        has_error = any(c.get("severity") == "error" for c in conflicts)
        
        print(f"[协商诊断] 第{iteration+1}轮冲突检测: {len(conflicts)}个冲突, 其中error: {sum(1 for c in conflicts if c.get('severity')=='error')}, warning: {sum(1 for c in conflicts if c.get('severity')=='warning')}")
        for c_idx, c in enumerate(conflicts):
            print(f"[协商诊断]   冲突{c_idx+1}: [{c.get('severity')}] {c.get('description', '')[:80]}")

        if not has_error:
            logger.info(f"[协商] ✓ 第{iteration + 1}轮已无严重冲突")
            negotiation_log.append({
                "iteration": iteration + 1,
                "action": "协商完成",
                "remaining_conflicts": len(conflicts),
                "all_resolved": True
            })
            # 发布 ACCEPT 事件
            await event_bus.publish(session_id, create_negotiation_event(
                event_type=NegotiationEventType.ACCEPT,
                session_id=session_id,
                from_agent="dispatcher",
                to_agent="all_vehicles",
                phase=NegotiationPhase.FINALIZING,
                proposal={"final_conflicts": len(conflicts)},
                utility={"dispatcher": 0.95, "vehicle": 0.95},
            ))
            # 发布 FINALIZED 事件
            await event_bus.publish(session_id, create_negotiation_event(
                event_type=NegotiationEventType.FINALIZED,
                session_id=session_id,
                from_agent="dispatcher",
                to_agent="all_vehicles",
                phase=NegotiationPhase.FINALIZED,
                proposal={"iteration_count": iteration + 1},
                utility={"dispatcher": 1.0, "vehicle": 1.0},
            ))
            return {
                "day_plans": current_plans,
                "negotiation_log": negotiation_log,
                "iteration_count": iteration + 1,
                "fully_resolved": True,
                "validation": validation,
                "negotiation_events": event_bus.get_session_log(session_id),
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

            # 对当天的所有冲突逐一尝试修复策略（按优先级）
            # 修复一个冲突后继续处理下一个，直到所有冲突都遍历完毕
            for conflict in day_conflict_list:
                if not isinstance(conflict, dict):
                    continue

                # 如果当前 day_plan 已经被前面的冲突修复改动了，先从 current_plans 获取最新快照
                plan_before_snapshot = copy.deepcopy(current_plans[day_idx]) if day_idx < len(current_plans) else None

                # --- 发布 PROPOSE 事件：开始尝试修复 ---
                await event_bus.publish(session_id, create_negotiation_event(
                    event_type=NegotiationEventType.PROPOSE,
                    session_id=session_id,
                    from_agent="dispatcher",
                    to_agent=f"day_{day_num}",
                    phase=NegotiationPhase.NEGOTIATE,
                    proposal={
                        "conflict_type": conflict.get("type", ""),
                        "conflict_description": conflict.get("description", ""),
                        "iteration": iteration + 1,
                        "day": day_num,
                    },
                    utility={"dispatcher": max(0.8 - iteration * 0.1, 0.3)},
                    route_preview=build_route_preview(
                        vehicle_id=f"day{day_num}",
                        coordinates=[],
                    ),
                ))

                # 尝试策略1~5（按优先级），一旦某个策略成功就标记 fixed 并继续下一个 conflict
                conflict_fixed = False

                # 策略1：时间平移
                result = strategy_time_shift(current_plans[day_idx], conflict, margin=15)
                if result:
                    adjustments = _build_adjustment_details(plan_before_snapshot, result, "时间平移") if plan_before_snapshot else []
                    current_plans[day_idx] = result
                    negotiation_log.append({
                        "iteration": iteration + 1, "day": day_num,
                        "action": "时间平移",
                        "target": conflict.get("activities", []),
                        "type": conflict.get("type"),
                        "adjustments": adjustments,
                    })
                    await event_bus.publish(session_id, create_negotiation_event(
                        event_type=NegotiationEventType.COUNTER,
                        session_id=session_id,
                        from_agent="dispatcher",
                        to_agent=f"day_{day_num}",
                        phase=NegotiationPhase.NEGOTIATE,
                        proposal={"action": "时间平移", "target": conflict.get("activities", []), "adjustments": adjustments},
                        utility={"dispatcher": 0.85, "vehicle": 0.7},
                        route_preview=build_route_preview(vehicle_id=f"day{day_num}", coordinates=[]),
                    ))
                    conflict_fixed = True

                # 策略2(原策略6)：开放时间适配 - 在时段交换之前执行，确保开放时间冲突被优先修复
                # 增强：对所有冲突类型都尝试开放时间适配（不限于 outside_opening_hours）
                if not conflict_fixed:
                    plan_before_snapshot = copy.deepcopy(current_plans[day_idx])
                    result = strategy_adjust_opening_hours(current_plans[day_idx], conflict)
                    if result:
                        current_plans[day_idx] = result
                        adjustments = _build_adjustment_details(plan_before_snapshot, result, "开放时间适配")
                        negotiation_log.append({
                            "iteration": iteration + 1, "day": day_num,
                            "action": "开放时间适配",
                            "target": conflict.get("activities", []),
                            "type": conflict.get("type"),
                            "adjustments": adjustments,
                        })
                        await event_bus.publish(session_id, create_negotiation_event(
                            event_type=NegotiationEventType.COUNTER,
                            session_id=session_id,
                            from_agent="dispatcher",
                            to_agent=f"day_{day_num}",
                            phase=NegotiationPhase.NEGOTIATE,
                            proposal={"action": "开放时间适配", "target": conflict.get("activities", []), "adjustments": adjustments},
                            utility={"dispatcher": 0.82, "vehicle": 0.78},
                            route_preview=build_route_preview(vehicle_id=f"day{day_num}", coordinates=[]),
                        ))
                        conflict_fixed = True

                # 策略3(原策略2)：时段交换
                if not conflict_fixed:
                    plan_before_snapshot = copy.deepcopy(current_plans[day_idx])
                    result = strategy_swap_time_slot(current_plans[day_idx], conflict)
                    if result:
                        current_plans[day_idx] = result
                        adjustments = _build_adjustment_details(plan_before_snapshot, result, "时段交换") if plan_before_snapshot else []
                        negotiation_log.append({
                            "iteration": iteration + 1, "day": day_num,
                            "action": "时段交换",
                            "target": conflict.get("activities", []),
                            "type": conflict.get("type"),
                            "adjustments": adjustments
                        })
                        await event_bus.publish(session_id, create_negotiation_event(
                            event_type=NegotiationEventType.COUNTER,
                            session_id=session_id,
                            from_agent="dispatcher",
                            to_agent=f"day_{day_num}",
                            phase=NegotiationPhase.NEGOTIATE,
                            proposal={"action": "时段交换", "target": conflict.get("activities", []), "adjustments": adjustments},
                            utility={"dispatcher": 0.8, "vehicle": 0.75},
                            route_preview=build_route_preview(vehicle_id=f"day{day_num}", coordinates=[]),
                        ))
                        conflict_fixed = True

                # 策略4(原策略3)：时长压缩
                if not conflict_fixed:
                    plan_before_snapshot = copy.deepcopy(current_plans[day_idx])
                    result = strategy_compress_duration(current_plans[day_idx], conflict)
                    if result:
                        current_plans[day_idx] = result
                        adjustments = _build_adjustment_details(plan_before_snapshot, result, "时长压缩") if plan_before_snapshot else []
                        negotiation_log.append({
                            "iteration": iteration + 1, "day": day_num,
                            "action": "时长压缩",
                            "target": conflict.get("activities", []),
                            "type": conflict.get("type"),
                            "adjustments": adjustments
                        })
                        await event_bus.publish(session_id, create_negotiation_event(
                            event_type=NegotiationEventType.COUNTER,
                            session_id=session_id,
                            from_agent="dispatcher",
                            to_agent=f"day_{day_num}",
                            phase=NegotiationPhase.NEGOTIATE,
                            proposal={"action": "时长压缩", "target": conflict.get("activities", []), "adjustments": adjustments},
                            utility={"dispatcher": 0.75, "vehicle": 0.6},
                        ))
                        conflict_fixed = True

                # 策略5(原策略4)：活动替换
                if not conflict_fixed and backup_attractions:
                    plan_before_snapshot = copy.deepcopy(current_plans[day_idx])
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
                        await event_bus.publish(session_id, create_negotiation_event(
                            event_type=NegotiationEventType.COUNTER,
                            session_id=session_id,
                            from_agent="dispatcher",
                            to_agent=f"day_{day_num}",
                            phase=NegotiationPhase.NEGOTIATE,
                            proposal={"action": "活动替换", "target": conflict.get("activities", [])},
                            utility={"dispatcher": 0.7, "vehicle": 0.5},
                        ))
                        conflict_fixed = True

                # 策略6(原策略5)：跨天移动（需要多天）
                if not conflict_fixed and len(current_plans) > 1:
                    plans_before_snapshot = copy.deepcopy(current_plans)
                    result = strategy_cross_day_move(current_plans, conflict)
                    if result:
                        adjustments = []
                        for d_idx in range(len(current_plans)):
                            old_plan = plans_before_snapshot[d_idx] if d_idx < len(plans_before_snapshot) else {}
                            new_plan = result[d_idx] if d_idx < len(result) else {}
                            adj = _build_adjustment_details(old_plan, new_plan, "跨天移动")
                            adjustments.extend(adj)
                        current_plans = result
                        negotiation_log.append({
                            "iteration": iteration + 1,
                            "action": "跨天移动",
                            "target": conflict.get("activities", []),
                            "type": conflict.get("type"),
                            "adjustments": adjustments
                        })
                        await event_bus.publish(session_id, create_negotiation_event(
                            event_type=NegotiationEventType.COUNTER,
                            session_id=session_id,
                            from_agent="dispatcher",
                            to_agent="all_vehicles",
                            phase=NegotiationPhase.NEGOTIATE,
                            proposal={"action": "跨天移动", "target": conflict.get("activities", [])},
                            utility={"dispatcher": 0.65, "vehicle": 0.55},
                        ))
                        conflict_fixed = True

                # 策略7(原策略6→已移至策略2)：此位置的开放时间适配已被移除并前置到策略2
                # 组合修复：当单一策略失败时，尝试"压缩+平移"、"时段交换+平移"等组合策略
                if not conflict_fixed:
                    # 组合策略A: 压缩 + 平移
                    combined_plan_a = copy.deepcopy(current_plans[day_idx])
                    combined_result_a = strategy_compress_duration(combined_plan_a, conflict)
                    if combined_result_a:
                        # 对压缩后的结果再尝试时间平移
                        combined_result_a = strategy_time_shift(combined_result_a, conflict, margin=15)
                        if combined_result_a:
                            current_plans[day_idx] = combined_result_a
                            adjustments = _build_adjustment_details(plan_before_snapshot, combined_result_a, "组合修复(压缩+平移)") # type:ignore
                            negotiation_log.append({
                                "iteration": iteration + 1, "day": day_num,
                                "action": "组合修复(压缩+平移)",
                                "target": conflict.get("activities", []),
                                "type": conflict.get("type"),
                                "adjustments": adjustments
                            })
                            await event_bus.publish(session_id, create_negotiation_event(
                                event_type=NegotiationEventType.COUNTER,
                                session_id=session_id,
                                from_agent="dispatcher",
                                to_agent=f"day_{day_num}",
                                phase=NegotiationPhase.NEGOTIATE,
                                proposal={"action": "组合修复(压缩+平移)", "target": conflict.get("activities", [])},
                                utility={"dispatcher": 0.5, "vehicle": 0.45},
                                route_preview=build_route_preview(vehicle_id=f"day{day_num}", coordinates=[]),
                            ))
                            conflict_fixed = True

                # 组合策略B: 时段交换 + 平移
                if not conflict_fixed:
                    combined_plan_b = copy.deepcopy(current_plans[day_idx])
                    combined_result_b = strategy_swap_time_slot(combined_plan_b, conflict)
                    if combined_result_b:
                        # 对时段交换后的结果再尝试时间平移
                        combined_result_b = strategy_time_shift(combined_result_b, conflict, margin=15)
                        if combined_result_b:
                            current_plans[day_idx] = combined_result_b
                            adjustments = _build_adjustment_details(plan_before_snapshot, combined_result_b, "组合修复(时段交换+平移)") # type:ignore
                            negotiation_log.append({
                                "iteration": iteration + 1, "day": day_num,
                                "action": "组合修复(时段交换+平移)",
                                "target": conflict.get("activities", []),
                                "type": conflict.get("type"),
                                "adjustments": adjustments
                            })
                            await event_bus.publish(session_id, create_negotiation_event(
                                event_type=NegotiationEventType.COUNTER,
                                session_id=session_id,
                                from_agent="dispatcher",
                                to_agent=f"day_{day_num}",
                                phase=NegotiationPhase.NEGOTIATE,
                                proposal={"action": "组合修复(时段交换+平移)", "target": conflict.get("activities", [])},
                                utility={"dispatcher": 0.48, "vehicle": 0.42},
                                route_preview=build_route_preview(vehicle_id=f"day{day_num}", coordinates=[]),
                            ))
                            conflict_fixed = True

                # 策略8(原策略7)：闭馆日解决（针对 closed_day，需要多天行程序）
                if not conflict_fixed and len(current_plans) > 1:
                    conflict_type = conflict.get("type", "")
                    if conflict_type == "closed_day":
                        plans_before_snapshot = copy.deepcopy(current_plans)
                        result = strategy_closed_day_resolve(
                            current_plans, conflict, structured_requirement
                        )
                        if result:
                            adjustments = []
                            for d_idx in range(len(current_plans)):
                                old_plan = plans_before_snapshot[d_idx] if d_idx < len(plans_before_snapshot) else {}
                                new_plan = result[d_idx] if d_idx < len(result) else {}
                                adj = _build_adjustment_details(old_plan, new_plan, "闭馆日解决")
                                adjustments.extend(adj)
                            current_plans = result
                            negotiation_log.append({
                                "iteration": iteration + 1,
                                "action": "闭馆日解决",
                                "target": conflict.get("activities", []),
                                "type": conflict.get("type"),
                                "adjustments": adjustments,
                            })
                            await event_bus.publish(session_id, create_negotiation_event(
                                event_type=NegotiationEventType.COUNTER,
                                session_id=session_id,
                                from_agent="dispatcher",
                                to_agent="all_vehicles",
                                phase=NegotiationPhase.NEGOTIATE,
                                proposal={"action": "闭馆日解决", "target": conflict.get("activities", [])},
                                utility={"dispatcher": 0.55, "vehicle": 0.6},
                            ))
                            conflict_fixed = True

                # 策略9(原策略8)：交通段拆分（针对 time_overlap 中交通与餐饮重叠）
                if not conflict_fixed:
                    conflict_type = conflict.get("type", "")
                    if conflict_type == "time_overlap":
                        conflict_activities = conflict.get("activities", [])
                        # 检查是否包含交通活动和餐饮活动
                        transport = current_plans[day_idx].get("transport")
                        if isinstance(transport, dict):
                            transport_name = f"前往{transport.get('to', '')}"
                            meals = current_plans[day_idx].get("meals", [])
                            for meal in meals:
                                if isinstance(meal, dict):
                                    meal_name = meal.get("name", "")
                                    if transport_name in conflict_activities and meal_name in conflict_activities:
                                        plan_before_snapshot = copy.deepcopy(current_plans[day_idx])
                                        result = strategy_transport_split(current_plans[day_idx], conflict)
                                        if result:
                                            current_plans[day_idx] = result
                                            adjustments = _build_adjustment_details(plan_before_snapshot, result, "交通段拆分")
                                            negotiation_log.append({
                                                "iteration": iteration + 1, "day": day_num,
                                                "action": "交通段拆分",
                                                "target": conflict.get("activities", []),
                                                "type": conflict.get("type"),
                                                "adjustments": adjustments,
                                            })
                                            await event_bus.publish(session_id, create_negotiation_event(
                                                event_type=NegotiationEventType.COUNTER,
                                                session_id=session_id,
                                                from_agent="dispatcher",
                                                to_agent=f"day_{day_num}",
                                                phase=NegotiationPhase.NEGOTIATE,
                                                proposal={"action": "交通段拆分", "target": conflict.get("activities", []), "adjustments": adjustments},
                                                utility={"dispatcher": 0.6, "vehicle": 0.55},
                                            ))
                                            conflict_fixed = True
                                        break

                # 策略11(新增)：地理距离拆分 - 将远距离景点跨天移动
                if not conflict_fixed:
                    conflict_type = conflict.get("type", "")
                    if conflict_type in ("geo_distance",) and len(current_plans) > 1:
                        plans_before_snapshot = copy.deepcopy(current_plans)
                        result = strategy_geo_distance_split(
                            current_plans, conflict, structured_requirement
                        )
                        if result:
                            adjustments = []
                            for d_idx in range(len(current_plans)):
                                old_plan = plans_before_snapshot[d_idx] if d_idx < len(plans_before_snapshot) else {}
                                new_plan = result[d_idx] if d_idx < len(result) else {}
                                adj = _build_adjustment_details(old_plan, new_plan, "地理距离拆分")
                                adjustments.extend(adj)
                            current_plans = result
                            negotiation_log.append({
                                "iteration": iteration + 1,
                                "action": "地理距离拆分",
                                "target": conflict.get("activities", []),
                                "type": conflict.get("type"),
                                "adjustments": adjustments,
                            })
                            await event_bus.publish(session_id, create_negotiation_event(
                                event_type=NegotiationEventType.COUNTER,
                                session_id=session_id,
                                from_agent="dispatcher",
                                to_agent="all_vehicles",
                                phase=NegotiationPhase.NEGOTIATE,
                                proposal={"action": "地理距离拆分", "target": conflict.get("activities", [])},
                                utility={"dispatcher": 0.58, "vehicle": 0.5},
                            ))
                            conflict_fixed = True

                # 策略12(新增)：地理距离替换 - 用备选景点替换远距离景点
                if not conflict_fixed and backup_attractions:
                    conflict_type = conflict.get("type", "")
                    if conflict_type in ("geo_distance",):
                        plan_before_snapshot = copy.deepcopy(current_plans[day_idx])
                        result = strategy_geo_distance_replace(
                            current_plans[day_idx], conflict, backup_attractions
                        )
                        if result:
                            current_plans[day_idx] = result
                            adjustments = _build_adjustment_details(plan_before_snapshot, result, "地理距离替换")
                            negotiation_log.append({
                                "iteration": iteration + 1, "day": day_num,
                                "action": "地理距离替换",
                                "target": conflict.get("activities", []),
                                "type": conflict.get("type"),
                                "adjustments": adjustments,
                            })
                            await event_bus.publish(session_id, create_negotiation_event(
                                event_type=NegotiationEventType.COUNTER,
                                session_id=session_id,
                                from_agent="dispatcher",
                                to_agent=f"day_{day_num}",
                                phase=NegotiationPhase.NEGOTIATE,
                                proposal={"action": "地理距离替换", "target": conflict.get("activities", [])},
                                utility={"dispatcher": 0.5, "vehicle": 0.45},
                            ))
                            conflict_fixed = True

                if conflict_fixed:
                    any_fixed = True

        if not any_fixed:
            # === 改进的终止条件 ===
            # 记录本轮无修复
            no_fix_streak = getattr(negotiate_and_fix, "_no_fix_streak", 0) + 1
            negotiate_and_fix._no_fix_streak = no_fix_streak #type: ignore

            # 检测是否仍有error冲突
            current_v = check_itinerary_conflicts(current_plans, structured_requirement)
            has_remaining_errors = any(c.get("severity") == "error" for c in current_v.get("conflicts", []))

            if has_remaining_errors and no_fix_streak == 1:
                # 第一轮无修复时，不直接终止，先触发全局重排（按地理分区重新分配）
                logger.info(f"[协商] 第{iteration + 1}轮无修复，触发全局重排尝试...")
                _global_reshuffle(current_plans, structured_requirement)
                negotiation_log.append({
                    "iteration": iteration + 1,
                    "action": "全局重排（无有效局部修复策略）"
                })
                await event_bus.publish(session_id, create_negotiation_event(
                    event_type=NegotiationEventType.COUNTER,
                    session_id=session_id,
                    from_agent="dispatcher",
                    to_agent="all_vehicles",
                    phase=NegotiationPhase.NEGOTIATE,
                    proposal={"action": "全局重排（按地理聚类重新分配）"},
                    utility={"dispatcher": 0.35, "vehicle": 0.35},
                ))
            elif has_remaining_errors and no_fix_streak >= 2:
                # 连续两轮无任何修复且仍有error冲突，触发终止
                logger.warning(f"[协商] 第{iteration + 1}轮无任何修复（连续{no_fix_streak}轮），提前终止")
                negotiation_log.append({
                    "iteration": iteration + 1,
                    "action": f"提前终止（连续{no_fix_streak}轮无有效修复策略）"
                })
                await event_bus.publish(session_id, create_negotiation_event(
                    event_type=NegotiationEventType.REJECT,
                    session_id=session_id,
                    from_agent="dispatcher",
                    to_agent="all_vehicles",
                    phase=NegotiationPhase.FINALIZING,
                    proposal={"reason": f"连续{no_fix_streak}轮无有效修复策略"},
                    utility={"dispatcher": 0.3, "vehicle": 0.3},
                ))
                break
            else:
                # 无error冲突，继续迭代
                logger.info(f"[协商] 第{iteration + 1}轮无修复，但已无error冲突，继续迭代")
        else:
            # 有修复，重置连续无修复计数
            negotiate_and_fix._no_fix_streak = 0  # type: ignore

        # 验证修复效果
        remaining = len(check_itinerary_conflicts(current_plans, structured_requirement)
                        .get("conflicts", []))
        logger.info(f"[协商] 第{iteration + 1}轮后剩余 {remaining} 个冲突")

    # 最终校验
    final_v = check_itinerary_conflicts(current_plans, structured_requirement)
    final_error = any(c.get("severity") == "error" for c in final_v.get("conflicts", []))

    # 收集最终 long_distance_warnings（增强：检查所有路段交通耗时是否超过阈值）
    transport_time_threshold = structured_requirement.get("transport_time_threshold_min", 90)
    final_long_distance_warnings = []
    for d_idx, plan in enumerate(current_plans):
        attrs = plan.get("attractions", [])
        for i in range(len(attrs) - 1):
            loc_i = attrs[i].get("location", {})
            loc_j = attrs[i+1].get("location", {})
            dist = _haversine_distance(loc_i, loc_j)
            # 估算交通耗时（按25km/h公交速度，与 get_real_transport_time fallback保持一致）
            estimated_duration_min = int((dist / 25) * 60) if dist < float('inf') else 999
            if estimated_duration_min > transport_time_threshold:
                final_long_distance_warnings.append({
                    "day": d_idx + 1,
                    "from": attrs[i].get("name", ""),
                    "to": attrs[i+1].get("name", ""),
                    "distance_km": round(dist, 1),
                    "estimated_duration_min": estimated_duration_min,
                    "threshold_min": transport_time_threshold,
                })

    # 发布最终完成事件
        await event_bus.publish(session_id, create_negotiation_event(
        event_type=NegotiationEventType.FINALIZED,
        session_id=session_id,
        from_agent="dispatcher",
        to_agent="all_vehicles",
        phase=NegotiationPhase.FINALIZED,
        proposal={
            "fully_resolved": not final_error,
            "final_conflicts": len(final_v.get("conflicts", [])),
            "long_distance_warnings": final_long_distance_warnings,
        },
        extra={"longDistanceWarning": len(final_long_distance_warnings) > 0},
        utility=compute_utility_dict(current_plans, structured_requirement),
    ))

    # ========== 【新增】最终通知所有Agent ==========
    final_responses = await agent_message_bus.broadcast(
        from_agent="dispatcher",
        message={
            "type": AgentMessageType.SCHEDULE_PROPOSAL,
            "payload": {
                "action": "negotiation_complete",
                "session_id": session_id,
                "fully_resolved": not final_error,
                "total_conflicts": len(final_v.get("conflicts", [])),
                "final_plans_count": len(current_plans),
            }
        },
        session_id=session_id,
    )
    negotiation_log.append({
        "iteration": max_iterations,
        "action": "广播协商完成",
        "fully_resolved": not final_error,
        "agent_responses": list(final_responses.keys()) if final_responses else [],
    })

    return {
        "day_plans": current_plans,
        "negotiation_log": negotiation_log,
        "iteration_count": max_iterations,
        "fully_resolved": not final_error,
        "validation": final_v,
        "negotiation_events": event_bus.get_session_log(session_id),
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

    # 第2步：收集备选数据（在路线优化/协商之前收集，确保收集的是原始数据）
    backup = _collect_backup_data(agent_results, structured_requirement)

    # 第3步：多轮协商（将路线优化作为协商修复流程的一部分，在每轮迭代中执行）
    #   这样做的好处：
    #   - 路线优化和冲突修复交替进行，优化后的时间分配不会在后续协商中被重写
    #   - 如果路线优化产生了新冲突，同一次迭代中立即修复
    #   - 优化结果（景点排序）可以指导协商策略更精确地调整时间
    logger.info("[协商] 第2步: 多轮协商修复（含路线优化）")

    # 【P1增强】确保策略选择器已注册
    if strategy_selector.registry.strategy_count == 0:
        register_default_strategies(strategy_selector)
        logger.info(f"[协商] 已在入口注册{strategy_selector.registry.strategy_count}个策略")
    result = await negotiate_and_fix(
        day_plans,
        structured_requirement,
        backup,
        max_iterations=5,
        optimize_route=optimize_route,
        use_real_traffic=use_real_traffic,
    )

    return {
        "day_plans": result["day_plans"],
        "negotiation": {
            "log": result.get("negotiation_log", []),
            "iteration_count": result.get("iteration_count", 0),
            "fully_resolved": result.get("fully_resolved", False),
        },
        "route_optimization_applied": optimize_route,
        "final_validation": result.get("validation", {})
    }


def _simple_route_optimize(day_plan: dict) -> dict:
    """简版路线优化（按纬度排序，复用原有逻辑），支持远距离警告"""
    plan = copy.deepcopy(day_plan)
    attractions = plan.get("attractions", [])
    valid = [a for a in attractions if isinstance(a, dict)]
    plan["attractions"] = sorted(
        valid,
        key=lambda x: x.get("location", {}).get("lat", 0)
        if isinstance(x.get("location"), dict) else 0
    )
    # 检查远距离路段（增强：同时检查直线距离估算的交通耗时是否超过阈值）
    long_distance_warnings = []
    transport_time_threshold_min = 90  # 默认90分钟
    attrs = plan["attractions"]
    for i in range(len(attrs) - 1):
        loc_i = attrs[i].get("location", {})
        loc_j = attrs[i+1].get("location", {})
        dist = _haversine_distance(loc_i, loc_j)
        # 估算交通耗时（25km/h公交速度）
        estimated_duration_min = int((dist / 25) * 60) if dist < float('inf') else 999
        if estimated_duration_min > transport_time_threshold_min:
            long_distance_warnings.append({
                "from": attrs[i].get("name", ""),
                "to": attrs[i+1].get("name", ""),
                "distance_km": round(dist, 1),
                "estimated_duration_min": estimated_duration_min,
                "threshold_min": transport_time_threshold_min,
            })
    if long_distance_warnings:
        plan["_long_distance_warnings"] = long_distance_warnings
    return plan


def _collect_backup_data(agent_results: dict, structured_requirement: dict) -> dict:
    """
    收集未使用的备选景点数据（增强版：支持从静态数据中获取兜底备选）

    计算逻辑：
      1. 统计景点智能体返回的所有景点
      2. 根据 integrate_agent_results_to_daily_plans 中的分配逻辑，
         每个 slot（morning/afternoon/evening）分配到 per_day 个景点，
         但 per_day 受限于实际景点数。因此实际使用数 = 各 slot 的 per_day 之和 * travel_days。
      3. 实际使用数取 per_day 之和 * travel_days，但不会超过各 slot 实际拥有的景点数。
      4. 剩余景点作为备选，供策略4（活动替换）使用。
      5. 如果智能体返回的景点不足导致无备选，尝试从静态数据中获取同城市其他景点，
         或从所有智能体返回结果中按评分排序取前N个作为强制备选。
    """
    attractions = agent_results.get("attraction", {}).get("attractions", [])
    if not attractions:
        return {"attractions": []}

    travel_days = structured_requirement.get("travel_days", 1)

    # 统计各 time_slot 的景点数
    morning_attrs = [a for a in attractions if isinstance(a, dict) and a.get("visit_time_slot") == "morning"]
    afternoon_attrs = [a for a in attractions if isinstance(a, dict) and a.get("visit_time_slot") == "afternoon"]
    evening_attrs = [a for a in attractions if isinstance(a, dict) and a.get("visit_time_slot") == "evening"]

    # 计算每个 slot 每天分配的景点数（与 integrate_agent_results_to_daily_plans 逻辑一致）
    def calc_per_day(slot_list):
        if not slot_list:
            return 0
        per_day = max(1, len(slot_list) // travel_days) if slot_list else 0
        total_needed = per_day * travel_days
        if total_needed > len(slot_list):
            return max(1, len(slot_list) // travel_days)
        return per_day

    per_day_morning = calc_per_day(morning_attrs)
    per_day_afternoon = calc_per_day(afternoon_attrs)
    per_day_evening = calc_per_day(evening_attrs)

    # 实际使用的景点总数
    used_count = (per_day_morning + per_day_afternoon + per_day_evening) * travel_days

    # 如果实际使用数超出景点总数，说明景点不够，没有备选
    if used_count >= len(attractions):
            logger.warning(f"[协商] 景点全部用完（{len(attractions)}个），无备选可用")

            # === 增强：强制生成备选列表 ===
            # 方法1：从所有景点中按评分排序取前N个作为备选
            scored_attrs = sorted(
                [a for a in attractions if isinstance(a, dict) and a.get("rating")],
                key=lambda x: float(x.get("rating", 0) or 0),
                reverse=True
            )
            if scored_attrs:
                forced_backup = scored_attrs[:max(1, len(scored_attrs) // 3)]
                backup_attrs = copy.deepcopy(forced_backup)
                logger.info(f"[协商] 强制生成 {len(backup_attrs)} 个备选景点（按评分排序）")
                return {"attractions": backup_attrs}

            # 方法2：从未使用的同类型景点中选取（来自其他智能体返回结果）
            other_agent_attractions = []
            for agent_key in ['hotel', 'food', 'transport']:
                agent_data = agent_results.get(agent_key, {})
                if isinstance(agent_data, dict):
                    for key in ['attractions', 'nearby_attractions', 'recommendations', 'suggested_spots']:
                        items = agent_data.get(key, [])
                        if isinstance(items, list):
                            for item in items:
                                if isinstance(item, dict) and item.get("name"):
                                    other_agent_attractions.append(item)

            if other_agent_attractions:
                sorted_others = sorted(
                    other_agent_attractions,
                    key=lambda x: float(x.get("rating", 0) or 0),
                    reverse=True
                )
                backup_attrs = copy.deepcopy(sorted_others[:max(3, len(sorted_others) // 2)])
                logger.info(f"[协商] 从其他智能体结果中获取 {len(backup_attrs)} 个强制备选景点")
                return {"attractions": backup_attrs}

            # 方法3：如果前两种都为空，复制所有已用景点中评分最高的作为备选
            logger.warning(f"[协商] 无法生成强制备选，将已使用景点中评分高的复制为备选")
            used_attrs = attractions[:min(used_count, len(attractions))]
            sorted_used = sorted(
                used_attrs,
                key=lambda x: float(x.get("rating", 0) or 0),
                reverse=True
            ) if used_attrs else attractions
            if sorted_used:
                backup_attrs = copy.deepcopy(sorted_used[:max(2, len(sorted_used) // 2)])
                logger.info(f"[协商] 从已用景点复制 {len(backup_attrs)} 个作为强制备选")
                return {"attractions": backup_attrs}

            return {"attractions": []}

    backup_attrs = attractions[used_count:]
    logger.info(f"[协商] 收集到 {len(backup_attrs)} 个备选景点（已使用 {used_count} 个）")
    return {
            "attractions": backup_attrs
        }