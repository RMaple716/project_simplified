"""
Pareto 优化器 — 多目标优化模块

【第三阶段新增】在"交通时间"和"冲突数量"之间找 Pareto 最优解。

Pareto 前沿概念：
  方案A 和 方案B，如果 A 在所有目标维度上都不比 B 差，且至少有一个维度严格更好，
  则 A 支配（dominate）B。所有不被任何其他方案支配的方案构成 Pareto 前沿。

使用场景：
  1. 路线优化时：比较多种排序方案的 Pareto 优劣
  2. 协商完成后：向用户展示多个 Pareto 最优方案供选择
  3. 冲突修复时：评估修复是否带来了其他目标的劣化

Pareto 目标维度：
  - 目标1（最小化）：总交通时间（分钟）
  - 目标2（最小化）：总冲突惩罚值（warning 加权和）
  - 目标3（最大化）：效用综合得分（overall_with_penalty）

使用方法：
    from .pareto_optimizer import pareto_optimizer

    # 分析一组方案的 Pareto 前沿
    front = pareto_optimizer.compute_pareto_front(candidates)

    # 在路线优化时，从 Pareto 最优方案中选择
    best = pareto_optimizer.select_from_pareto(alternatives)
"""

import logging
import copy
import math
from typing import Dict, Any, List, Optional, Tuple, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ParetoCandidate:
    """
    Pareto 候选方案

    Attributes:
        name: 方案名称
        day_plans: 行程方案
        total_transport_time: 总交通时间（分钟），越小越好（目标1）
        conflict_penalty: 冲突惩罚值，越小越好（目标2）
        utility_score: 综合效用得分，越大越好（目标3）
        details: 详细信息
    """
    name: str
    day_plans: List[dict]
    total_transport_time: float = 0.0
    conflict_penalty: float = 0.0
    utility_score: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)

    def dominates(self, other: "ParetoCandidate") -> bool:
        """
        检查本方案是否支配另一个方案

        支配条件（在最小化目标下）：
        - 所有维度上不差于对方（≤ for 越小越好维度，≥ for 越大越好维度）
        - 至少有一个维度严格更好

        Args:
            other: 另一个候选方案

        Returns:
            True: 本方案支配 other
        """
        # 目标1：交通时间，越小越好（≤）
        better_or_equal_1 = self.total_transport_time <= other.total_transport_time
        strictly_better_1 = self.total_transport_time < other.total_transport_time

        # 目标2：冲突惩罚，越小越好（≤）
        better_or_equal_2 = self.conflict_penalty <= other.conflict_penalty
        strictly_better_2 = self.conflict_penalty < other.conflict_penalty

        # 目标3：效用得分，越大越好（≥）
        better_or_equal_3 = self.utility_score >= other.utility_score
        strictly_better_3 = self.utility_score > other.utility_score

        # 所有维度上不差
        all_better_or_equal = better_or_equal_1 and better_or_equal_2 and better_or_equal_3

        # 至少一个维度严格更好
        any_strictly_better = strictly_better_1 or strictly_better_2 or strictly_better_3

        return all_better_or_equal and any_strictly_better

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "total_transport_time": round(self.total_transport_time, 1),
            "conflict_penalty": round(self.conflict_penalty, 4),
            "utility_score": round(self.utility_score, 4),
            "details": self.details,
        }


