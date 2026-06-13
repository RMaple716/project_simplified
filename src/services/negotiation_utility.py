"""
协商效用评估体系 — 多维效用函数

功能:
1. ✅ 计算行程方案的多维效用值
2. ✅ 支持可配置的权重
3. ✅ 支持用户偏好调整
4. ✅ 用于比较不同协商结果，选择最优方案

使用方式:
    from src.services.negotiation_utility import utility_evaluator

    # 计算效用
    utility = utility_evaluator.evaluate(day_plans, structured_requirement)
    # 结果: {"time_rationality": 0.85, "geo_compactness": 0.72, ...}

    # 配置权重
    utility_evaluator.configure_weights({
        "time_rationality": 0.3,
        "geo_compactness": 0.3,
        "budget_conformance": 0.2,
        "preference_match": 0.2,
    })
"""
import math
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ==================== 效用维度定义 ====================

@dataclass
class UtilityWeights:
    """效用权重配置"""
    time_rationality: float = 0.30      # 时间合理性
    geo_compactness: float = 0.25       # 地理紧凑性
    budget_conformance: float = 0.20    # 预算符合度
    preference_match: float = 0.25      # 偏好匹配度

    @classmethod
    def default(cls) -> "UtilityWeights":
        return cls()

    def to_dict(self) -> Dict[str, float]:
        return {
            "time_rationality": self.time_rationality,
            "geo_compactness": self.geo_compactness,
            "budget_conformance": self.budget_conformance,
            "preference_match": self.preference_match,
        }

    def from_dict(self, weights: Dict[str, float]) -> None:
        """从字典更新权重（自动归一化）"""
        for key in ["time_rationality", "geo_compactness", "budget_conformance", "preference_match"]:
            if key in weights:
                setattr(self, key, float(weights[key]))
        self.normalize()

    def normalize(self) -> None:
        """归一化所有权重，使其和为1"""
        total = sum([
            self.time_rationality,
            self.geo_compactness,
            self.budget_conformance,
            self.preference_match,
        ])
        if total > 0:
            self.time_rationality /= total
            self.geo_compactness /= total
            self.budget_conformance /= total
            self.preference_match /= total


@dataclass
class UtilityResult:
    """效用评估结果"""
    # 各维度得分（0~1）
    time_rationality: float = 0.0       # 时间合理性
    geo_compactness: float = 0.0        # 地理紧凑性
    budget_conformance: float = 1.0     # 预算符合度
    preference_match: float = 0.5       # 偏好匹配度
    
    # 综合得分
    overall: float = 0.0
    
    # 详细信息
    details: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def dimensions(self) -> Dict[str, float]:
        return {
            "time_rationality": self.time_rationality,
            "geo_compactness": self.geo_compactness,
            "budget_conformance": self.budget_conformance,
            "preference_match": self.preference_match,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall": round(self.overall, 4),
            "dimensions": {k: round(v, 4) for k, v in self.dimensions.items()},
            "details": self.details,
        }


