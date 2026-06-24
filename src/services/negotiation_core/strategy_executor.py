"""
策略执行器模块

替代 negotiate_and_fix() 中 300 行的 if/elif 硬编码链，
通过 StrategyExecutor 统一调度所有策略。

核心职责:
1. 根据冲突类型从 strategy_selector 获取推荐策略列表
2. 通过策略适配器按优先级顺序尝试策略（无需 if/elif）
3. 处理策略结果（单天/多天）
4. 记录策略执行统计

【重构】移除了 execute_strategy() 中的 if/elif 硬编码链。
每个策略在注册时附带一个适配器（adapter），负责将统一调用参数
转换为该策略的具体参数签名。新增策略只需：
  1. 写策略函数
  2. 在 register_default_strategies() 中注册策略 + 适配器
无需修改 StrategyExecutor 的任何代码。

【第三阶段】效用驱动策略选择：
  try_strategies_chain() 改为尝试所有可行策略，选择效用最高的，
  而不是按固定优先级顺序只取第一个成功的。
"""

import logging
import copy
from typing import Dict, Any, List, Optional, Tuple, Callable

from src.services.negotiation_strategies import (
    strategy_selector,
)

logger = logging.getLogger(__name__)


class StrategyExecutor:
    """
    策略执行器（单例，第三阶段增强版）

    将策略选择 + 执行 + 结果处理 封装为统一接口。
    外部只需调用 try_strategies_chain() 方法。

    职责链:
    1. select_strategies(conflict_type) → 获取策略列表
    2. try_strategies_in_order() → 通过适配器依次尝试（无 if/elif）
    3. handle_result() → 处理结果（单天/多天）

    【第三阶段改动】
    - try_strategies_chain() 尝试所有可行策略，收集候选方案
    - 使用 utility_evaluator.select_best_strategy_result() 选择效用最高的
    - 保持对旧接口的兼容

    核心设计：
    - 每个策略注册时附带一个适配器函数（adapter）
    - 适配器的统一签名：
        adapter(day_plans, day_idx, conflict, conflict_type,
                backup_attractions, structured_requirement)
        -> (result, is_multi_day)
    - execute_strategy() 通过 adapter 调用策略，不再使用 if/elif
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
        self.select_top_n = 8
        # 【第三阶段】是否启用效用驱动选择
        self.use_utility_driven_selection = True
        logger.info("[策略执行器] 第三阶段增强版初始化完成")

    def select_strategies(self, conflict_type: str) -> List[Dict[str, Any]]:
        """
        选择适用于指定冲突类型的策略列表

        Args:
            conflict_type: 冲突类型

        Returns:
            策略信息列表（按优先级排序）
        """
        strategies = strategy_selector.select_strategies(
            conflict_type=conflict_type,
            top_n=self.select_top_n,
        )

        if strategies:
            logger.debug(
                f"[策略执行器] 冲突类型={conflict_type}, "
                f"推荐策略: {[s['name'] for s in strategies]}"
            )
            return strategies

        # 回退：策略选择器无推荐时，使用 fallback 列表
        logger.debug(
            f"[策略执行器] 冲突类型={conflict_type}: 策略选择器无推荐, 回退默认"
        )
        return self._fallback_strategies()

    def _fallback_strategies(self) -> List[Dict[str, Any]]:
        """当策略选择器无推荐时的回退方案"""
        fallback = []
        registry = strategy_selector.registry
        for fallback_name in [
            "strategy_time_shift",
            "strategy_adjust_opening_hours",
            "strategy_swap_time_slot",
            "strategy_compress_duration",
            "strategy_replace_activity",
            "strategy_cross_day_move",
            "strategy_closed_day_resolve",
            "strategy_transport_split",
            "strategy_geo_distance_split",
            "strategy_geo_distance_replace",
        ]:
            if fallback_name in registry._strategies:
                info = registry._strategies[fallback_name]
                fallback.append({
                    "name": fallback_name,
                    "func": info["func"],
                    "priority": info["priority"],
                    "description": info.get("description", ""),
                    "is_async": info.get("is_async", False),
                    "conflict_types": info.get("conflict_types", []),
                })

        if not fallback:
            # 终极回退：所有已注册策略
            all_names = sorted(
                registry._strategies.keys(),
                key=lambda n: registry._strategies[n]["priority"]
            )
            for name in all_names:
                info = registry._strategies[name]
                fallback.append({
                    "name": name,
                    "func": info["func"],
                    "priority": info["priority"],
                    "description": info.get("description", ""),
                    "is_async": info.get("is_async", False),
                    "conflict_types": info.get("conflict_types", []),
                })

        return fallback

    def execute_strategy(
        self,
        strategy_info: Dict[str, Any],
        day_plans: List[dict],
        day_idx: int,
        conflict: Dict[str, Any],
        conflict_type: str,
        backup_attractions: Optional[List[dict]],
        structured_requirement: Optional[dict],
    ) -> Tuple[Optional[Any], bool]:
        """
        执行单个策略（通过适配器，无 if/elif）

        每个策略在注册时附带一个适配器函数（adapter），
        适配器知道如何将统一调用参数转换为该策略的具体参数签名。

        Args:
            strategy_info: 策略信息（含 name, func 等）
            day_plans: 当前全部行程计划
            day_idx: 当前处理的 day 索引
            conflict: 冲突信息
            conflict_type: 冲突类型
            backup_attractions: 备选景点列表
            structured_requirement: 结构化需求

        Returns:
            (result, is_multi_day) 其中:
              - result: 策略执行结果（dict 或 List[dict] 或 None）
              - is_multi_day: 结果是否为多天格式
        """
        strategy_name = strategy_info["name"]
        registry = strategy_selector.registry

        # 边界检查：day_idx 越界
        if day_idx < 0 or day_idx >= len(day_plans):
            return (None, False)

        # 边界检查：冲突为空，跳过执行
        if not conflict or not any(conflict.values()):
            return (None, False)

        try:
            # ========== 通过适配器调用策略（无 if/elif） ==========
            # 从注册表中获取该策略的适配器函数
            adapter = registry.get_adapter(strategy_name)

            if adapter is not None:
                # 通过适配器调用，适配器负责处理参数转换和前置条件检查
                result, is_multi_day = adapter(
                    day_plans,
                    day_idx,
                    conflict,
                    conflict_type,
                    backup_attractions,
                    structured_requirement,
                )

                if result is not None and result is not False:
                    return (result, is_multi_day)

                # 策略执行失败（适配器返回 None/False）
                strategy_selector.record_failure(strategy_name)
                return (None, False)

            # ========== 没有适配器时的回退：直接调用 func ==========
            # 这种情况只在新增策略忘记注册适配器时发生
            current_day_plan = day_plans[day_idx]
            result = strategy_info["func"](current_day_plan, conflict)

            if result is not None and result is not False:
                logger.warning(
                    f"[策略执行器] 策略 '{strategy_name}' 无适配器，"
                    f"使用默认调用方式成功"
                )
                is_multi_day = isinstance(result, list)
                return (result, is_multi_day)

            strategy_selector.record_failure(strategy_name)
            return (None, False)

        except Exception as e:
            logger.warning(
                f"[策略执行器] 策略 '{strategy_name}' 执行异常: {e}"
            )
            strategy_selector.record_failure(strategy_name)
            return (None, False)

    def try_strategies_chain(
        self,
        day_plans: List[dict],
        day_idx: int,
        conflict: Dict[str, Any],
        conflict_type: str,
        backup_attractions: Optional[List[dict]],
        structured_requirement: Optional[dict],
    ) -> Tuple[Optional[Any], bool, str]:
        """
        尝试策略链

        【第三阶段】效用驱动选择：
        尝试所有可行策略，收集候选方案，选择效用最高的。
        替代原有的"按固定优先级顺序尝试，第一个成功就返回"。

        Args:
            day_plans: 当前全部行程计划
            day_idx: 当前处理的 day 索引
            conflict: 冲突信息
            conflict_type: 冲突类型
            backup_attractions: 备选景点列表
            structured_requirement: 结构化需求

        Returns:
            (final_result, is_multi_day, strategy_name)
            如果所有策略都失败，返回 (None, False, "")
        """
        # 边界情况检查：无效冲突、无效 day_idx
        if not conflict or not isinstance(conflict, dict):
            return (None, False, None) #type:ignore

        # 未知冲突类型检查：如果冲突类型非空且没有专用的（非通配符"*"）策略匹配，
        # 则直接返回 None，避免通配符策略在未知类型上意外执行产生不可预测的结果
        if conflict_type and conflict_type.strip():
            from src.services.negotiation_strategies import strategy_selector as _sel
            # 检查 registry 中是否有为该冲突类型注册的专用策略（含通配符"*"以外的匹配）
            registry = _sel.registry
            # 检查 _conflict_strategies 中是否有该冲突类型的专属条目
            # 注意：通配符"*"是通用策略，对所有类型都匹配，不属于专属匹配
            dedicated_types = set(registry._conflict_strategies.keys()) - {"*"}
            has_dedicated = conflict_type in dedicated_types
            if not has_dedicated:
                return (None, False, "") #type:ignore

        # day_idx 越界检查（负数或超出范围）
        if day_idx < 0 or day_idx >= len(day_plans):
            return (None, False, None) #type:ignore

        strategies = self.select_strategies(conflict_type)

        if not strategies:
            return (None, False, None) #type:ignore

        if self.use_utility_driven_selection and structured_requirement:
            # ========== 第三阶段：效用驱动选择 ==========
            # 尝试所有可行策略，收集候选方案
            candidates = []  # [(strategy_name, result, is_multi_day), ...]

            for strategy_info in strategies:
                strategy_name = strategy_info["name"]

                result, is_multi_day = self.execute_strategy(
                    strategy_info=strategy_info,
                    day_plans=day_plans,
                    day_idx=day_idx,
                    conflict=conflict,
                    conflict_type=conflict_type,
                    backup_attractions=backup_attractions,
                    structured_requirement=structured_requirement,
                )

                if result is not None:
                    candidates.append((strategy_name, result, is_multi_day))
                    strategy_selector.record_success(strategy_name)
                else:
                    strategy_selector.record_failure(strategy_name)

            if not candidates:
                return (None, False, "")

            # 使用效用函数选择最佳方案
            # 构造候选方案的效用比较输入
            from src.services.negotiation_utility import utility_evaluator

            # 将每个候选结果应用到行程，再计算效用
            utility_candidates = []
            for strategy_name, result, is_multi_day in candidates:
                proposed_plans = self.apply_strategy_result(
                    day_plans=copy.deepcopy(day_plans),
                    day_idx=day_idx,
                    result=result,
                    is_multi_day=is_multi_day,
                    strategy_name=strategy_name,
                )
                utility_candidates.append(
                    (strategy_name, proposed_plans, conflict, [])
                )

            best_strategy, best_plans, best_utility = (
                utility_evaluator.select_best_strategy_result(
                    candidates=utility_candidates,
                    structured_requirement=structured_requirement,
                )
            )

            if best_strategy is None or best_plans is None:
                # 兜底：取第一个候选
                best_name, best_result, best_multi = candidates[0]
                logger.info(
                    f"[效用驱动] 效用选择无结果，兜底取第一个: {best_name}"
                )
                return (best_result, best_multi, best_name)

            # 找到原始 result 和 is_multi_day
            for strategy_name, result, is_multi_day in candidates:
                if strategy_name == best_strategy:
                    logger.info(
                        f"[效用驱动] 选中策略 '{best_strategy}': "
                        f"utility={best_utility.overall_with_penalty:.4f}"  #type:ignore
                    )
                    return (result, is_multi_day, best_strategy)

            # 兜底
            best_name, best_result, best_multi = candidates[0]
            return (best_result, best_multi, best_name)

        else:
            # ========== 传统模式：按优先级顺序尝试，第一个成功就返回 ==========
            for strategy_info in strategies:
                strategy_name = strategy_info["name"]

                result, is_multi_day = self.execute_strategy(
                    strategy_info=strategy_info,
                    day_plans=day_plans,
                    day_idx=day_idx,
                    conflict=conflict,
                    conflict_type=conflict_type,
                    backup_attractions=backup_attractions,
                    structured_requirement=structured_requirement,
                )

                if result is not None:
                    strategy_selector.record_success(strategy_name)
                    return (result, is_multi_day, strategy_name)

            return (None, False, "")

    def apply_strategy_result(
        self,
        day_plans: List[dict],
        day_idx: int,
        result: Any,
        is_multi_day: bool,
        strategy_name: str,
    ) -> List[dict]:
        """
        将策略结果应用到 day_plans

        Args:
            day_plans: 原始行程计划
            day_idx: 当前 day 索引
            result: 策略执行结果
            is_multi_day: 结果是否为多天格式
            strategy_name: 策略名称（用于日志）

        Returns:
            应用结果后的新 day_plans（深拷贝）
        """
        proposed = copy.deepcopy(day_plans)

        if is_multi_day and isinstance(result, list):
            proposed = result
        elif isinstance(result, dict) and result.get("attractions") is not None:
            proposed[day_idx] = result

        return proposed

    def record_result(self, strategy_name: str, success: bool) -> None:
        """记录策略执行结果"""
        if success:
            strategy_selector.record_success(strategy_name)
        else:
            strategy_selector.record_failure(strategy_name)

    def print_stats(self) -> str:
        """打印策略统计信息"""
        return strategy_selector.print_strategy_stats()


# 全局单例
strategy_executor = StrategyExecutor()