"""src/services/negotiation_core/conflict_detector.py"""
"""
冲突检测封装模块

将 check_itinerary_conflicts() 的调用封装为独立模块，
标准化输出格式，支持配置检测阈值。

现在通过调用 conflict_checkers.py 中的 8 个独立检测函数
实现具体的冲突检测逻辑，而非直接调用 check_itinerary_conflicts。
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

from .conflict_checkers import (
    check_time_overlaps,
    check_geo_distances,
    check_overloaded_day,
    check_visit_durations,
    check_opening_hours_compliance,
    check_meal_time_reasonableness,
    check_long_transport_times,
    check_cross_day_transport,
    DEFAULT_GEO_DISTANCE_ERROR_KM,
    DEFAULT_GEO_DISTANCE_WARNING_KM,
    DEFAULT_TRANSPORT_TIME_THRESHOLD_MIN,
    DEFAULT_MAX_DAILY_DURATION_MIN,
    DEFAULT_MIN_VISIT_DURATION_MIN,
    DEFAULT_MAX_VISIT_DURATION_MIN,
)

logger = logging.getLogger(__name__)


class ConflictDetectionResult:
    """
    冲突检测结果封装
    
    标准化 output，统一访问方式。
    """
    
    def __init__(self, raw_result: Dict[str, Any]):
        self._raw = raw_result
        self.conflicts: List[Dict[str, Any]] = raw_result.get("conflicts", [])
        self.has_conflict: bool = raw_result.get("has_conflict", False)
        self.has_error: bool = any(
            c.get("severity") == "error" for c in self.conflicts
        )
        self.has_warning: bool = any(
            c.get("severity") == "warning" for c in self.conflicts
        )
    
    def get_errors(self) -> List[Dict[str, Any]]:
        return [c for c in self.conflicts if c.get("severity") == "error"]
    
    def get_warnings(self) -> List[Dict[str, Any]]:
        return [c for c in self.conflicts if c.get("severity") == "warning"]
    
    def get_by_day(self, day_num: int) -> List[Dict[str, Any]]:
        return [c for c in self.conflicts if c.get("day") == day_num]
    
    def get_by_type(self, conflict_type: str) -> List[Dict[str, Any]]:
        return [c for c in self.conflicts if c.get("type") == conflict_type]
    
    def group_by_day(self) -> Dict[int, List[Dict[str, Any]]]:
        groups: Dict[int, List[Dict[str, Any]]] = {}
        for c in self.conflicts:
            day = c.get("day", 1)
            if day not in groups:
                groups[day] = []
            groups[day].append(c)
        return groups
    
    @property
    def error_count(self) -> int:
        return len(self.get_errors())
    
    @property
    def warning_count(self) -> int:
        return len(self.get_warnings())
    
    @property
    def total_count(self) -> int:
        return len(self.conflicts)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_conflict": self.has_conflict,
            "has_error": self.has_error,
            "has_warning": self.has_warning,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "total_count": self.total_count,
            "conflicts": self.conflicts,
        }


# ============================================================
# 辅助函数
# ============================================================

def _extract_thresholds(structured_requirement: dict, **kwargs) -> dict:
    """
    从 structured_requirement 和 kwargs 中提取并合并阈值参数

    优先级: kwargs（最高） > structured_requirement（中） > DEFAULT_* 常量（最低）
    """
    thresholds = {
        "geo_distance_error_km": structured_requirement.get(
            "geo_distance_error_km", DEFAULT_GEO_DISTANCE_ERROR_KM
        ),
        "geo_distance_warning_km": structured_requirement.get(
            "geo_distance_warning_km", DEFAULT_GEO_DISTANCE_WARNING_KM
        ),
        "transport_time_threshold_min": structured_requirement.get(
            "transport_time_threshold_min", DEFAULT_TRANSPORT_TIME_THRESHOLD_MIN
        ),
        "max_daily_duration_min": structured_requirement.get(
            "max_daily_duration_min", DEFAULT_MAX_DAILY_DURATION_MIN
        ),
        "min_visit_duration_min": structured_requirement.get(
            "min_visit_duration_min", DEFAULT_MIN_VISIT_DURATION_MIN
        ),
        "max_visit_duration_min": structured_requirement.get(
            "max_visit_duration_min", DEFAULT_MAX_VISIT_DURATION_MIN
        ),
    }
    # kwargs 显式参数覆盖
    thresholds.update(kwargs)
    return thresholds


def _calc_total_cost(day_plans: List[dict]) -> float:
    """计算所有天的总花费"""
    total = 0.0
    for day_plan in day_plans:
        for attraction in day_plan.get("attractions", []):
            if isinstance(attraction, dict):
                price = attraction.get("ticket_price", 0)
                if isinstance(price, (int, float)):
                    total += price
        for meal in day_plan.get("meals", []):
            if isinstance(meal, dict):
                price = meal.get("avg_price_per_person", 0)
                if isinstance(price, (int, float)):
                    total += price
        transport = day_plan.get("transport", {})
        if isinstance(transport, dict):
            price = transport.get("price", 0)
            if isinstance(price, (int, float)):
                total += price
    return total


# ============================================================
# 主入口
# ============================================================

def detect_conflicts(
    day_plans: List[dict],
    structured_requirement: dict,
    **kwargs
) -> ConflictDetectionResult:
    """
    检测行程中的冲突（通过调用 8 个独立检测函数）

    将原来的 check_itinerary_conflicts() 内联逻辑拆分为：
    1. 调用 8 个独立检测函数
    2. 预算检测（独立处理）
    3. 合并结果并包装为 ConflictDetectionResult

    Args:
        day_plans: 每日行程列表
        structured_requirement: 结构化需求
        **kwargs: 额外的参数（如阈值配置）

    Returns:
        ConflictDetectionResult 实例
    """
    # 1. 提取阈值
    thresholds = _extract_thresholds(structured_requirement, **kwargs)

    # 2. 调用 8 个独立检测函数
    all_conflicts = []

    # 维度1: 时间重叠
    all_conflicts.extend(check_time_overlaps(day_plans, **thresholds))

            # 维度2: 地理距离
    all_conflicts.extend(check_geo_distances(
        day_plans,
        **thresholds,
    ))

    # 维度3: 日程过满
    all_conflicts.extend(check_overloaded_day(
        day_plans,
        **thresholds,
    ))

    # 维度4: 游览时长
    all_conflicts.extend(check_visit_durations(
        day_plans,
        **thresholds,
    ))

    # 维度5: 营业时间
    all_conflicts.extend(check_opening_hours_compliance(day_plans, **thresholds))

    # 维度6: 餐饮时间
    all_conflicts.extend(check_meal_time_reasonableness(day_plans, **thresholds))

    # 维度7: 交通时长
    all_conflicts.extend(check_long_transport_times(
        day_plans,
        **thresholds,
    ))

    # 维度8: 跨天交通
    all_conflicts.extend(check_cross_day_transport(day_plans, **thresholds))

    # 3. 预算检测（独立处理，非维度函数）
    total_cost = _calc_total_cost(day_plans)
    budget = structured_requirement.get("total_budget", 0)
    if budget > 0 and total_cost > budget:
        all_conflicts.append({
            "type": "budget_exceeded",
            "description": f"总花费 {total_cost:.0f} 元超出预算 {budget:.0f} 元",
            "severity": "error",
            "day": 0,
            "activities": [],
        })

    # 4. 构造与 check_itinerary_conflicts 兼容的输出
    has_error = any(c["severity"] == "error" for c in all_conflicts)

    raw_result = {
        "has_conflict": has_error,
        "conflicts": all_conflicts,
        "total_cost": total_cost,
    }

    result = ConflictDetectionResult(raw_result)

    logger.debug(
        f"[冲突检测] 发现 {result.total_count} 个冲突 "
        f"(error={result.error_count}, warning={result.warning_count})"
    )

    return result