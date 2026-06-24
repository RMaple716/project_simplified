"""src/services/negotiation_core/conflict_checkers.py"""
"""
冲突检测函数模块

将 check_itinerary_conflicts() 中的 8 个检测维度拆分为独立函数。
每个函数接收 day_plans 列表和可选阈值参数，返回标准化的冲突列表。

所有阈值参数在文件顶部定义为 DEFAULT_* 常量，函数签名中通过具名 kwargs 传参。
"""

import math
import datetime as _dt
from typing import List, Dict, Any, Optional

# 从 validate.py 复用工具函数
from src.routes.validate import (
    parse_time_to_minutes,
    parse_duration_to_minutes,
    format_minutes,
    check_time_overlap,
    check_attraction_opening_hours,
)

# ============================================================
# 默认阈值常量
# ============================================================

DEFAULT_GEO_DISTANCE_ERROR_KM = 30.0
DEFAULT_GEO_DISTANCE_WARNING_KM = 15.0
DEFAULT_TRANSPORT_TIME_THRESHOLD_MIN = 90
DEFAULT_MAX_DAILY_DURATION_MIN = 720
DEFAULT_MIN_VISIT_DURATION_MIN = 30
DEFAULT_MAX_VISIT_DURATION_MIN = 240

# 用餐时间范围（分钟，从午夜0点起算）
DEFAULT_BREAKFAST_RANGE = (420, 540)    # 07:00-09:00
DEFAULT_LUNCH_RANGE = (690, 810)        # 11:30-13:30
DEFAULT_DINNER_RANGE = (1020, 1170)     # 17:00-19:30


# ============================================================
# 辅助函数
# ============================================================

def _collect_daily_activities(day_plan: dict) -> List[dict]:
    """
    从一天的行程计划中收集所有活动并格式化为统一结构
    """
    activities = []

    for attraction in day_plan.get("attractions", []):
        if not isinstance(attraction, dict):
            continue
        activities.append({
            "name": attraction.get("name", "未知景点"),
            "start_time": attraction.get("start_time") or attraction.get("visit_time", "上午"),
            "end_time": attraction.get("end_time"),
            "duration": attraction.get("visit_duration", "2小时"),
            "activity_type": "attraction",
            "location": attraction.get("address", ""),
            "cost": attraction.get("ticket_price", 0) if isinstance(attraction.get("ticket_price"), (int, float)) else 0
        })

    for meal in day_plan.get("meals", []):
        if not isinstance(meal, dict):
            continue
        activities.append({
            "name": meal.get("name", "用餐"),
            "start_time": meal.get("start_time") or meal.get("time") or meal.get("meal_time", "中午"),
            "end_time": meal.get("end_time"),
            "duration": meal.get("duration", "1小时"),
            "activity_type": "meal",
            "location": meal.get("address", ""),
            "cost": meal.get("avg_price_per_person", 0) if isinstance(meal.get("avg_price_per_person"), (int, float)) else 0
        })

    if day_plan.get("transport"):
        transport = day_plan["transport"]
        if isinstance(transport, dict):
            activities.append({
                "name": f"前往{transport.get('to', '目的地')}",
                "start_time": transport.get("departure_time", "上午"),
                "duration": transport.get("duration", "1小时"),
                "activity_type": "transport",
                "location": "",
                "cost": transport.get("price", 0) if isinstance(transport.get("price"), (int, float)) else 0
            })

    return activities


def _extract_location(attraction) -> tuple:
    """从景点字典中提取 (lat, lng) 坐标"""
    if not isinstance(attraction, dict):
        return (None, None)
    loc: dict = attraction.get("location") if isinstance(attraction.get("location"), dict) else {} #type: ignore
    lat = loc.get("lat")
    lng = loc.get("lng")
    if lat is not None and lng is not None:
        try:
            return (float(lat), float(lng))
        except (TypeError, ValueError):
            return (None, None)
    return (None, None)


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """计算两点之间的大圆距离（km）"""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _make_meal_conflict(
    meal_name: str,
    meal_type: str,
    start_m: int,
    end_m: int,
    expected_range: tuple,
    day_num: int,
    date: str,
) -> dict:
    """构造用餐时间冲突记录"""
    type_labels = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}
    label = type_labels.get(meal_type, meal_type)
    return {
        "type": "unreasonable_meal_time",
        "description": (
            f"{label}'{meal_name}' 安排在 {format_minutes(start_m)}-{format_minutes(end_m)}，"
            f"不在合理{label}时间段（{format_minutes(expected_range[0])}-{format_minutes(expected_range[1])}）内"
        ),
        "severity": "warning",
        "day": day_num,
        "date": date,
        "activities": [meal_name],
        "meal_type": meal_type,
        "expected_range": f"{format_minutes(expected_range[0])}-{format_minutes(expected_range[1])}",
    }


