"""
协商效用评估体系 — 多维效用函数

功能:
1. ✅ 计算行程方案的多维效用值
2. ✅ 支持可配置的权重（从 structured_requirement 读取）
3. ✅ 支持用户偏好调整
4. ✅ 用于比较不同协商结果，选择最优方案
5. ✅ 【第三阶段】warning 冲突惩罚项
6. ✅ 【第三阶段】效用驱动策略选择（最高效用而非固定顺序）
7. ✅ 【第三阶段】用户偏好学习（从接受/拒绝/手动调整中自动调整权重）

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
from typing import Dict, Any, List, Optional, Tuple, Callable
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
    
    # 【第三阶段】冲突惩罚后的效用
    overall_with_penalty: float = 0.0
    
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
            "overall_with_penalty": round(self.overall_with_penalty, 4),
            "dimensions": {k: round(v, 4) for k, v in self.dimensions.items()},
            "details": self.details,
        }


class UtilityEvaluator:
    """
    效用评估器（第三增强版）

    计算行程方案的多维效用值，支持可配置的权重。
    【第三阶段新增】:
      - 从 structured_requirement 中读取用户权重偏好
      - warning 冲突惩罚项
      - 用于效用驱动的策略选择
      - 用户偏好学习（从接受/拒绝/手动调整反馈中自动调整权重）
    """

    def __init__(self):
        self.weights = UtilityWeights.default()
        # 【第三阶段】warning 冲突各类型对应的扣分系数
        # 权重越高表示用户越在意该类型的 warning
        self.warning_penalties = {
            "unreasonable_meal_time": 0.03,       # 不合理用餐时间
            "overloaded_day": 0.05,               # 当日过满
            "too_short_duration": 0.04,            # 游览时长过短
            "too_long_duration": 0.03,             # 游览时长过长
            "geo_distance_warning": 0.03,          # 地理距离警告
            "transport_time_warning": 0.04,        # 交通时长警告
            "budget_exceeded": 0.08,               # 超预算
            "outside_opening_hours": 0.06,         # 营业时间外
            "closed_day": 0.07,                    # 闭馆日
            "cross_day_transport_warning": 0.04,   # 跨天交通警告
        }
        # 权重预热期：前 N 轮使用默认权重，之后从需求读取
        self._warmup_rounds = 0

        # ==================== 【第三阶段】用户偏好学习 ====================
        # 学习率：每次反馈调整的步长
        self._learning_rate: float = 0.1
        # 历史反馈记录：[{feedback, weights_before, dimension_scores, ...}, ...]
        self._feedback_history: List[Dict[str, Any]] = []
        # 方案历史：缓存最近 N 次评估的方案，供偏好学习使用
        self._recent_evaluations: List[dict] = []
        # 最大历史记录数
        self._max_feedback_history: int = 50
        # 当用户拒绝了某个方案时，该方案的效用心跳记录
        self._rejected_plans: List[Dict[str, Any]] = []
        logger.info("[效用评估] 第三阶段增强版（含偏好学习）初始化完成")

    def configure_weights(self, weights: Dict[str, float]) -> None:
        """
        配置效用权重

        Args:
            weights: 权重字典，可包含 time_rationality, geo_compactness,
                    budget_conformance, preference_match
        """
        self.weights.from_dict(weights)
        logger.info(f"[效用评估] 权重已更新: {self.weights.to_dict()}")

    def configure_weights_from_requirement(
        self,
        structured_requirement: Dict[str, Any],
    ) -> None:
        """
        【第三阶段】从结构化需求中读取用户权重偏好

        权重来源于：
        1. structured_requirement 中的 "utility_weights" 字段
        2. 如果未设置，则从用户的 "preferences" 推断
        3. 如果都未设置，使用默认权重

        Args:
            structured_requirement: 结构化需求
        """
        # 方式1：直接读取 utility_weights
        utility_weights = structured_requirement.get("utility_weights")
        if utility_weights and isinstance(utility_weights, dict):
            self.weights.from_dict(utility_weights)
            logger.info(
                f"[效用评估] 从需求读取权重: {self.weights.to_dict()}"
            )
            return

        # 方式2：从 preferences 推断
        preferences = structured_requirement.get("preferences", [])
        if preferences:
            inferred = self._infer_weights_from_preferences(preferences)
            self.weights.from_dict(inferred)
            logger.info(
                f"[效用评估] 从偏好'{preferences}'推断权重: "
                f"{self.weights.to_dict()}"
            )
            return

        # 方式3：默认权重
        logger.info(f"[效用评估] 使用默认权重: {self.weights.to_dict()}")

    def _infer_weights_from_preferences(
        self,
        preferences: List[str],
    ) -> Dict[str, float]:
        """
        从用户偏好推断效用权重

        Args:
            preferences: 用户偏好列表

        Returns:
            推断的权重字典
        """
        pref_text = " ".join(preferences).lower()

        # 各维度关键词映射
        time_keywords = ["紧凑", "高效", "密集", "快", "省时", "效率", "时间"]
        geo_keywords = ["近", "集中", "步行", "紧凑", "方便", "附近", "顺路", "距离"]
        budget_keywords = ["省钱", "预算", "便宜", "经济", "实惠", "穷游", "低价"]
        pref_keywords = ["深度", "品质", "体验", "特色", "美食", "文化", "自然", "购物"]

        # 计算各维度匹配度
        time_weight = self._keyword_match_score(pref_text, time_keywords) * 0.3 + 0.2
        geo_weight = self._keyword_match_score(pref_text, geo_keywords) * 0.3 + 0.15
        budget_weight = self._keyword_match_score(pref_text, budget_keywords) * 0.3 + 0.10
        pref_weight = self._keyword_match_score(pref_text, pref_keywords) * 0.3 + 0.20

        # 归一化
        weights = {
            "time_rationality": time_weight,
            "geo_compactness": geo_weight,
            "budget_conformance": budget_weight,
            "preference_match": pref_weight,
        }
        total = sum(weights.values())
        if total > 0:
            for k in weights:
                weights[k] /= total

        return weights

    def _keyword_match_score(
        self,
        text: str,
        keywords: List[str],
    ) -> float:
        """计算文本中关键词的匹配得分（0~1）"""
        if not text or not keywords:
            return 0.5
        matches = sum(1 for kw in keywords if kw in text)
        return min(1.0, matches / 2.0)  # 2个关键词就满分

    def get_weights(self) -> Dict[str, float]:
        """获取当前权重配置"""
        return self.weights.to_dict()

    def get_warning_penalty(self, conflict_type: str) -> float:
        """获取指定冲突类型的扣分系数"""
        return self.warning_penalties.get(conflict_type, 0.02)

    def evaluate(
        self,
        day_plans: List[Dict[str, Any]],
        structured_requirement: Dict[str, Any],
        conflicts: Optional[List[Dict[str, Any]]] = None,
    ) -> UtilityResult:
        """
        计算行程方案的多维效用

        Args:
            day_plans: 每日行程列表
            structured_requirement: 结构化需求
            conflicts: 【第三阶段】可选，当前冲突列表，用于计算惩罚项

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

        # 【第三阶段】warning 冲突惩罚项
        penalty = self._calculate_conflict_penalty(conflicts)
        result.overall_with_penalty = max(0.0, result.overall - penalty)
        result.details["conflict_penalty"] = {
            "penalty": round(penalty, 4),
            "conflicts_count": len(conflicts) if conflicts else 0,
        }

        return result

    def _calculate_conflict_penalty(
        self,
        conflicts: Optional[List[Dict[str, Any]]],
    ) -> float:
        """
        【第三阶段】计算冲突扣分

        每个 warning 冲突根据类型扣减效用值。
        error 冲突已由协商流程单独处理，这里只计算 warning 的扣分。

        Args:
            conflicts: 冲突列表

        Returns:
            总扣分值（0~1）
        """
        if not conflicts:
            return 0.0

        total_penalty = 0.0
        for conflict in conflicts:
            conflict_type = conflict.get("type", "")
            severity = conflict.get("severity", "warning")
            # warning 级别的冲突才扣分
            if severity == "warning":
                penalty = self.get_warning_penalty(conflict_type)
                total_penalty += penalty

        # 扣分上限 0.5，防止效用被过度压低
        return min(0.5, total_penalty)

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

    def select_best_strategy_result(
        self,
        candidates: List[Tuple[str, List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]],
        structured_requirement: Dict[str, Any],
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
        """
        【第三阶段】效用驱动的策略选择

        从多个候选方案中选择效用最高的那个。
        替代原有的"按固定优先级顺序尝试，第一个成功就返回"。

        Args:
            candidates: [(strategy_name, day_plans, conflict, adjustments), ...]
            structured_requirement: 结构化需求

        Returns:
            (best_strategy, best_plans, best_utility)
            如果无候选，返回 (None, None, None)
        """
        if not candidates:
            return None, None, None

        best_strategy = None
        best_plans = None
        best_utility = -1.0
        best_utility_dict = None

        for strategy_name, plans, conflict, adjustments in candidates:
            utility = self.evaluate(plans, structured_requirement, conflicts=[conflict])
            # 使用含惩罚的综合效用
            effective_utility = utility.overall_with_penalty

            if effective_utility > best_utility:
                best_utility = effective_utility
                best_strategy = strategy_name
                best_plans = plans
                best_utility_dict = utility

            logger.debug(
                f"[效用驱动选择] {strategy_name}: "
                f"overall={utility.overall:.4f}, "
                f"with_penalty={effective_utility:.4f}"
            )

        logger.info(
            f"[效用驱动选择] 选中 '{best_strategy}': "
            f"utility={best_utility:.4f}"
        )

        return best_strategy, best_plans, best_utility_dict #type:ignore

    # ==============================================================
    # 【第三阶段】用户偏好学习
    # ==============================================================

    def record_feedback(
        self,
        day_plans: List[Dict[str, Any]],
        structured_requirement: Dict[str, Any],
        feedback: str,
        user_notes: Optional[str] = None,
    ) -> None:
        """
        记录用户对某个协商方案的反馈

        支持的反馈类型:
          - "accept": 用户接受了方案 → 确认当前权重合理（小幅度正向增强）
          - "reject": 用户拒绝了方案 → 分析该方案的维度缺陷，调低表现好的维度权重
          - "adjust": 用户手动调整了部分内容 → 对比调整前后的维度变化
          - "prefer_time": 用户更看重时间合理性 → 调高 time_rationality 权重
          - "prefer_geo": 用户更看重地理紧凑性 → 调高 geo_compactness 权重
          - "prefer_budget": 用户更看重预算 → 调高 budget_conformance 权重
          - "prefer_pref": 用户更看重偏好匹配 → 调高 preference_match 权重

        Args:
            day_plans: 方案行程
            structured_requirement: 结构化需求
            feedback: 反馈类型
            user_notes: 用户备注（可选）
        """
        # 计算该方案的各维度得分
        result = self.evaluate(day_plans, structured_requirement)

        # 记录反馈历史
        record = {
            "feedback": feedback,
            "weights_before": self.weights.to_dict(),
            "dimension_scores": result.dimensions,
            "overall": result.overall,
            "user_notes": user_notes,
            "timestamp": self._current_timestamp(),
        }
        self._feedback_history.append(record)

        # 根据反馈类型调整权重
        if feedback == "accept":
            self._learn_from_acceptance(result)
        elif feedback == "reject":
            self._learn_from_rejection(result)
        elif feedback == "adjust":
            self._learn_from_adjustment(day_plans, structured_requirement, user_notes)
        elif feedback.startswith("prefer_"):
            preferred_dim = feedback.replace("prefer_", "")
            self._learn_from_explicit_preference(preferred_dim)

        # 限制历史记录大小
        if len(self._feedback_history) > self._max_feedback_history:
            self._feedback_history = self._feedback_history[
                -self._max_feedback_history:
            ]

    def _learn_from_acceptance(self, result: UtilityResult) -> None:
        """
        从用户接受的行为中学习

        用户接受了方案 → 各维度都比较满意 → 小幅度正向增强当前权重。
        方案中得分特别高的维度说明用户比较认可该方向，微调权重。
        """
        changes = {}
        for dim, score in result.dimensions.items():
            # 得分 > 0.7 的维度：小幅调高权重（确认方向正确）
            if score > 0.7:
                factor = 1.0 + self._learning_rate * 0.3 * (score - 0.7)
                changes[dim] = getattr(self.weights, dim) * factor
            # 得分 < 0.4 的维度：小幅调低权重（用户可能不重视这个维度）
            elif score < 0.4:
                factor = 1.0 - self._learning_rate * 0.2 * (0.4 - score)
                changes[dim] = getattr(self.weights, dim) * factor

        if changes:
            for k, v in changes.items():
                setattr(self.weights, k, max(0.05, min(0.8, v)))
            self.weights.normalize()
            logger.info(
                f"[偏好学习-接受] 权重已微调: {self.weights.to_dict()}"
            )

    def _learn_from_rejection(self, result: UtilityResult) -> None:
        """
        从用户拒绝的行为中学习

        用户拒绝了方案 → 某些维度不满意。
        原则：对得分高的维度调低权重（用户不认可这个方向的过度优化），
              对得分低的维度调高权重（用户希望这个维度做得更好）。
        """
        changes = {}
        for dim, score in result.dimensions.items():
            # 得分 > 0.7 但被拒绝 → 用户不认可这个维度的过度 ? 调低权重
            if score > 0.7:
                factor = 1.0 - self._learning_rate * 0.4 * (score - 0.7)
                changes[dim] = getattr(self.weights, dim) * factor
            # 得分 < 0.4 且被拒绝 → 用户希望该维度改善 → 调高权重
            elif score < 0.4:
                factor = 1.0 + self._learning_rate * 0.3 * (0.4 - score)
                changes[dim] = getattr(self.weights, dim) * factor

        if changes:
            for k, v in changes.items():
                setattr(self.weights, k, max(0.05, min(0.8, v)))
            self.weights.normalize()
            logger.info(
                f"[偏好学习-拒绝] 权重已调整: {self.weights.to_dict()}"
            )

    def _learn_from_adjustment(
        self,
        day_plans: List[Dict[str, Any]],
        structured_requirement: Dict[str, Any],
        user_notes: Optional[str] = None,
    ) -> None:
        """
        从用户手动调整的行为中学习

        用户手动调整了行程 → 分析调整方向。
        通过比较用户提供的调整说明来判断倾向。
        user_notes 可能包含关键词如 "太赶"、"距离太远"、"太贵"等。
        """
        if not user_notes:
            return

        notes_lower = user_notes.lower()

        # 关键词 → 维度映射
        keyword_dimensions = {
            "太赶": "time_rationality",
            "时间": "time_rationality",
            "来不及": "time_rationality",
            "太远": "geo_compactness",
            "距离": "geo_compactness",
            "不顺路": "geo_compactness",
            "太贵": "budget_conformance",
            "预算": "budget_conformance",
            "花钱": "budget_conformance",
            "不喜欢": "preference_match",
            "没兴趣": "preference_match",
            "想去": "preference_match",
        }

        adjustments = {dim: 0.0 for dim in ["time_rationality", "geo_compactness", "budget_conformance", "preference_match"]}
        for keyword, dim in keyword_dimensions.items():
            if keyword in notes_lower:
                # 用户对这个维度不满意 → 调高其权重
                adjustments[dim] += self._learning_rate * 0.5

        # 应用调整
        has_change = False
        for dim, delta in adjustments.items():
            if delta > 0:
                new_val = getattr(self.weights, dim) + delta
                setattr(self.weights, dim, max(0.05, min(0.8, new_val)))
                has_change = True

        if has_change:
            self.weights.normalize()
            logger.info(
                f"[偏好学习-调整] 从用户备注'{user_notes}'学习: "
                f"权重已更新: {self.weights.to_dict()}"
            )

    def _learn_from_explicit_preference(self, preferred_dim: str) -> None:
        """
        从用户的显式偏好选择中学习

        Args:
            preferred_dim: 用户偏好的维度名（不含 "prefer_" 前缀）
        """
        dim_mapping = {
            "time": "time_rationality",
            "geo": "geo_compactness",
            "budget": "budget_conformance",
            "pref": "preference_match",
        }

        target_dim = dim_mapping.get(preferred_dim)
        if not target_dim:
            logger.warning(f"[偏好学习] 未知偏好维度: {preferred_dim}")
            return

        # 调高目标维度权重，等比调低其他维度
        current = getattr(self.weights, target_dim)
        increase = self._learning_rate * 0.4
        new_target = min(0.8, current + increase)

        # 其他维度等比缩减
        other_dims = [d for d in ["time_rationality", "geo_compactness", "budget_conformance", "preference_match"] if d != target_dim]
        total_other = sum(getattr(self.weights, d) for d in other_dims)
        if total_other > 0:
            scale = (1.0 - new_target) / total_other
            for d in other_dims:
                setattr(self.weights, d, getattr(self.weights, d) * scale)

        setattr(self.weights, target_dim, new_target)
        self.weights.normalize()

        logger.info(
            f"[偏好学习-显式] 用户偏好'{preferred_dim}': "
            f"权重已更新: {self.weights.to_dict()}"
        )

    def get_feedback_history(self) -> List[Dict[str, Any]]:
        """
        获取反馈历史记录

        Returns:
            反馈历史列表
        """
        return list(self._feedback_history)

    def suggest_next_weights(
        self,
        base_requirement: Dict[str, Any],
    ) -> Dict[str, float]:
        """
        根据历史反馈建议下一轮协商的权重

        综合分析之前的反馈历史，给出推荐的权重配置。
        如果历史记录不足，返回基于 structured_requirement 的权重。

        Args:
            base_requirement: 基础结构化需求

        Returns:
            建议的权重字典
        """
        if len(self._feedback_history) < 2:
            # 历史不足，使用基础的权重配置
            self.configure_weights_from_requirement(base_requirement)
            return self.weights.to_dict()

        # 使用最近 5 条反馈的平均倾向
        recent = self._feedback_history[-5:]

        # 统计各反馈类型出现的次数
        feedback_counts = {}
        for record in recent:
            fb = record["feedback"]
            feedback_counts[fb] = feedback_counts.get(fb, 0) + 1

        # 根据反馈频率调整
        suggested = UtilityWeights.default()
        # 从 base_requirement 初始化
        if "utility_weights" in base_requirement:
            suggested.from_dict(base_requirement["utility_weights"])

        # 应用反馈倾向
        for fb, count in feedback_counts.items():
            if fb == "reject":
                # 多次拒绝 → 尝试改变权重分布
                for dim in ["time_rationality", "geo_compactness", "budget_conformance", "preference_match"]:
                    current = getattr(suggested, dim)
                    setattr(suggested, dim, current * (1.0 + 0.05 * count))

        suggested.normalize()
        return suggested.to_dict()

    def _current_timestamp(self) -> str:
        """获取当前时间戳字符串"""
        from datetime import datetime
        return datetime.now().isoformat(timespec="seconds")


# ==================== 全局单例 ====================

utility_evaluator = UtilityEvaluator()


# ==================== 快捷函数 ====================

def compute_utility_dict(
    day_plans: List[Dict[str, Any]],
    structured_requirement: Dict[str, Any],
    conflicts: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, float]:
    """
    计算并返回效用字典（兼容旧版接口）

    Args:
        day_plans: 每日行程
        structured_requirement: 结构化需求
        conflicts: 【第三阶段】可选，冲突列表

    Returns:
        效用字典 {"dispatcher": overall, "vehicle": geo_compactness, ...}
    """
    result = utility_evaluator.evaluate(day_plans, structured_requirement, conflicts=conflicts)
    return {
        "dispatcher": round(result.overall, 4),
        "time_rationality": round(result.time_rationality, 4),
        "geo_compactness": round(result.geo_compactness, 4),
        "budget_conformance": round(result.budget_conformance, 4),
        "preference_match": round(result.preference_match, 4),
        "overall_with_penalty": round(result.overall_with_penalty, 4),
    }