class UtilityEvaluator:
    """
    效用评估器

    计算行程方案的多维效用值，支持可配置的权重。
    """

    def __init__(self):
        self.weights = UtilityWeights.default()
        logger.info("[效用评估] 初始化完成")

    def configure_weights(self, weights: Dict[str, float]) -> None:
        """
        配置效用权重

        Args:
            weights: 权重字典，可包含 time_rationality, geo_compactness,
                    budget_conformance, preference_match
        """
        self.weights.from_dict(weights)
        logger.info(f"[效用评估] 权重已更新: {self.weights.to_dict()}")

    def get_weights(self) -> Dict[str, float]:
        """获取当前权重配置"""
        return self.weights.to_dict()

    def evaluate(
        self,
        day_plans: List[Dict[str, Any]],
        structured_requirement: Dict[str, Any],
    ) -> UtilityResult:
        """
        计算行程方案的多维效用

        Args:
            day_plans: 每日行程列表
            structured_requirement: 结构化需求

        Returns:
            效用评估结果
        """
        result = UtilityResult()

        # 1. 时间合理性
        time_score, time_details = self._evaluate_time_rationality(
            day_plans, structured_requirement
        )
        result.time_rationality = time_score
        result.details["time_rationality"] = time_details

        # 2. 地理紧凑性
        geo_score, geo_details = self._evaluate_geo_compactness(
            day_plans, structured_requirement
        )
        result.geo_compactness = geo_score
        result.details["geo_compactness"] = geo_details

        # 3. 预算符合度
        budget_score, budget_details = self._evaluate_budget_conformance(
            day_plans, structured_requirement
        )
        result.budget_conformance = budget_score
        result.details["budget_conformance"] = budget_details

        # 4. 偏好匹配度
        pref_score, pref_details = self._evaluate_preference_match(
            day_plans, structured_requirement
        )
        result.preference_match = pref_score
        result.details["preference_match"] = pref_details

        # 综合得分（加权平均）
        result.overall = (
            time_score * self.weights.time_rationality
            + geo_score * self.weights.geo_compactness
            + budget_score * self.weights.budget_conformance
            + pref_score * self.weights.preference_match
        )

        return result

    def _evaluate_time_rationality(
        self,
        day_plans: List[Dict[str, Any]],
        structured_requirement: Dict[str, Any],
    ) -> Tuple[float, Dict[str, Any]]:
        """
        评估时间合理性

        考虑因素:
        - 活动是否在合理时间段内（6:00-23:00）
        - 每日总游览时长是否适中（不过长/过短）
        - 交通时间是否合理
        - 餐饮时间是否正常

        Returns:
            (得分0~1, 详细信息)
        """
        if not day_plans:
            return 0.5, {"reason": "无行程数据"}

        total_penalty = 0.0
        total_checks = 0
        details = {}

        from src.routes.validate import parse_time_to_minutes, parse_duration_to_minutes

        for day_idx, plan in enumerate(day_plans):
            day_num = day_idx + 1
            
            # 检查不合理时间段
            for attr in plan.get("attractions", []):
                if not isinstance(attr, dict):
                    continue
                start = attr.get("start_time") or attr.get("visit_time", "")
                end = attr.get("end_time", "")
                
                if start:
                    start_m = parse_time_to_minutes(start)
                    # 早于6:00或晚于23:00扣分
                    if start_m < 360:  # 6:00
                        total_penalty += 0.3
                        total_checks += 1
                    elif start_m > 1380:  # 23:00
                        total_penalty += 0.2
                        total_checks += 1
                    else:
                        total_checks += 1
                
                if end:
                    end_m = parse_time_to_minutes(end)
                    if end_m > 1380:
                        total_penalty += 0.2
                        total_checks += 1

            # 检查每日总时长
            total_day_minutes = 0
            for attr in plan.get("attractions", []):
                if not isinstance(attr, dict):
                    continue
                dur = attr.get("duration") or attr.get("visit_duration", "2小时")
                total_day_minutes += parse_duration_to_minutes(dur)

            # 理想每日时长：6-10小时
            if total_day_minutes > 0:
                total_checks += 1
                if total_day_minutes < 240:  # < 4小时
                    total_penalty += 0.15
                elif total_day_minutes > 720:  # > 12小时
                    total_penalty += 0.25
                else:
                    total_penalty += 0  # 合理范围

            details[f"day_{day_num}"] = {
                "total_minutes": total_day_minutes,
                "penalty": total_penalty,
            }

        score = max(0.0, 1.0 - (total_penalty / max(total_checks, 1)))
        return score, {"days_checked": len(day_plans), "total_penalty": total_penalty}

    def _evaluate_geo_compactness(
        self,
        day_plans: List[Dict[str, Any]],
        structured_requirement: Dict[str, Any],
    ) -> Tuple[float, Dict[str, Any]]:
        """
        评估地理紧凑性

        考虑因素:
        - 相邻景点之间的距离
        - 是否存在跨城远距离移动
        - 每天景点的地理分布集中度

        Returns:
            (得分0~1, 详细信息)
        """
        if not day_plans:
            return 0.5, {"reason": "无行程数据"}

        total_distances = []
        max_distances_per_day = []
        details = {}

        for day_idx, plan in enumerate(day_plans):
            attrs = plan.get("attractions", [])
            valid_attrs = [a for a in attrs if isinstance(a, dict)]
            
            if len(valid_attrs) < 2:
                max_distances_per_day.append(0)
                continue

            day_distances = []
            for i in range(len(valid_attrs) - 1):
                loc_i = valid_attrs[i].get("location", {})
                loc_j = valid_attrs[i + 1].get("location", {})
                dist = self._haversine_distance(loc_i, loc_j)
                day_distances.append(dist)
                total_distances.append(dist)

            max_dist = max(day_distances) if day_distances else 0
            max_distances_per_day.append(max_dist)
            details[f"day_{day_idx + 1}"] = {
                "distances_km": [round(d, 1) for d in day_distances],
                "max_distance_km": round(max_dist, 1),
            }

        if not total_distances:
            return 1.0, {"reason": "无景点间距离数据"}

        # 计算紧凑度得分
        # 理想情况：所有相邻景点距离 < 15km
        # 15-30km：部分扣分
        # > 30km：严重扣分
        total_penalty = 0.0
        for dist in total_distances:
            if dist > 30:
                total_penalty += 0.3
            elif dist > 15:
                total_penalty += 0.15

        # 检查每日最大距离
        for max_dist in max_distances_per_day:
            if max_dist > 50:
                total_penalty += 0.2

        score = max(0.0, 1.0 - (total_penalty / max(len(total_distances), 1)))
        return score, {
            "total_segments": len(total_distances),
            "avg_distance_km": round(sum(total_distances) / len(total_distances), 1),
            "max_distance_km": round(max(total_distances), 1),
            "total_penalty": total_penalty,
        }

    def _evaluate_budget_conformance(
        self,
        day_plans: List[Dict[str, Any]],
        structured_requirement: Dict[str, Any],
    ) -> Tuple[float, Dict[str, Any]]:
        """
        评估预算符合度

        考虑因素:
        - 总花费是否在预算范围内
        - 每日花费是否均衡

        Returns:
            (得分0~1, 详细信息)
        """
        total_budget = structured_requirement.get("total_budget", 0)
        if not total_budget:
            return 1.0, {"reason": "无预算限制"}

        # 估算总花费（从景点门票/活动费用估算）
        total_cost = 0
        daily_costs = []

        for plan in day_plans:
            day_cost = 0
            for attr in plan.get("attractions", []):
                if not isinstance(attr, dict):
                    continue
                # 尝试获取费用信息
                cost = attr.get("cost") or attr.get("price") or attr.get("ticket_price", 0)
                try:
                    day_cost += float(cost) if cost else 0
                except (ValueError, TypeError):
                    pass

            # 估算餐饮费用（每餐约50-100元）
            num_meals = len(plan.get("meals", []))
            day_cost += num_meals * 75

            total_cost += day_cost
            daily_costs.append(day_cost)

        if total_cost <= 0:
            return 0.8, {"reason": "无法获取费用信息", "estimated_cost": 0}

        # 预算符合度得分
        if total_cost <= total_budget:
            # 在预算内：得分0.8~1.0（越接近预算满分）
            score = 0.8 + 0.2 * (1 - total_cost / total_budget)
        else:
            # 超出预算：得分0~0.8
            over_ratio = (total_cost - total_budget) / total_budget
            score = max(0, 0.8 - over_ratio * 0.5)

        return min(1.0, score), {
            "total_budget": total_budget,
            "estimated_cost": round(total_cost),
            "over_budget": total_cost > total_budget,
            "over_amount": round(max(0, total_cost - total_budget)),
            "daily_costs": [round(c) for c in daily_costs],
        }

    def _evaluate_preference_match(
        self,
        day_plans: List[Dict[str, Any]],
        structured_requirement: Dict[str, Any],
    ) -> Tuple[float, Dict[str, Any]]:
        """
        评估偏好匹配度

        考虑因素:
        - 景点类型是否符合用户偏好（自然/人文/美食等）
        - 推荐景点的评分
        - 是否有用户明确提到的必去景点

        Returns:
            (得分0~1, 详细信息)
        """
        preferences = structured_requirement.get("preferences", [])
        if not preferences:
            return 0.8, {"reason": "无偏好数据"}

        # 偏好关键词映射
        pref_keywords = {
            "自然": ["自然", "山", "水", "湖", "公园", "森林", "海", "沙滩", "风景"],
            "人文": ["人文", "历史", "博物馆", "古迹", "寺庙", "文化", "遗址", "古镇"],
            "美食": ["美食", "餐厅", "小吃", "餐饮"],
            "购物": ["购物", "商场", "商业街", "市场"],
            "亲子": ["亲子", "儿童", "乐园", "动物园", "科技馆"],
            "冒险": ["冒险", "户外", "运动", "徒步", "登山"],
            "休闲": ["休闲", "spa", "温泉", "度假", "放松"],
            "摄影": ["摄影", "拍照", "打卡", "观景", "夜景"],
        }

        total_score = 0
        attr_count = 0
        matched_prefs = set()
        details = {}

        for plan in day_plans:
            for attr in plan.get("attractions", []):
                if not isinstance(attr, dict):
                    continue
                attr_count += 1
                attr_name = attr.get("name", "")
                attr_type = attr.get("type", "")
                attr_tags = attr.get("tags", [])
                if isinstance(attr_tags, str):
                    attr_tags = [attr_tags]

                attr_text = f"{attr_name} {attr_type} {' '.join(attr_tags)}".lower()
                attr_score = 0

                for pref in preferences:
                    pref_lower = pref.lower()
                    # 检查偏好关键词
                    for category, keywords in pref_keywords.items():
                        if category.lower() in pref_lower:
                            for kw in keywords:
                                if kw in attr_text:
                                    attr_score += 1
                                    matched_prefs.add(category)
                                    break
                    # 检查直接匹配
                    if pref_lower in attr_text:
                        attr_score += 2

                # 计算该景点的匹配度（归一化到0~1）
                max_possible = len(preferences) * 2
                attr_normalized = min(1.0, attr_score / max_possible) if max_possible > 0 else 0.5
                total_score += attr_normalized
                details[attr_name] = {
                    "match_score": attr_normalized,
                    "attr_text_preview": attr_text[:50],
                }

        if attr_count == 0:
            return 0.5, {"reason": "无景点数据"}

        avg_score = total_score / attr_count if attr_count > 0 else 0.5
        return avg_score, {
            "total_attractions": attr_count,
            "matched_categories": list(matched_prefs),
            "unmatched_preferences": [
                p for p in preferences
                if not any(
                    p.lower() in attr_text
                    for plan in day_plans
                    for attr in plan.get("attractions", [])
                    if isinstance(attr, dict)
                    for attr_text in [
                        f"{attr.get('name', '')} {attr.get('type', '')}"
                    ]
                )
            ],
        }

    def _haversine_distance(self, loc1: Dict[str, Any], loc2: Dict[str, Any]) -> float:
        """计算两点间的Haversine距离（公里）"""
        if not loc1 or not loc2:
            return float("inf")
        
        lat1 = loc1.get("lat") or loc1.get("latitude")
        lng1 = loc1.get("lng") or loc1.get("longitude") or loc1.get("lon")
        lat2 = loc2.get("lat") or loc2.get("latitude")
        lng2 = loc2.get("lng") or loc2.get("longitude") or loc2.get("lon")
        
        if None in (lat1, lng1, lat2, lng2):
            return float("inf")
        
        try:
            lat1, lng1, lat2, lng2 = float(lat1), float(lng1), float(lat2), float(lng2)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return float("inf")
        
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlng / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def compare_results(
        self,
        results: List[Tuple[str, List[Dict[str, Any]], Dict[str, Any]]],
    ) -> List[Tuple[str, UtilityResult]]:
        """
        比较多个协商结果，返回按效用排序的结果

        Args:
            results: [(方案名称, day_plans, structured_requirement), ...]

        Returns:
            按效用从高到低排序的 [(方案名称, 效用结果), ...]
        """
        evaluated = []
        for name, plans, req in results:
            utility = self.evaluate(plans, req)
            evaluated.append((name, utility))

        evaluated.sort(key=lambda x: x[1].overall, reverse=True)
        return evaluated


# ==================== 全局单例 ====================

utility_evaluator = UtilityEvaluator()


# ==================== 快捷函数 ====================

def compute_utility_dict(
    day_plans: List[Dict[str, Any]],
    structured_requirement: Dict[str, Any],
) -> Dict[str, float]:
    """
    计算并返回效用字典（兼容旧版接口）

    Args:
        day_plans: 每日行程
        structured_requirement: 结构化需求

    Returns:
        效用字典 {"dispatcher": overall, "vehicle": geo_compactness, ...}
    """
    result = utility_evaluator.evaluate(day_plans, structured_requirement)
    return {
        "dispatcher": round(result.overall, 4),
        "time_rationality": round(result.time_rationality, 4),
        "geo_compactness": round(result.geo_compactness, 4),
        "budget_conformance": round(result.budget_conformance, 4),
        "preference_match": round(result.preference_match, 4),
    }