# ============================================================
# 8 个独立检测函数
# ============================================================

def check_time_overlaps(day_plans: List[dict], **kwargs) -> List[dict]:
    """检测时间重叠（维度1）"""
    all_conflicts = []

    for day_idx, day_plan in enumerate(day_plans):
        day_num = day_idx + 1
        date = day_plan.get("date", f"第{day_num}天")

        daily_activities = _collect_daily_activities(day_plan)
        if not daily_activities:
            continue

        from src.routes.validate import detect_time_conflicts
        day_result = detect_time_conflicts(daily_activities)
        for conflict in day_result["conflicts"]:
            conflict["day"] = day_num
            conflict["date"] = date
            all_conflicts.append(conflict)

    return all_conflicts


def check_geo_distances(
    day_plans: List[dict],
    error_threshold_km: float = DEFAULT_GEO_DISTANCE_ERROR_KM,
    warning_threshold_km: float = DEFAULT_GEO_DISTANCE_WARNING_KM,
    **kwargs
) -> List[dict]:
    """检测地理距离（维度2）"""
    all_conflicts = []

    for day_idx, day_plan in enumerate(day_plans):
        day_num = day_idx + 1
        attractions = day_plan.get("attractions", [])
        if len(attractions) < 2:
            continue

        for i in range(len(attractions) - 1):
            a = attractions[i]
            b = attractions[i + 1]
            lat1, lng1 = _extract_location(a)
            lat2, lng2 = _extract_location(b)

            if None not in (lat1, lng1, lat2, lng2):
                dist_km = _haversine(lat1, lng1, lat2, lng2)

                if dist_km > error_threshold_km:
                    all_conflicts.append({
                        "type": "geo_distance",
                        "description": (
                            f"第{day_num}天「{a.get('name', '')}」到「{b.get('name', '')}」"
                            f"直线距离约{dist_km:.0f}公里，超过{int(error_threshold_km)}公里，交通耗时过长"
                        ),
                        "severity": "error",
                        "day": day_num,
                        "activities": [a.get("name", ""), b.get("name", "")],
                        "distance_km": round(dist_km, 1),
                        "suggestion": f"第{day_num}天「{a.get('name', '')}」和「{b.get('name', '')}」相距过远，建议分开到不同天游览或替换其中一景点",
                    })
                elif dist_km > warning_threshold_km:
                    all_conflicts.append({
                        "type": "geo_distance_warning",
                        "description": (
                            f"第{day_num}天「{a.get('name', '')}」到「{b.get('name', '')}」"
                            f"直线距离约{dist_km:.0f}公里，建议确认交通方案"
                        ),
                        "severity": "warning",
                        "day": day_num,
                        "activities": [a.get("name", ""), b.get("name", "")],
                        "distance_km": round(dist_km, 1),
                    })

    return all_conflicts


def check_overloaded_day(
    day_plans: List[dict],
    max_daily_duration_min: int = DEFAULT_MAX_DAILY_DURATION_MIN,
    **kwargs
) -> List[dict]:
    """检测日程过满（维度3）"""
    all_conflicts = []

    for day_idx, day_plan in enumerate(day_plans):
        day_num = day_idx + 1
        date = day_plan.get("date", f"第{day_num}天")

        daily_activities = _collect_daily_activities(day_plan)
        if not daily_activities:
            continue

        time_ranges = []
        for act in daily_activities:
            start_minutes = parse_time_to_minutes(act.get("start_time", "上午"))
            duration_str = act.get("duration", "2小时")
            duration_minutes = parse_duration_to_minutes(duration_str)
            end_minutes = start_minutes + duration_minutes
            time_ranges.append((start_minutes, end_minutes, act["name"]))

        if not time_ranges:
            continue

        day_start = min(r[0] for r in time_ranges)
        day_end = max(r[1] for r in time_ranges)
        total_duration = day_end - day_start

        if total_duration > max_daily_duration_min:
            total_hours = total_duration / 60
            max_hours = max_daily_duration_min / 60
            all_conflicts.append({
                "type": "overloaded_day",
                "description": (
                    f"当日行程总时长 {total_hours:.1f} 小时，"
                    f"建议不超过{max_hours:.0f}小时"
                ),
                "severity": "warning",
                "day": day_num,
                "date": date,
                "activities": [r[2] for r in time_ranges],
                "total_minutes": total_duration,
            })

    return all_conflicts


