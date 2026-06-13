"""
协商策略选择器 — 动态策略管理与智能选择

功能:
1. ✅ 根据冲突类型动态选择最合适的修复策略
2. ✅ 记录每种策略的历史成功率，动态调整优先级
3. ✅ 支持并行尝试多个策略，选择最优结果
4. ✅ 策略注册机制，可动态添加新策略

使用方式:
    from src.services.negotiation_strategies import strategy_selector

    # 注册所有策略（启动时执行一次）
    strategy_selector.register_default_strategies()

    # 根据冲突选择最佳策略
    best_strategies = strategy_selector.select_strategies(conflict_type)

    # 记录策略结果
    strategy_selector.record_result(strategy_name, success=True)

    # 获取成功率
    rates = strategy_selector.get_success_rates()
"""
import time
import logging
from typing import Dict, Any, List, Optional, Callable, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """
    策略注册表

    管理所有可用的协商策略，支持按冲突类型筛选和优先级排序。
    """

    def __init__(self):
        # strategy_name -> strategy_info
        self._strategies: Dict[str, Dict[str, Any]] = {}
        # conflict_type -> [strategy_names]  （按优先级排序）
        self._conflict_strategies: Dict[str, List[str]] = defaultdict(list)
        # strategy_name -> {success_count, total_count, last_used}
        self._stats: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {"success": 0, "total": 0, "last_used": 0.0}
        )

    def register_strategy(
        self,
        name: str,
        func: Callable,
        conflict_types: List[str],
        priority: int = 50,
        description: str = "",
        is_async: bool = False,
        timeout_seconds: float = 5.0,
    ) -> None:
        """
        注册一个协商策略

        Args:
            name: 策略名称（如 "strategy_time_shift"）
            func: 策略函数（同步或异步）
            conflict_types: 适用的冲突类型列表
            priority: 优先级（数值越小越优先，范围0-100）
            description: 策略描述
            is_async: 是否为异步函数
            timeout_seconds: 超时时间（秒）
        """
        self._strategies[name] = {
            "name": name,
            "func": func,
            "conflict_types": conflict_types,
            "priority": priority,
            "description": description,
            "is_async": is_async,
            "timeout_seconds": timeout_seconds,
        }

        for ctype in conflict_types:
            existing = self._conflict_strategies[ctype]
            if name not in existing:
                existing.append(name)
                # 按优先级排序
                existing.sort(key=lambda n: self._strategies[n]["priority"])

        logger.info(
            f"[策略注册] '{name}' 已注册 (冲突类型: {conflict_types}, "
            f"优先级: {priority}, 异步: {is_async})"
        )

    def unregister_strategy(self, name: str) -> None:
        """注销策略"""
        if name in self._strategies:
            info = self._strategies.pop(name)
            for ctype in info["conflict_types"]:
                if ctype in self._conflict_strategies and name in self._conflict_strategies[ctype]:
                    self._conflict_strategies[ctype].remove(name)
            logger.info(f"[策略注册] '{name}' 已注销")

    def get_strategies_for_conflict(
        self,
        conflict_type: str,
        top_n: Optional[int] = None,
        dynamic_priority: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        获取适用于特定冲突类型的策略列表（按优先级排序）

        Args:
            conflict_type: 冲突类型（如 "time_overlap", "geo_distance"）
            top_n: 只返回前N个最优策略
            dynamic_priority: 是否根据历史成功率动态调整优先级

        Returns:
            策略信息列表
        """
        names = list(self._conflict_strategies.get(conflict_type, []))
        # 也添加通用策略（冲突类型为 "*" 的表示适用于所有冲突）
        generic_names = list(self._conflict_strategies.get("*", []))
        for gn in generic_names:
            if gn not in names:
                names.append(gn)

        strategy_infos = []
        for name in names:
            info = self._strategies.get(name)
            if info:
                base_priority = info["priority"]

                if dynamic_priority:
                    # 根据历史成功率动态调整优先级
                    stats = self._stats[name]
                    if stats["total"] > 0:
                        success_rate = stats["success"] / stats["total"]
                        # 成功率越高，优先级数值越低（更优先）
                        # 基础优先级基础上减去成功率*20的偏移
                        adjusted = base_priority - (success_rate * 20)
                    else:
                        adjusted = base_priority
                else:
                    adjusted = base_priority

                strategy_infos.append({
                    "name": name,
                    "func": info["func"],
                    "priority": adjusted,
                    "base_priority": base_priority,
                    "description": info["description"],
                    "is_async": info["is_async"],
                    "timeout_seconds": info["timeout_seconds"],
                    "conflict_types": info["conflict_types"],
                })

        # 按调整后的优先级排序
        strategy_infos.sort(key=lambda s: s["priority"])

        if top_n and top_n > 0:
            strategy_infos = strategy_infos[:top_n]

        return strategy_infos

    def get_all_strategies(self) -> List[Dict[str, Any]]:
        """获取所有注册的策略"""
        return [
            {
                "name": name,
                "priority": info["priority"],
                "conflict_types": info["conflict_types"],
                "description": info["description"],
                "is_async": info["is_async"],
            }
            for name, info in sorted(
                self._strategies.items(), key=lambda x: x[1]["priority"]
            )
        ]

    def record_result(self, strategy_name: str, success: bool) -> None:
        """
        记录策略执行结果

        Args:
            strategy_name: 策略名称
            success: 是否成功
        """
        stats = self._stats[strategy_name]
        stats["total"] += 1
        if success:
            stats["success"] += 1
        stats["last_used"] = time.time()

    def get_success_rates(self) -> Dict[str, float]:
        """
        获取所有策略的成功率

        Returns:
            {strategy_name: success_rate (0.0~1.0)}
        """
        rates = {}
        for name, stats in self._stats.items():
            if stats["total"] > 0:
                rates[name] = stats["success"] / stats["total"]
            else:
                rates[name] = 0.0
        return rates

    def get_stats(self) -> Dict[str, Dict[str, float]]:
        """获取所有策略的详细统计"""
        return dict(self._stats)

    def reset_stats(self, strategy_name: Optional[str] = None) -> None:
        """重置统计信息"""
        if strategy_name:
            self._stats[strategy_name] = {"success": 0, "total": 0, "last_used": 0.0}
        else:
            self._stats.clear()

    @property
    def strategy_count(self) -> int:
        return len(self._strategies)

    @property
    def conflict_type_count(self) -> int:
        return len(self._conflict_strategies)


class StrategySelector:
    """
    策略选择器（单例）

    根据冲突类型动态选择策略，支持并行尝试和成功率记忆。
    封装了 StrategyRegistry 的操作。
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
        self.registry = StrategyRegistry()
        # 并行尝试超时（秒）
        self.parallel_timeout = 10.0
        # 是否启用动态优先级
        self.dynamic_priority_enabled = True
        # 默认返回的策略数量
        self.default_top_n = 3
        logger.info("[策略选择器] 初始化完成")

    def select_strategies(
        self,
        conflict_type: str,
        top_n: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        为指定冲突类型选择最优策略列表

        Args:
            conflict_type: 冲突类型
            top_n: 返回的策略数量（None=全部）

        Returns:
            按优先级排序的策略列表
        """
        return self.registry.get_strategies_for_conflict(
            conflict_type=conflict_type,
            top_n=top_n or self.default_top_n,
            dynamic_priority=self.dynamic_priority_enabled,
        )

    def select_best_strategy(
        self,
        conflict_type: str,
    ) -> Optional[Dict[str, Any]]:
        """
        为指定冲突类型选择最优策略

        Args:
            conflict_type: 冲突类型

        Returns:
            最优策略信息，如果没有适用的策略则返回None
        """
        strategies = self.select_strategies(conflict_type, top_n=1)
        return strategies[0] if strategies else None

    def record_success(self, strategy_name: str) -> None:
        """记录策略执行成功"""
        self.registry.record_result(strategy_name, success=True)

    def record_failure(self, strategy_name: str) -> None:
        """记录策略执行失败"""
        self.registry.record_result(strategy_name, success=False)

    def get_success_rates(self) -> Dict[str, float]:
        """获取所有策略的成功率"""
        return self.registry.get_success_rates()

    def print_strategy_stats(self) -> str:
        """打印策略统计信息"""
        lines = ["=" * 60, "策略统计信息", "=" * 60]
        for name, info in sorted(
            self.registry._strategies.items(), key=lambda x: x[1]["priority"]
        ):
            stats = self.registry._stats[name]
            rate = (
                f"{stats['success'] / stats['total'] * 100:.1f}%"
                if stats["total"] > 0
                else "N/A"
            )
            lines.append(
                f"  {name:40s} | 优先级:{info['priority']:3d} | "
                f"成功:{int(stats['success']):3d}/{int(stats['total']):3d} ({rate})"
            )
        lines.append("=" * 60)
        return "\n".join(lines)


# ==================== 冲突类型映射 ====================

# 冲突类型 -> 适用的策略名称（按推荐优先级排序）
CONFLICT_STRATEGY_MAP = {
    "time_overlap": [
        "strategy_time_shift",
        "strategy_swap_time_slot",
        "strategy_compress_duration",
        "strategy_replace_activity",
        "strategy_cross_day_move",
        "strategy_transport_split",
    ],
    "outside_opening_hours": [
        "strategy_adjust_opening_hours",
        "strategy_time_shift",
        "strategy_swap_time_slot",
        "strategy_replace_activity",
    ],
    "partial_outside_opening_hours": [
        "strategy_adjust_opening_hours",
        "strategy_time_shift",
    ],
    "closed_day": [
        "strategy_closed_day_resolve",
        "strategy_cross_day_move",
        "strategy_replace_activity",
    ],
    "geo_distance": [
        "strategy_geo_distance_split",
        "strategy_geo_distance_replace",
        "strategy_cross_day_move",
        "strategy_replace_activity",
    ],
    "geo_distance_warning": [
        "strategy_geo_distance_split",
        "strategy_geo_distance_replace",
    ],
    "budget_exceeded": [
        "strategy_replace_activity",
    ],
    "unreasonable_time": [
        "strategy_time_shift",
        "strategy_swap_time_slot",
    ],
    "too_short_duration": [],
    "too_long_duration": [
        "strategy_compress_duration",
    ],
    "overloaded_day": [
        "strategy_cross_day_move",
        "strategy_time_shift",
        "strategy_compress_duration",
    ],
}


def register_default_strategies(strategy_selector_instance: StrategySelector) -> None:
    """
    注册默认的协商修复策略

    将 negotiation_service.py 中的策略函数注册到策略选择器。
    此函数应在启动时或首次使用策略选择器之前调用。

    Args:
        strategy_selector_instance: 策略选择器实例
    """
    registry = strategy_selector_instance.registry

    # 注意：这些函数的引用将在运行时解析
    # 实际注册时，从 negotiation_service 模块获取函数引用
    from src.services.negotiation_service import (
        strategy_time_shift,
        strategy_swap_time_slot,
        strategy_compress_duration,
        strategy_replace_activity,
        strategy_cross_day_move,
        strategy_adjust_opening_hours,
        strategy_closed_day_resolve,
        strategy_transport_split,
        strategy_geo_distance_split,
        strategy_geo_distance_replace,
    )

    # 注册每个策略（按文档中的优先级顺序）
    registry.register_strategy(
        name="strategy_time_shift",
        func=strategy_time_shift,
        conflict_types=[
            "time_overlap", "outside_opening_hours", "unreasonable_time",
            "overloaded_day", "*",  # 通用策略
        ],
        priority=10,
        description="时间平移：整体平移冲突活动的起止时间",
    )

    registry.register_strategy(
        name="strategy_adjust_opening_hours",
        func=strategy_adjust_opening_hours,
        conflict_types=[
            "outside_opening_hours", "partial_outside_opening_hours", "*",
        ],
        priority=15,
        description="开放时间适配：将活动时间平移到开放时段内",
    )

    registry.register_strategy(
        name="strategy_swap_time_slot",
        func=strategy_swap_time_slot,
        conflict_types=[
            "time_overlap", "unreasonable_time", "overloaded_day", "*",
        ],
        priority=20,
        description="时段交换：交换冲突活动的上午/下午时间段",
    )

    registry.register_strategy(
        name="strategy_compress_duration",
        func=strategy_compress_duration,
        conflict_types=[
            "time_overlap", "too_long_duration", "overloaded_day", "*",
        ],
        priority=25,
        description="时长压缩：缩短冲突活动的游览时长至45分钟",
    )

    registry.register_strategy(
        name="strategy_replace_activity",
        func=strategy_replace_activity,
        conflict_types=[
            "time_overlap", "closed_day", "geo_distance",
            "budget_exceeded", "outside_opening_hours",
        ],
        priority=30,
        description="活动替换：用备选景点替换冲突景点",
    )

    registry.register_strategy(
        name="strategy_cross_day_move",
        func=strategy_cross_day_move,
        conflict_types=[
            "time_overlap", "closed_day", "geo_distance",
            "overloaded_day", "*",
        ],
        priority=35,
        description="跨天移动：将冲突活动移动到活动最少的一天",
    )

    registry.register_strategy(
        name="strategy_closed_day_resolve",
        func=strategy_closed_day_resolve,
        conflict_types=["closed_day"],
        priority=40,
        description="闭馆日解决：将安排在被闭馆日的景点移至其他天",
    )

    registry.register_strategy(
        name="strategy_transport_split",
        func=strategy_transport_split,
        conflict_types=["time_overlap"],
        priority=45,
        description="交通段拆分：拆分交通与餐饮的时间重叠",
    )

    registry.register_strategy(
        name="strategy_geo_distance_split",
        func=strategy_geo_distance_split,
        conflict_types=["geo_distance", "geo_distance_warning"],
        priority=50,
        description="地理距离拆分：将远距离景点跨天分配到不同天",
    )

    registry.register_strategy(
        name="strategy_geo_distance_replace",
        func=strategy_geo_distance_replace,
        conflict_types=["geo_distance", "geo_distance_warning"],
        priority=55,
        description="地理距离替换：用备选景点替换远距离景点",
    )

    logger.info(
        f"[策略注册] 已注册 {registry.strategy_count} 个策略，"
        f"覆盖 {registry.conflict_type_count} 种冲突类型"
    )


# ==================== 全局单例 ====================

strategy_selector = StrategySelector()