class ParetoOptimizer:
    """
    Pareto 优化器（单例）

    核心功能：
    1. compute_pareto_front() — 从一组候选方案中计算 Pareto 前沿
    2. select_from_pareto() — 从 Pareto 前沿中选择最合适的方案
    3. is_pareto_improvement() — 判断修改前后是否 Pareto 改进
    4. compute_objectives() — 计算方案在各目标维度上的值
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        # 默认权重（当需要从 Pareto 前沿中选一个时）
        self.transport_weight = 0.4      # 交通时间权重
        self.conflict_weight = 0.3       # 冲突惩罚权重
        self.utility_weight = 0.3        # 效用得分权重
        logger.info("[Pareto优化器] 初始化完成")

    def compute_objectives(
        self,
        day_plans: List[dict],
        structured_requirement: dict,
        conflicts: Optional[List[dict]] = None,
    ) -> Tuple[float, float, float]:
        """
        计算方案在三个 Pareto 目标维度上的值

        Args:
            day_plans: 行程方案
            structured_requirement: 结构化需求
            conflicts: 冲突列表（可选，不提供时会自动检测）

        Returns:
            (total_transport_time, conflict_penalty, utility_score)
        """
        from src.services.negotiation_utility import utility_evaluator
        from .conflict_detector import detect_conflicts

        # 1. 计算总交通时间
        total_transport = self._estimate_total_transport_time(day_plans)

        # 2. 计算冲突惩罚
        if conflicts is None:
            detection = detect_conflicts(day_plans, structured_requirement)
            conflicts = detection.conflicts

        # 用效用评估器计算惩罚值
        utility_result = utility_evaluator.evaluate(
            day_plans, structured_requirement,
            conflicts=conflicts,
        )
        conflict_penalty = utility_result.details.get(
            "conflict_penalty", {}
        ).get("penalty", 0.0)

        # 3. 综合效用得分
        utility_score = utility_result.overall_with_penalty

        return total_transport, conflict_penalty, utility_score

    def compute_pareto_front(
        self,
        candidates: List[Tuple[str, List[dict], Dict[str, Any]]],
        structured_requirement: dict,
    ) -> List[ParetoCandidate]:
        """
        从一组候选方案中计算 Pareto 前沿

        Args:
            candidates: [(方案名称, day_plans, 额外信息), ...]
            structured_requirement: 结构化需求

        Returns:
            Pareto 前沿上的方案列表（按效用得分降序排列）
        """
        if not candidates:
            return []

        # 将所有候选转换为 ParetoCandidate
        pareto_candidates = []
        for name, plans, extra in candidates:
            transport, penalty, utility = self.compute_objectives(
                plans, structured_requirement
            )
            pc = ParetoCandidate(
                name=name,
                day_plans=plans,
                total_transport_time=transport,
                conflict_penalty=penalty,
                utility_score=utility,
                details=extra,
            )
            pareto_candidates.append(pc)

        # 计算支配关系，找出 Pareto 前沿
        front = []
        for i, candidate in enumerate(pareto_candidates):
            dominated = False
            for j, other in enumerate(pareto_candidates):
                if i == j:
                    continue
                if other.dominates(candidate):
                    dominated = True
                    logger.debug(
                        f"[Pareto] '{candidate.name}' 被 '{other.name}' 支配"
                    )
                    break

            if not dominated:
                front.append(candidate)

        # 按效用得分降序排列
        front.sort(key=lambda x: x.utility_score, reverse=True)

        logger.info(
            f"[Pareto] 从 {len(candidates)} 个方案中找到 "
            f"{len(front)} 个 Pareto 最优方案"
        )
        return front

    def select_from_pareto(
        self,
        front: List[ParetoCandidate],
        user_preference: Optional[Dict[str, float]] = None,
    ) -> ParetoCandidate:
        """
        从 Pareto 前沿中选择最合适的方案

        使用加权和法（scalarization）将多目标转为单目标。
        用户可以通过 user_preference 调整各目标的相对重要性。

        Args:
            front: Pareto 候选方案列表
            user_preference: 用户偏好权重
                {"transport": 0.4, "conflict": 0.3, "utility": 0.3}
                不提供时使用默认权重

        Returns:
            选中的方案
        """
        if not front:
            raise ValueError("Pareto 前沿为空，无法选择")

        if len(front) == 1:
            return front[0]

        # 应用用户偏好权重
        w1 = user_preference.get("transport", self.transport_weight) if user_preference else self.transport_weight
        w2 = user_preference.get("conflict", self.conflict_weight) if user_preference else self.conflict_weight
        w3 = user_preference.get("utility", self.utility_weight) if user_preference else self.utility_weight

        # 归一化权重
        total_w = w1 + w2 + w3
        w1, w2, w3 = w1 / total_w, w2 / total_w, w3 / total_w

        # 数据归一化（min-max），避免量纲影响
        transport_vals = [c.total_transport_time for c in front]
        penalty_vals = [c.conflict_penalty for c in front]
        utility_vals = [c.utility_score for c in front]

        t_min, t_max = min(transport_vals), max(transport_vals)
        p_min, p_max = min(penalty_vals), max(penalty_vals)
        u_min, u_max = min(utility_vals), max(utility_vals)

        def normalize(val, vmin, vmax):
            if vmax - vmin == 0:
                return 0.5
            return (val - vmin) / (vmax - vmin)

        best_score = -float('inf')
        best_candidate = None

        for candidate in front:
            # 交通时间（越小越好）→ 用 1 - normalized 使得越大越好
            t_norm = 1 - normalize(candidate.total_transport_time, t_min, t_max)
            # 冲突惩罚（越小越好）→ 同样处理
            p_norm = 1 - normalize(candidate.conflict_penalty, p_min, p_max)
            # 效用得分（越大越好）
            u_norm = normalize(candidate.utility_score, u_min, u_max)

            # 加权综合得分
            score = w1 * t_norm + w2 * p_norm + w3 * u_norm

            if score > best_score:
                best_score = score
                best_candidate = candidate

        assert best_candidate is not None, "Pareto前沿非空时应总是选中一个方案"

        logger.info(
            f"[Pareto] 从 {len(front)} 个最优方案中选择 "
            f"'{best_candidate.name}' (score={best_score:.4f})"
        )
        return best_candidate

    def is_pareto_improvement(
        self,
        before: List[dict],
        after: List[dict],
        structured_requirement: dict,
    ) -> bool:
        """
        判断修改前后是否 Pareto 改进

        Pareto 改进：修改后至少一个目标改善，且没有目标劣化。

        Args:
            before: 修改前的方案
            after: 修改后的方案
            structured_requirement: 结构化需求

        Returns:
            True: 是 Pareto 改进
        """
        t_before, p_before, u_before = self.compute_objectives(
            before, structured_requirement
        )
        t_after, p_after, u_after = self.compute_objectives(
            after, structured_requirement
        )

        # 交通时间变小（改善）
        transport_better = t_after < t_before
        transport_no_worse = t_after <= t_before

        # 冲突惩罚变小（改善）
        penalty_better = p_after < p_before
        penalty_no_worse = p_after <= p_before

        # 效用变大（改善）
        utility_better = u_after > u_before
        utility_no_worse = u_after >= u_before

        # 所有维度不劣化且至少一个改善
        all_no_worse = transport_no_worse and penalty_no_worse and utility_no_worse
        any_better = transport_better or penalty_better or utility_better

        if all_no_worse and any_better:
            logger.info(
                f"[Pareto改进] ✅ 交通:{t_before:.0f}→{t_after:.0f}min, "
                f"惩罚:{p_before:.4f}→{p_after:.4f}, "
                f"效用:{u_before:.4f}→{u_after:.4f}"
            )
            return True

        logger.debug(
            f"[Pareto改进] ❌ 不是 Pareto 改进: "
            f"交通:{t_before:.0f}→{t_after:.0f}min, "
            f"惩罚:{p_before:.4f}→{p_after:.4f}, "
            f"效用:{u_before:.4f}→{u_after:.4f}"
        )
        return False

    def rank_by_pareto_depth(
        self,
        candidates: List[Tuple[str, List[dict], Dict[str, Any]]],
        structured_requirement: dict,
    ) -> List[List[ParetoCandidate]]:
        """
        按 Pareto 深度分层排序（非支配排序）

        第1层：Pareto 前沿（不被任何方案支配）
        第2层：除第1层外，剩下的方案中的 Pareto 前沿
        以此类推...

        用于遗传算法中的选择操作。

        Args:
            candidates: 候选方案列表
            structured_requirement: 结构化需求

        Returns:
            分层结果，每层是一个 ParetoCandidate 列表
        """
        if not candidates:
            return []

        # 将所有候选转换为 ParetoCandidate
        all_candidates = []
        for name, plans, extra in candidates:
            transport, penalty, utility = self.compute_objectives(
                plans, structured_requirement
            )
            pc = ParetoCandidate(
                name=name,
                day_plans=plans,
                total_transport_time=transport,
                conflict_penalty=penalty,
                utility_score=utility,
                details=extra,
            )
            all_candidates.append(pc)

        layers = []
        remaining = list(all_candidates)

        while remaining:
            front = []
            not_front = []

            for candidate in remaining:
                dominated = False
                for other in remaining:
                    if other is candidate:
                        continue
                    if other.dominates(candidate):
                        dominated = True
                        break

                if dominated:
                    not_front.append(candidate)
                else:
                    front.append(candidate)

            if not front:
                break  # 防止无限循环

            front.sort(key=lambda x: x.utility_score, reverse=True)
            layers.append(front)
            remaining = not_front

        logger.info(
            f"[Pareto分层] {sum(len(l) for l in layers)} 个方案分为 "
            f"{len(layers)} 层"
        )
        return layers

    def _estimate_total_transport_time(
        self,
        day_plans: List[dict],
    ) -> float:
        """
        估算总交通时间

        Args:
            day_plans: 行程方案

        Returns:
            总交通时间（分钟）
        """
        total = 0.0
        for plan in day_plans:
            attrs = plan.get("attractions", [])
            valid = [a for a in attrs if isinstance(a, dict)]
            for i in range(len(valid) - 1):
                loc_i = valid[i].get("location", {})
                loc_j = valid[i + 1].get("location", {})
                dist = self._haversine_km(loc_i, loc_j)
                if dist < float('inf'):
                    # 估算交通时间（25km/h 公交速度）
                    total += (dist / 25) * 60
        return total

    def _haversine_km(self, loc1: dict, loc2: dict) -> float:
        """计算两个地点之间的大圆距离（km）"""
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


# 全局单例
pareto_optimizer = ParetoOptimizer()