def check_visit_durations(
    day_plans: List[dict],
    min_duration_min: int = DEFAULT_MIN_VISIT_DURATION_MIN,
    max_duration_min: int = DEFAULT_MAX_VISIT_DURATION_MIN,
    **kwargs
) -> List[dict]:
    """检测游览时长（维度4）"""
    all_conflicts = []

    for day_idx, day_plan in enumerate(day_plans):
        day_num = day_idx + 1
        date = day_plan.get("date", f"第{day_num}天")

        for attraction in day_plan.get("attractions", []):
            if not isinstance(attraction, dict):
                continue
            name = attraction.get("name", "未知景点")
            start_str = attraction.get("start_time") or attraction.get("visit_time", "上午")
            end_str = attraction.get("end_time")
            duration_str = attraction.get("visit_duration", "2小时")

            start_min = parse_time_to_minutes(start_str)

            if end_str:
                end_min = parse_time_to_minutes(end_str)
            else:
                dur_min = parse_duration_to_minutes(duration_str)
                end_min = start_min + dur_min

            visit_duration = end_min - start_min

            if visit_duration < min_duration_min:
                all_conflicts.append({
                    "type": "visit_duration_too_short",
                    "description": (
                        f"'{name}' 游览时间过短 ({visit_duration}分钟)，"
                        f"建议至少{min_duration_min}分钟"
                    ),
                    "severity": "warning",
                    "day": day_num,
                    "date": date,
                    "activities": [name],
                    "duration_minutes": visit_duration,
                    "suggestion": f"建议增加'{name}'的游览时间至{min_duration_min}分钟以上",
                })
            elif visit_duration > max_duration_min:
                all_conflicts.append({
                    "type": "visit_duration_too_long",
                    "description": (
                        f"'{name}' 游览时间过长 ({visit_duration}分钟)，"
                        f"建议不超过{max_duration_min}分钟"
                    ),
                    "severity": "warning",
                    "day": day_num,
                    "date": date,
                    "activities": [name],
                    "duration_minutes": visit_duration,
                    "suggestion": f"建议减少'{name}'的游览时间或分多天游览",
                })

    return all_conflicts


def check_opening_hours_compliance(day_plans: List[dict], **kwargs) -> List[dict]:
    """检测营业时间（维度5）"""
    all_conflicts = []

    for day_idx, day_plan in enumerate(day_plans):
        day_num = day_idx + 1
        date = day_plan.get("date", f"第{day_num}天")

        for attraction in day_plan.get("attractions", []):
            if not isinstance(attraction, dict):
                continue
            start_str = attraction.get("start_time") or attraction.get("visit_time", "上午")
            start_min = parse_time_to_minutes(start_str)

            duration_str = attraction.get("visit_duration", "2小时")
            dur_min = parse_duration_to_minutes(duration_str)
            end_min = start_min + dur_min

            day_date = date if "-" in str(date) else None
            opening_conflicts = check_attraction_opening_hours(
                attraction, start_min, end_min, day_date=day_date
            )
            for conflict in opening_conflicts:
                conflict["day"] = day_num
                conflict["date"] = date
                all_conflicts.append(conflict)

    return all_conflicts


def check_meal_time_reasonableness(
    day_plans: List[dict],
    breakfast_range: tuple = DEFAULT_BREAKFAST_RANGE,
    lunch_range: tuple = DEFAULT_LUNCH_RANGE,
    dinner_range: tuple = DEFAULT_DINNER_RANGE,
    **kwargs
) -> List[dict]:
    """检测餐饮时间合理性（维度6）"""
    all_conflicts = []

    for day_idx, day_plan in enumerate(day_plans):
        day_num = day_idx + 1
        date = day_plan.get("date", f"第{day_num}天")

        for meal in day_plan.get("meals", []):
            if not isinstance(meal, dict):
                continue

            meal_name = meal.get("name", "用餐")
            meal_start_str = meal.get("start_time") or meal.get("time") or meal.get("meal_time", "中午")
            meal_start_m = parse_time_to_minutes(meal_start_str)
            meal_dur_str = meal.get("duration", "1小时")
            meal_dur_m = parse_duration_to_minutes(meal_dur_str)
            meal_end_m = meal_start_m + meal_dur_m

            meal_type = (meal.get("meal_type") or "").lower()
            meal_time_field = (meal.get("meal_time") or "").lower()
            meal_name_lower = (meal.get("name") or "").lower()

            is_breakfast = any(kw in meal_type or kw in meal_time_field or kw in meal_name_lower
                               for kw in ["breakfast", "早餐", "早上", "早"])
            is_lunch = any(kw in meal_type or kw in meal_time_field or kw in meal_name_lower
                           for kw in ["lunch", "午餐", "中午", "中餐"])
            is_dinner = any(kw in meal_type or kw in meal_time_field or kw in meal_name_lower
                            for kw in ["dinner", "晚餐", "晚上", "晚"])

            if not any([is_breakfast, is_lunch, is_dinner]):
                if 360 <= meal_start_m < 600:
                    is_breakfast = True
                elif 660 <= meal_start_m < 870:
                    is_lunch = True
                elif 990 <= meal_start_m < 1200:
                    is_dinner = True

            if is_breakfast:
                if meal_start_m < breakfast_range[0] or meal_end_m > breakfast_range[1]:
                    all_conflicts.append(
                        _make_meal_conflict(meal_name, "breakfast", meal_start_m, meal_end_m,
                                            breakfast_range, day_num, date)
                    )
            elif is_lunch:
                if meal_start_m < lunch_range[0] or meal_end_m > lunch_range[1]:
                    all_conflicts.append(
                        _make_meal_conflict(meal_name, "lunch", meal_start_m, meal_end_m,
                                            lunch_range, day_num, date)
                    )
            elif is_dinner:
                if meal_start_m < dinner_range[0] or meal_end_m > dinner_range[1]:
                    all_conflicts.append(
                        _make_meal_conflict(meal_name, "dinner", meal_start_m, meal_end_m,
                                            dinner_range, day_num, date)
                    )

    return all_conflicts


def check_long_transport_times(
    day_plans: List[dict],
    transport_time_threshold_min: int = DEFAULT_TRANSPORT_TIME_THRESHOLD_MIN,
    **kwargs
) -> List[dict]:
    """检测交通时长（维度7）"""
    all_conflicts = []

    for day_idx, day_plan in enumerate(day_plans):
        day_num = day_idx + 1
        attractions = day_plan.get("attractions", [])
        if len(attractions) < 2:
            continue

        for i in range(len(attractions) - 1):
            a = attractions[i]
            b = attractions[i + 1]
            lat1, lng1 = _extract_location(a)
            lat2, lng2 = _extract_location(b)

            if None not in (lat1, lng1, lat2, lng2):
                dist_km = _haversine(lat1, lng1, lat2, lng2)
                estimated_duration_min = int((dist_km / 25) * 60)

                if estimated_duration_min > transport_time_threshold_min:
                    all_conflicts.append({
                        "type": "long_distance",
                        "description": (
                            f"第{day_num}天「{a.get('name', '')}」到「{b.get('name', '')}」"
                            f"估算交通时间约{estimated_duration_min}分钟，超过{transport_time_threshold_min}分钟"
                        ),
                        "severity": "warning",
                        "day": day_num,
                        "activities": [a.get("name", ""), b.get("name", "")],
                        "distance_km": round(dist_km, 1),
                        "estimated_duration_min": estimated_duration_min,
                        "suggestion": (
                            f"第{day_num}天「{a.get('name', '')}」和「{b.get('name', '')}」相距"
                            f"{dist_km:.0f}公里，交通耗时约{estimated_duration_min}分钟，"
                            f"建议调整景点顺序或替换"
                        ),
                    })

    return all_conflicts


def check_cross_day_transport(day_plans: List[dict], **kwargs) -> List[dict]:
    """检测跨天交通（维度8）"""
    all_conflicts = []

    if len(day_plans) < 2:
        return all_conflicts

    for day_idx in range(len(day_plans) - 1):
        current_plan = day_plans[day_idx]
        next_plan = day_plans[day_idx + 1]
        day_num = day_idx + 1

        current_attrs = current_plan.get("attractions", [])
        next_attrs = next_plan.get("attractions", [])

        if not current_attrs or not next_attrs:
            continue

        last_attr = current_attrs[-1] if isinstance(current_attrs[-1], dict) else None
        first_attr = next_attrs[0] if isinstance(next_attrs[0], dict) else None

        if not last_attr or not first_attr:
            continue

        lat1, lng1 = _extract_location(last_attr)
        lat2, lng2 = _extract_location(first_attr)

        if None not in (lat1, lng1, lat2, lng2):
            dist_km = _haversine(lat1, lng1, lat2, lng2)
            if dist_km > 30:
                all_conflicts.append({
                    "type": "cross_day_transport",
                    "description": (
                        f"第{day_num}天「{last_attr.get('name', '')}」到"
                        f"第{day_num + 1}天「{first_attr.get('name', '')}」"
                        f"直线距离约{dist_km:.0f}公里，跨天交通距离较远"
                    ),
                    "severity": "warning",
                    "day": day_num,
                    "activities": [last_attr.get("name", ""), first_attr.get("name", "")],
                    "distance_km": round(dist_km, 1),
                    "cross_days": [day_num, day_num + 1],
                })

    return all_conflicts