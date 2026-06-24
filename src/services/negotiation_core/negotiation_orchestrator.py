"""
协商协调器

将 negotiate_and_fix() 巨型函数（~600 行）拆分为职责清晰的子函数。

拆分方案:
  negotiate_and_fix()                    # 只剩下 orchestration 逻辑（~80行）
  ├── call_negotiation_round()           # 单轮协商逻辑
  │   ├── resolve_day_conflicts()        # 单天冲突解决
  │   │   ├── try_strategy_chain()       # 策略链执行（委托 StrategyExecutor）
  │   │   ├── validate_repair_result()   # 修复后验证（委托 RepairValidator）
  │   │   └── collect_agent_feedback()   # Agent反馈收集（委托 RepairValidator）
  │   └── evaluate_round_progress()      # 评估本轮进展
  ├── handle_no_fix_situation()          # 无修复时的处理
  │   ├── trigger_global_reshuffle()     # 触发全局重排
  │   └── should_early_terminate()       # 是否提前终止
  └── build_final_result()               # 构建最终结果

【第三阶段】效用驱动的智能优化
  - 提前终止条件：从"有无error"改为"效用值达到阈值或连续N轮无改善"
  - 启动时从 structured_requirement 读取用户权重偏好
  - 每一轮记录效用变化，用于判断是否收敛
"""

from __future__ import annotations

import logging
import copy
import math
import uuid
from typing import Dict, Any, List, Optional, Tuple

from src.services.negotiation_utility import UtilityResult

logger = logging.getLogger(__name__)


def local_search_reshuffle(day_plans: List[dict], structured_requirement: dict) -> None:
    """
    局部搜索优化 - 逐步逼近最优分配（替代原有的全量聚类重排）

    【第三阶段改进】用局部搜索替代全局重排：
    原有全局重排会一次性打散所有景点再重新聚类，破坏性大。
    改为局部搜索：每次只移动一个景点到相邻天，评价效用变化，
    只接受效用提升的修改，逐步逼近最优解。

    流程:
      1. 对每天的景点按纬度排序（保持天内顺序合理）
      2. 找出"最不适配"的景点（与同天其他景点平均距离最远）
      3. 尝试将其移动到相邻天，评估效用变化
      4. 如果效用提升则接受，否则回滚
      5. 重复直到没有改进或达到最大迭代次数

    Args:
        day_plans: 每日行程列表（就地修改）
        structured_requirement: 结构化需求
    """
    if len(day_plans) <= 1:
        return

    from src.services.negotiation_utility import utility_evaluator

    max_iterations = 20
    min_utility_delta = 0.01  # 最小效用改善阈值
    num_days = len(day_plans)

    # 预处理：同一天内的景点按纬度排序（保证顺序合理性）
    for plan in day_plans:
        attrs = plan.get("attractions", [])
        valid = [a for a in attrs if isinstance(a, dict)]
        if len(valid) >= 2:
            valid.sort(key=lambda x: x.get("location", {}).get("lat", 0)
                       if isinstance(x.get("location"), dict) else 0)
            plan["attractions"] = valid

    # 获取初始效用
    current_utility = _compute_reshuffle_utility(day_plans, structured_requirement)
    logger.info(f"[局部搜索] 初始效用: {current_utility:.4f}")

    for iteration in range(max_iterations):
        # 找所有天中最不适配的景点
        best_move = None
        best_move_utility = current_utility

        for src_day_idx in range(num_days):
            src_attrs = day_plans[src_day_idx].get("attractions", [])
            valid_src = [a for a in src_attrs if isinstance(a, dict)]
            if not valid_src:
                continue

            for attr in valid_src:
                # 计算该景点与同天其他景点的平均距离
                same_day_dist = _avg_distance_to_others(attr, valid_src)

                # 尝试移动到相邻天（前/后一天）
                for target_day_delta in (-1, 1):
                    tgt_day_idx = src_day_idx + target_day_delta
                    if tgt_day_idx < 0 or tgt_day_idx >= num_days:
                        continue

                    tgt_attrs = day_plans[tgt_day_idx].get("attractions", [])
                    valid_tgt = [a for a in tgt_attrs if isinstance(a, dict)]

                    # 计算目标天的总时长，防止过载
                    if _is_day_overloaded_after_add(day_plans[tgt_day_idx], structured_requirement):
                        continue

                    # 模拟移动后的效用
                    trial_plans = copy.deepcopy(day_plans)
                    # 从源天移除
                    trial_plans[src_day_idx]["attractions"] = [
                        a for a in trial_plans[src_day_idx].get("attractions", [])
                        if isinstance(a, dict) and a.get("name") != attr.get("name")
                    ]
                    # 插入目标天（按纬度排序插入）
                    trial_plans[tgt_day_idx]["attractions"].append(copy.deepcopy(attr))
                    trial_plans[tgt_day_idx]["attractions"].sort(
                        key=lambda x: x.get("location", {}).get("lat", 0)
                        if isinstance(x.get("location"), dict) else 0
                    )

                    trial_utility = _compute_reshuffle_utility(trial_plans, structured_requirement)
                    utility_gain = trial_utility - current_utility

                    if utility_gain > best_move_utility - current_utility + min_utility_delta:
                        best_move_utility = trial_utility
                        best_move = (src_day_idx, tgt_day_idx, attr)

        if best_move is None or best_move_utility <= current_utility + min_utility_delta:
            logger.info(
                f"[局部搜索] 第{iteration + 1}轮: 无有效改进, "
                f"当前效用={current_utility:.4f}, 停止搜索"
            )
            break

        # 执行最优移动
        src_idx, tgt_idx, attr = best_move
        attr_name = attr.get("name", "")
        day_plans[src_idx]["attractions"] = [
            a for a in day_plans[src_idx].get("attractions", [])
            if isinstance(a, dict) and a.get("name") != attr_name
        ]
        day_plans[tgt_idx]["attractions"].append(copy.deepcopy(attr))
        day_plans[tgt_idx]["attractions"].sort(
            key=lambda x: x.get("location", {}).get("lat", 0)
            if isinstance(x.get("location"), dict) else 0
        )

        current_utility = best_move_utility
        logger.info(
            f"[局部搜索] 第{iteration + 1}轮: 移动'{attr_name}' "
            f"从第{src_idx + 1}天→第{tgt_idx + 1}天, "
            f"效用={current_utility:.4f}"
        )

    logger.info(f"[局部搜索] 完成, 最终效用={current_utility:.4f}")


def _compute_reshuffle_utility(
    day_plans: List[dict],
    structured_requirement: dict,
) -> float:
    """
    计算重排过程中使用的效用值（轻量版，仅考虑地理紧凑性和时间合理性）

    Args:
        day_plans: 行程计划
        structured_requirement: 结构化需求

    Returns:
        效用值 (0~1)，越高越好
    """
    from src.services.negotiation_utility import utility_evaluator
    from .conflict_detector import detect_conflicts

    detection = detect_conflicts(day_plans, structured_requirement)
    result = utility_evaluator.evaluate(
        day_plans, structured_requirement,
        conflicts=detection.conflicts,
    )
    return result.overall_with_penalty


def _avg_distance_to_others(attr: dict, others: List[dict]) -> float:
    """
    计算一个景点与其他景点的平均地理距离

    Args:
        attr: 目标景点
        others: 同天其他景点列表

    Returns:
        平均距离（km），如果无法计算返回极大值
    """
    loc = attr.get("location", {})
    lat = loc.get("lat") if isinstance(loc, dict) else None
    lng = loc.get("lng") if isinstance(loc, dict) else None

    if lat is None or lng is None:
        return float('inf')

    total_dist = 0.0
    count = 0
    for other in others:
        if other.get("name") == attr.get("name"):
            continue
        other_loc = other.get("location", {})
        o_lat = other_loc.get("lat") if isinstance(other_loc, dict) else None
        o_lng = other_loc.get("lng") if isinstance(other_loc, dict) else None
        if o_lat is not None and o_lng is not None:
            total_dist += _haversine_km(
                {"lat": float(lat), "lng": float(lng)},
                {"lat": float(o_lat), "lng": float(o_lng)},
            )
            count += 1

    return total_dist / count if count > 0 else float('inf')


def _is_day_overloaded_after_add(
    day_plan: dict,
    structured_requirement: dict,
) -> bool:
    """
    检查如果向某天添加一个景点后是否会超载

    Args:
        day_plan: 目标天的行程
        structured_requirement: 结构化需求

    Returns:
        True 表示会超载
    """
    max_daily = structured_requirement.get("max_daily_attractions", 5)
    current_count = len([
        a for a in day_plan.get("attractions", []) if isinstance(a, dict)
    ])
    return current_count >= max_daily
def _haversine_km(loc1: Optional[dict], loc2: Optional[dict]) -> float:
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


def _sort_by_utility(
    day_plan: dict,
    structured_requirement: Optional[dict] = None,
) -> Optional[dict]:
    """
    按综合效用评估排序景点顺序（代替纯按纬度排序）

    尝试多种排序方式，选择综合效用最高的方案：
    1. 按纬度排序（原方案）
    2. 按经度排序
    3. 按地理中心距离排序（贪心最近邻）

    Args:
        day_plan: 单日行程
        structured_requirement: 结构化需求（可选）

    Returns:
        优化后的 day_plan，如果无法优化返回 None
    """
    from src.services.negotiation_utility import utility_evaluator
    from .conflict_detector import detect_conflicts

    attractions = day_plan.get("attractions", [])
    valid = [a for a in attractions if isinstance(a, dict)]
    if len(valid) <= 2:
        return None

    # 生成多种候选排序
    candidates = []

    # 方案1：按纬度排序（原版方案）
    by_lat = sorted(
        copy.deepcopy(valid),
        key=lambda x: x.get("location", {}).get("lat", 0)
        if isinstance(x.get("location"), dict) else 0
    )
    candidates.append(("纬度排序", by_lat))

    # 方案2：按经度排序
    by_lng = sorted(
        copy.deepcopy(valid),
        key=lambda x: x.get("location", {}).get("lng", 0)
        if isinstance(x.get("location"), dict) else 0
    )
    candidates.append(("经度排序", by_lng))

    # 方案3：贪心最近邻（从第一个景点开始，每次选最近的下一个）
    if len(valid) >= 3:
        greedy = _greedy_nearest_neighbor(copy.deepcopy(valid))
        if greedy:
            candidates.append(("贪心最近邻", greedy))

    # 对每个候选方案计算效用
    from .pareto_optimizer import pareto_optimizer, ParetoCandidate

    best_score = -float('inf')
    best_candidate = None
    best_name = ""

    for name, attrs in candidates:
        trial_plan = copy.deepcopy(day_plan)
        trial_plan["attractions"] = attrs

        # 收集 long_distance_warnings（保持与旧版兼容）
        long_warnings = _check_long_distance_segments(attrs)
        if long_warnings:
            trial_plan["_long_distance_warnings"] = long_warnings

        # 只在有 structured_requirement 时计算效用
        if structured_requirement:
            # === 【第三阶段】Pareto 多目标优化 ===
            # 计算交通时间、冲突惩罚、效用的客观值
            transport, penalty, utility = pareto_optimizer.compute_objectives(
                [trial_plan], structured_requirement
            )
            score = utility

            # 检查：如果候选数量 >= 3，用 Pareto 前沿替代单纯效用比较
            if len(candidates) >= 3:
                # 累加到 Pareto 候选列表，后端统一用 Pareto 前沿筛选
                pass  # Pareto 筛选在下方统一处理
        else:
            # 无结构化需求时，用交通时长估算作为评分
            score = -_estimate_total_transport_time(attrs)

        logger.debug(
            f"[路线排序] {name}: score={score:.4f}"
        )

        if score > best_score:
            best_score = score
            best_candidate = attrs
            best_name = name

    # === 【第三阶段】Pareto 前沿增强 ===
    # 如果有结构化需求且候选 >= 3，使用 Pareto 前沿选择
    if structured_requirement and len(candidates) >= 3:
        pareto_input = []
        for name, attrs in candidates:
            trial_plan = copy.deepcopy(day_plan)
            trial_plan["attractions"] = attrs
            pareto_input.append((name, [trial_plan], {}))

        front = pareto_optimizer.compute_pareto_front(
            pareto_input, structured_requirement
        )

        if front:
            # 从 Pareto 前沿中选取一个（默认按效用排序取第一个）
            selected = pareto_optimizer.select_from_pareto(front)
            best_candidate = selected.day_plans[0].get("attractions", [])
            best_name = selected.name
            logger.info(
                f"[路线排序] Pareto前沿选择: '{best_name}' "
                f"(交通={selected.total_transport_time:.0f}min, "
                f"惩罚={selected.conflict_penalty:.4f}, "
                f"效用={selected.utility_score:.4f})"
            )

    if best_candidate is None:
        return None

    result_plan = copy.deepcopy(day_plan)
    result_plan["attractions"] = best_candidate

    logger.debug(
        f"[路线排序] 选择: {best_name} (score={best_score:.4f})"
    )
    return result_plan


def _greedy_nearest_neighbor(attractions: List[dict]) -> Optional[List[dict]]:
    """
    贪心最近邻排序

    从第一个景点开始，每次选择距离当前景点最近的未访问景点。

    Args:
        attractions: 景点列表

    Returns:
        排序后的景点列表
    """
    if not attractions:
        return None

    ordered = [attractions[0]]
    remaining = attractions[1:]

    while remaining:
        current = ordered[-1]
        current_loc = current.get("location", {})

        # 找最近的未访问景点
        nearest_idx = 0
        nearest_dist = float('inf')

        for i, attr in enumerate(remaining):
            attr_loc = attr.get("location", {})
            dist = _haversine_km(current_loc, attr_loc)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_idx = i

        ordered.append(remaining.pop(nearest_idx))

    return ordered


def _check_long_distance_segments(attractions: List[dict]) -> List[dict]:
    """
    检查景点间是否存在超远距离路段

    Args:
        attractions: 排序后的景点列表

    Returns:
        远距离警告列表
    """
    warnings = []
    transport_threshold_min = 90

    for i in range(len(attractions) - 1):
        loc_i = attractions[i].get("location", {})
        loc_j = attractions[i + 1].get("location", {})
        dist = _haversine_km(loc_i, loc_j)
        estimated_duration_min = int((dist / 25) * 60) if dist < float('inf') else 999
        if estimated_duration_min > transport_threshold_min:
            warnings.append({
                "from": attractions[i].get("name", ""),
                "to": attractions[i + 1].get("name", ""),
                "distance_km": round(dist, 1),
                "estimated_duration_min": estimated_duration_min,
                "threshold_min": transport_threshold_min,
            })
    return warnings


def _estimate_total_transport_time(attractions: List[dict]) -> float:
    """
    估算景点间的总交通时间

    Args:
        attractions: 景点列表

    Returns:
        总交通时间（分钟）
    """
    total = 0.0
    for i in range(len(attractions) - 1):
        loc_i = attractions[i].get("location", {})
        loc_j = attractions[i + 1].get("location", {})
        dist = _haversine_km(loc_i, loc_j)
        if dist < float('inf'):
            total += (dist / 25) * 60
    return total

class NegotiationOrchestrator:
    """
    协商协调器（单例，第三阶段增强版）

    管理 negotiate_and_fix() 的多轮迭代协商流程。
    所有子逻辑通过明确的函数调用而非内联代码实现。

    【第三阶段改动】
    - 启动时从 structured_requirement 加载用户权重到 utility_evaluator
    - 提前终止条件：效用值达到阈值或连续N轮无改善
    - 每轮记录效用变化日志
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
        # 连续无修复轮次计数器
        self.no_fix_streak = 0
        # 策略选择器是否已注册标记
        self._strategies_registered = False
        # 【第三阶段】效用记录
        self.utility_history: List[float] = []
        # 【第三阶段】效用无改善连续轮次
        self.utility_stagnation_count = 0
        # 【第三阶段】效用提前终止阈值
        self.utility_terminate_threshold = 0.85
        # 【第三阶段】效用无改善容忍轮数
        self.utility_stagnation_tolerance = 2
        # 【第三阶段】效用改善最小幅度
        self.utility_improvement_min_delta = 0.02
        logger.info("[协商协调器] 第三阶段增强版初始化完成")

    # ==============================================================
    # 主入口
    # ==============================================================

    async def negotiate_and_fix(
        self,
        day_plans: List[dict],
        structured_requirement: dict,
        backup_data: Optional[dict] = None,
        max_iterations: int = 5,
        optimize_route: bool = False,
        use_real_traffic: bool = False,
    ) -> dict:
        """
        核心协商流程：多轮迭代的冲突检测→修复→再检测→再修复

        此函数仅是协调器，所有具体工作委托给子函数。

        【第三阶段】新增功能：
        - 启动时从 structured_requirement 加载用户权重到 utility_evaluator
        - 提前终止条件增强：效用值达到阈值或连续N轮无改善

        Args:
            day_plans: 每日行程列表
            structured_requirement: 结构化需求
            backup_data: 备选景点数据 {"attractions": [...]}
            max_iterations: 最大迭代次数
            optimize_route: 是否在开始时执行一次路线优化
            use_real_traffic: 是否使用真实交通数据

        Returns:
            {
                "day_plans": 修复后的行程,
                "negotiation_log": 协商日志,
                "iteration_count": 实际迭代次数,
                "fully_resolved": bool,
                "validation": {...},
                "negotiation_events": [...],
                "utility_history": [...],   # 【第三阶段】每轮效用记录
            }
        """
        from src.services.negotiation_strategies import register_default_strategies
        from src.services.negotiation_utility import compute_utility_dict, utility_evaluator
        from src.services.negotiation_event_bus import agent_message_bus, AgentMessageType

        # 初始化
        session_id = structured_requirement.get("task_id") or str(uuid.uuid4())
        self.no_fix_streak = 0
        backup_attractions = list((backup_data or {}).get("attractions", []))
        current_plans = copy.deepcopy(day_plans)
        negotiation_log: List[dict] = []

        # 注册策略（首次运行时）
        from src.services.negotiation_strategies import strategy_selector
        if strategy_selector.registry.strategy_count == 0:
            register_default_strategies(strategy_selector)
            logger.info(f"[协商] 已注册{strategy_selector.registry.strategy_count}个策略到动态策略选择器")

        # === 【第三阶段】从需求加载用户权重偏好 ===
        utility_evaluator.configure_weights_from_requirement(structured_requirement)
        logger.info(
            f"[协商] 效用权重已配置: {utility_evaluator.get_weights()}"
        )

        # === 初始化效用记录 ===
        self.utility_history = []
        self.utility_stagnation_count = 0

        # === 【P2】初始化共享上下文（含加权投票默认配置） ===
        ctx = agent_message_bus.get_shared_context(session_id)
        ctx.setdefault("voting_weights", {
            "attractions_agent_001": 0.30,
            "food_agent_001": 0.15,
            "transport_agent_001": 0.25,
            "hotel_agent_001": 0.10,
            "dispatcher": 0.20,
        })
        ctx.setdefault("voting_pass_threshold", 0.60)
        # 协商历史摘要（供LLM参考）
        ctx.setdefault("negotiation_history", [])
        ctx.setdefault("accepted_adjustments", [])
        logger.info(f"[协商] session={session_id}: 共享上下文已初始化")

        # === 发布 CFP 事件 ===
        from .event_publisher import event_publisher
        await event_publisher.publish_cfp(
            session_id=session_id,
            max_iterations=max_iterations,
            total_days=len(current_plans),
            total_attractions=sum(len(p.get("attractions", [])) for p in current_plans),
        )

        # === 通知所有 Agent ===
        broadcast_responses = await agent_message_bus.broadcast(
            from_agent="dispatcher",
            message={
                "type": AgentMessageType.COORDINATE_REQUEST,
                "payload": {
                    "action": "negotiation_start",
                    "session_id": session_id,
                    "max_iterations": max_iterations,
                    "total_days": len(current_plans),
                    "total_attractions": sum(len(p.get("attractions", [])) for p in current_plans),
                }
            },
            session_id=session_id,
        )
        negotiation_log.append({
            "iteration": 0,
            "action": "广播协商开始",
            "target": "all_agents",
            "responses": list(broadcast_responses.keys()) if broadcast_responses else [],
        })

        # === 【改造方案 4.1.2】Agent间信息共享（阶段0） ===
        # 让各 Agent 将领域知识写入共享信息池
        try:
            from src.agents import attractions_agent, transport_agent, food_agent, hotel_agent

            # 收集所有景点和餐厅信息
            all_attractions = []
            all_restaurants = []
            all_hotels = []
            for plan in current_plans:
                all_attractions.extend(plan.get("attractions", []))
                all_restaurants.extend(plan.get("meals", []))
                all_hotels.extend(plan.get("hotels", []))

            # 各Agent写入共享信息（通过模块级便捷函数调用）
            await attractions_agent.share_info(session_id, all_attractions)
            await transport_agent.share_info(session_id, current_plans)
            await food_agent.share_info(session_id, all_restaurants)
            await hotel_agent.share_info(session_id, all_hotels)

            logger.info(
                f"[协商] session={session_id}: Agent间信息共享完成, "
                f"景点={len(all_attractions)}, 餐饮={len(all_restaurants)}, "
                f"酒店={len(all_hotels)}"
            )
        except Exception as e:
            logger.warning(f"[协商] Agent间信息共享异常（非致命）: {e}")

        # === 开始前执行一次路线优化（防震荡改进） ===
        if optimize_route:
            current_plans = await self._do_initial_route_optimization(
                current_plans, use_real_traffic, session_id,
                structured_requirement=structured_requirement,
            )

        # === 初始效用记录 ===
        from .conflict_detector import detect_conflicts
        initial_detection = detect_conflicts(current_plans, structured_requirement)
        initial_utility = utility_evaluator.evaluate(
            current_plans, structured_requirement,
            conflicts=initial_detection.conflicts,
        )
        self.utility_history.append(initial_utility.overall_with_penalty)
        logger.info(
            f"[协商] 初始效用: overall={initial_utility.overall:.4f}, "
            f"with_penalty={initial_utility.overall_with_penalty:.4f}, "
            f"冲突数={initial_detection.total_count}"
        )

        # === 【第三阶段】记录初始方案（供 Pareto 改进对比） ===
        self._initial_day_plans = copy.deepcopy(current_plans)

        # === 主迭代循环 ===
        for iteration in range(max_iterations):
            logger.info(f"[协商] === 第 {iteration + 1} 轮 ===")

            # 调用单轮协商
            round_result = await self._call_negotiation_round(
                current_plans=current_plans,
                structured_requirement=structured_requirement,
                backup_attractions=backup_attractions,
                session_id=session_id,
                iteration=iteration,
                negotiation_log=negotiation_log,
            )

            current_plans = round_result["day_plans"]
            no_errors = round_result["no_errors"]
            any_fixed = round_result["any_fixed"]

            # === 【第三阶段】效用评估 + 提前终止检查 ===
            round_detection = detect_conflicts(current_plans, structured_requirement)
            round_utility = utility_evaluator.evaluate(
                current_plans, structured_requirement,
                conflicts=round_detection.conflicts,
            )
            self.utility_history.append(round_utility.overall_with_penalty)

            logger.info(
                f"[协商] 第{iteration + 1}轮效用: "
                f"overall={round_utility.overall:.4f}, "
                f"with_penalty={round_utility.overall_with_penalty:.4f}, "
                f"冲突数={round_detection.total_count}"
            )

            # === 【第四阶段】发布本轮进度到 WebSocket ===
            fixes_count = 1 if any_fixed else 0
            await event_publisher.publish_round_progress(
                session_id=session_id,
                iteration=iteration,
                max_iterations=max_iterations,
                current_utility=round_utility.overall_with_penalty,
                remaining_conflicts=round_detection.total_count,
                fixes_this_round=fixes_count,
            )

            # 检查是否已满足尽早终止条件
            should_terminate = self._check_early_termination(
                iteration=iteration,
                no_errors=no_errors,
                any_fixed=any_fixed,
                round_utility=round_utility,
            )

            if no_errors and should_terminate:
                logger.info(f"[协商] ✓ 第{iteration + 1}轮满足终止条件")
                negotiation_log.append({
                    "iteration": iteration + 1,
                    "action": "协商完成（效用达标）",
                    "remaining_conflicts": round_detection.total_count,
                    "all_resolved": True,
                    "utility": round_utility.overall_with_penalty,
                })
                await event_publisher.publish_accept(
                    session_id=session_id,
                    final_conflicts=round_detection.total_count,
                )
                await event_publisher.publish_finalized(
                    session_id=session_id,
                    iteration_count=iteration + 1,
                    fully_resolved=True,
                    final_conflicts=0,
                )
                return self._build_result(
                    current_plans, negotiation_log, iteration + 1, True,
                    structured_requirement, session_id,
                )

            # 处理无修复的情况
            if not any_fixed:
                should_terminate = await self._handle_no_fix_situation(
                    current_plans=current_plans,
                    structured_requirement=structured_requirement,
                    iteration=iteration,
                    session_id=session_id,
                    negotiation_log=negotiation_log,
                )
                if should_terminate:
                    final_result = self._build_result(
                        current_plans, negotiation_log, iteration + 1, False,
                        structured_requirement, session_id,
                    )
                    return final_result
            else:
                # 有修复，重置连续无修复计数
                self.no_fix_streak = 0

            # 记录本轮剩余冲突数
            remaining = detect_conflicts(current_plans, structured_requirement)
            logger.info(f"[协商] 第{iteration + 1}轮后剩余 {remaining.total_count} 个冲突")

        # === 达到最大迭代次数后的最终处理 ===
        return self._build_result(
            current_plans, negotiation_log, max_iterations, False,
            structured_requirement, session_id,
        )

    def _check_early_termination(
        self,
        iteration: int,
        no_errors: bool,
        any_fixed: bool,
        round_utility: UtilityResult,
    ) -> bool:
        """
        【第三阶段】检查是否应提前终止

        基于效用值的提前终止条件：
        1. 无 error 冲突且效用值达到阈值（>0.85）
        2. 无 error 冲突且连续 N 轮效用无改善
        3. 无 error 冲突且已到最大迭代次数

        Args:
            iteration: 当前轮次（0-based）
            no_errors: 当前是否无 error 冲突
            any_fixed: 本轮是否有任何修复
            round_utility: 本轮效用评估结果

        Returns:
            True: 应终止; False: 继续
        """
        current_utility = round_utility.overall_with_penalty

        # 条件1：无 error 且效用达标
        if no_errors and current_utility >= self.utility_terminate_threshold:
            logger.info(
                f"[终止检查] 效用达标: {current_utility:.4f} >= "
                f"{self.utility_terminate_threshold}"
            )
            return True

        if not no_errors:
            return False

        # 条件2：检查效用是否在改善
        if len(self.utility_history) >= 2:
            prev_utility = self.utility_history[-2]
            utility_improvement = current_utility - prev_utility

            if utility_improvement < self.utility_improvement_min_delta:
                self.utility_stagnation_count += 1
                logger.info(
                    f"[终止检查] 效用改善不足: {utility_improvement:.4f} < "
                    f"{self.utility_improvement_min_delta}, "
                    f"停滞计数={self.utility_stagnation_count}/{self.utility_stagnation_tolerance}"
                )
            else:
                # 有改善，重置停滞计数
                self.utility_stagnation_count = 0

            if self.utility_stagnation_count >= self.utility_stagnation_tolerance:
                logger.info(
                    f"[终止检查] 效用连续{self.utility_stagnation_count}轮停滞"
                )
                return True

        return False

    # ==============================================================
    # 单轮协商
    # ==============================================================

    async def _call_negotiation_round(
        self,
        current_plans: List[dict],
        structured_requirement: dict,
        backup_attractions: List[dict],
        session_id: str,
        iteration: int,
        negotiation_log: List[dict],
    ) -> dict:
        """
        执行一轮协商

        返回:
            {
                "day_plans": 更新后的行程,
                "no_errors": 是否无 error 冲突,
                "any_fixed": 是否有任何修复,
                "total_conflicts": 总冲突数,
            }
        """
        from .conflict_detector import detect_conflicts

        # 检测当前冲突
        detection = detect_conflicts(current_plans, structured_requirement)
        has_error = detection.has_error

        if not has_error:
            return {
                "day_plans": current_plans,
                "no_errors": True,
                "any_fixed": False,
                "total_conflicts": detection.total_count,
            }

        # 按天分组处理冲突
        day_conflicts = detection.group_by_day()
        any_fixed = False

        for day_num, conflicts in day_conflicts.items():
            day_idx = day_num - 1
            if day_idx < 0 or day_idx >= len(current_plans):
                continue

            day_result = await self._resolve_day_conflicts(
                current_plans=current_plans,
                day_idx=day_idx,
                day_num=day_num,
                conflicts=conflicts,
                structured_requirement=structured_requirement,
                backup_attractions=backup_attractions,
                session_id=session_id,
                iteration=iteration,
                negotiation_log=negotiation_log,
            )

            current_plans = day_result["day_plans"]
            if day_result["any_fixed"]:
                any_fixed = True

        # 重新检测最终状态
        final_detection = detect_conflicts(current_plans, structured_requirement)

        return {
            "day_plans": current_plans,
            "no_errors": not final_detection.has_error,
            "any_fixed": any_fixed,
            "total_conflicts": final_detection.total_count,
        }

    # ==============================================================
    # 单天冲突解决
    # ==============================================================

    async def _resolve_day_conflicts(
        self,
        current_plans: List[dict],
        day_idx: int,
        day_num: int,
        conflicts: List[dict],
        structured_requirement: dict,
        backup_attractions: List[dict],
        session_id: str,
        iteration: int,
        negotiation_log: List[dict],
    ) -> dict:
        """
        解决某一天的所有冲突

        返回:
            {
                "day_plans": 更新后的行程,
                "any_fixed": 是否有修复,
            }
        """
        from .event_publisher import event_publisher
        from .strategy_executor import strategy_executor
        from .repair_validator import repair_validator

        plans = copy.deepcopy(current_plans)
        any_fixed = False

        # 本轮活跃冲突列表
        active_conflicts = list(conflicts)

        while active_conflicts:
            conflict = active_conflicts.pop(0)
            if not isinstance(conflict, dict):
                continue

            conflict_type = conflict.get("type", "")
            conflict_activities = conflict.get("activities", [])

            # === 发布 PROPOSE 事件 ===
            await event_publisher.publish_propose(
                session_id=session_id,
                day_num=day_num,
                iteration=iteration,
                conflict_type=conflict_type,
                conflict_description=conflict.get("description", ""),
            )

            # === Agent 征询环节（执行策略前） ===
            try:
                # 使用增强版事前咨询（consult_agents_on_conflict）
                # 对应重构清单 4.2.2：Agent 从"事后否决"变为"事前建议"
                consultation = await repair_validator.consult_agents_on_conflict(
                    session_id=session_id,
                    conflict=conflict,
                    day_plan=plans[day_idx],
                    day_idx=day_idx,
                )

                suggested = consultation.get("suggested_strategies", [])
                vetoed = consultation.get("veto_strategies", [])

                if suggested or vetoed:
                    negotiation_log.append({
                        "iteration": iteration + 1,
                        "day": day_num,
                        "action": "Agent征询",
                        "target": conflict_activities,
                        "type": conflict_type,
                        "suggested_strategies": suggested,
                        "veto_strategies": vetoed,
                    })

                # 如果有 Agent 建议的策略，优先尝试
                if suggested:
                    agent_preferred_strategies = [s["name"] for s in suggested]
                    logger.info(
                        f"[协商] Agent建议的策略: {agent_preferred_strategies}"
                    )
            except Exception as e:
                logger.warning(f"[协商] Agent征询环节异常（非致命）: {e}")

            # === 【改造方案 4.2.5】冲突招标（在策略链执行前） ===
            try:
                bids = await self._call_for_bids(
                    conflict=conflict,
                    day_plans=plans,
                    structured_requirement=structured_requirement,
                    session_id=session_id,
                )
                if bids:
                    # 发布招标事件
                    await event_publisher.publish_bid(
                        session_id=session_id,
                        conflict_type=conflict_type,
                        bids=bids,
                        day_num=day_num,
                    )

                    best_bid = await self._evaluate_bids(
                        bids=bids,
                        conflict=conflict,
                        day_plans=plans,
                        day_idx=day_idx,
                        structured_requirement=structured_requirement,
                    )
                    if best_bid:
                        logger.info(
                            f"[协商] 冲突招标中标: agent={best_bid.get('agent_id')}, "
                            f"strategy={best_bid.get('strategy')}, "
                            f"utility={best_bid.get('utility', 0):.4f}"
                        )

                        # 发布招标结果事件
                        await event_publisher.publish_bid_result(
                            session_id=session_id,
                            winner_agent=best_bid.get("agent_id", "unknown"),
                            winning_strategy=best_bid.get("strategy", "unknown"),
                            day_num=day_num,
                        )

                        negotiation_log.append({
                            "iteration": iteration + 1,
                            "day": day_num,
                            "action": "冲突招标",
                            "target": conflict_activities,
                            "type": conflict_type,
                            "bids": [
                                {"agent_id": b["agent_id"], "strategy": b["strategy"],
                                 "expected_utility": b.get("expected_utility", 0)}
                                for b in bids
                            ],
                            "winner": best_bid.get("agent_id"),
                            "winning_strategy": best_bid.get("strategy"),
                        })
                        # 如果中标 Agent 提供了 plan_after，直接使用
                        if best_bid.get("plan_after"):
                            plans = best_bid["plan_after"]
                            any_fixed = True
                            active_conflicts.clear()
                            continue
            except Exception as e:
                logger.warning(f"[协商] 冲突招标环节异常（非致命）: {e}")

            # === 策略链执行（第三阶段：效用驱动选择） ===
            plan_before_snapshot = copy.deepcopy(plans[day_idx])
            plans_before_snapshot_multi = copy.deepcopy(plans)

            result, is_multi_day, strategy_name = strategy_executor.try_strategies_chain(
                day_plans=plans,
                day_idx=day_idx,
                conflict=conflict,
                conflict_type=conflict_type,
                backup_attractions=backup_attractions,
                structured_requirement=structured_requirement,
            )

            if result is not None:
                # 应用策略结果
                proposed_plans = strategy_executor.apply_strategy_result(
                    day_plans=plans,
                    day_idx=day_idx,
                    result=result,
                    is_multi_day=is_multi_day,
                    strategy_name=strategy_name,
                )

                # === 验证修复结果 ===
                is_valid, day_errors = repair_validator.verify_repair(
                    proposed_plans=proposed_plans,
                    structured_requirement=structured_requirement,
                    day_num=day_num,
                )

                if not is_valid:
                    logger.info(
                        f"[协商] 策略 {strategy_name} 修复后当天仍有 "
                        f"{len(day_errors)} 个error冲突，回滚"
                    )
                    strategy_executor.record_result(strategy_name, False)
                    continue

                                # === Agent 投票确认 ===
                consensus = await repair_validator.collect_agent_consensus(
                    proposed_plans=proposed_plans,
                    original_plans=plans,
                    conflict=conflict,
                    strategy_name=strategy_name,
                    session_id=session_id,
                    structured_requirement=structured_requirement,
                )

                if not consensus["approved"]:
                    logger.info(f"[协商] 策略 {strategy_name} 被Agent否决，尝试下一策略")
                    strategy_executor.record_result(strategy_name, False)

                    # 收集否决理由供后续 LLM 协商使用
                    veto_reasons = consensus.get("veto_reasons", [])
                    if veto_reasons:
                        negotiation_log.append({
                            "iteration": iteration + 1,
                            "day": day_num,
                            "action": "Agent否决详情",
                            "strategy": strategy_name,
                            "veto_reasons": veto_reasons,
                        })

                    # 如果有反提案，记录到日志
                    counter_proposals = consensus.get("counter_proposals", [])
                    if counter_proposals:
                        negotiation_log.append({
                            "iteration": iteration + 1,
                            "day": day_num,
                            "action": "Agent反提案建议",
                            "strategy": strategy_name,
                            "counter_proposals": counter_proposals,
                        })

                    continue

                # === 采纳方案 ===
                plans = proposed_plans
                strategy_executor.record_result(strategy_name, True)

                # 生成调整详情
                if is_multi_day:
                    adjustments = []
                    for d_idx in range(len(plans)):
                        old_plan = plans_before_snapshot_multi[d_idx] if d_idx < len(plans_before_snapshot_multi) else {}
                        new_plan = proposed_plans[d_idx] if d_idx < len(proposed_plans) else {}
                        adj = repair_validator.build_adjustment_details(old_plan, new_plan, strategy_name)
                        adjustments.extend(adj)
                else:
                    adjustments = repair_validator.build_adjustment_details(
                        plan_before_snapshot, 
                        plans[day_idx] if isinstance(plans[day_idx], dict) and plans[day_idx].get("attractions") is not None else plan_before_snapshot,
                        strategy_name,
                    )

                # 记录日志
                action_name = strategy_name.replace("strategy_", "").replace("_", "·")
                negotiation_log.append({
                    "iteration": iteration + 1,
                    "day": day_num,
                    "action": f"动态策略-{action_name}",
                    "target": conflict_activities,
                    "type": conflict_type,
                    "adjustments": adjustments,
                })

                # 发布事件
                target_agent = "all_vehicles" if is_multi_day else f"day_{day_num}"
                await event_publisher.publish_counter(
                    session_id=session_id,
                    strategy_name=f"动态策略-{action_name}",
                    conflict_activities=conflict_activities,
                    adjustments=adjustments,
                    target_agent=target_agent,
                    day_num=day_num,
                )

                any_fixed = True

                # === 防震荡：本轮不再处理新冲突 ===
                from .conflict_detector import detect_conflicts
                fresh = detect_conflicts(plans, structured_requirement)
                logger.info(
                    f"[协商] 修复后重新检测: 剩余 {fresh.error_count} 个error冲突"
                    f"（留待下一轮处理）"
                )
                active_conflicts.clear()

            else:
                # 所有确定性策略失败 → LLM仲裁
                llm_success = await self._try_llm_arbitration(
                    plans=plans,
                    day_idx=day_idx,
                    day_num=day_num,
                    conflict=conflict,
                    conflict_type=conflict_type,
                    structured_requirement=structured_requirement,
                    session_id=session_id,
                    iteration=iteration,
                    negotiation_log=negotiation_log,
                )

                if llm_success:
                    any_fixed = True
                    active_conflicts.clear()
                else:
                    # === 【P2】LLM仲裁失败 → 触发反提案机制 ===
                    try:
                        cp_result = await repair_validator.try_counter_proposal(
                            session_id=session_id,
                            conflict=conflict,
                            day_plans=plans,
                            structured_requirement=structured_requirement,
                            negotiation_log=negotiation_log,
                        )
                        if cp_result and cp_result.get("adjustments"):
                            # 应用反提案结果
                            cp_plans = cp_result.get("modified_plans")
                            if cp_plans:
                                plans = cp_plans
                            any_fixed = True
                            active_conflicts.clear()

                            negotiation_log.append({
                                "iteration": iteration + 1,
                                "day": day_num,
                                "action": f"反提案-{cp_result.get('proposal_author', 'unknown')}",
                                "target": conflict_activities,
                                "type": conflict_type,
                                "adjustments": cp_result.get("adjustments", []),
                            })
                            logger.info(
                                f"[协商] 反提案成功: author={cp_result.get('proposal_author', 'unknown')}"
                            )
                    except Exception as e:
                        logger.warning(f"[协商] 反提案环节异常（非致命）: {e}")

            # === 【P2增强】反提案失败 → LLM多Agent协商 ===
                    if not any_fixed:
                        llm_nego_success = await self._try_llm_negotiation(
                            plans=plans,
                            day_num=day_num,
                            conflict=conflict,
                            conflict_type=conflict_type,
                            structured_requirement=structured_requirement,
                            session_id=session_id,
                            iteration=iteration,
                            negotiation_log=negotiation_log,
                        )
                        if llm_nego_success:
                            any_fixed = True
                            active_conflicts.clear()

                        else:
                            # === 【T6增强】LLM协商失败 → Contract Net 兜底 ===
                            contract_success = await self._try_contract_net(
                                plans=plans,
                                day_idx=day_idx,
                                day_num=day_num,
                                conflict=conflict,
                                conflict_type=conflict_type,
                                structured_requirement=structured_requirement,
                                session_id=session_id,
                                iteration=iteration,
                                negotiation_log=negotiation_log,
                            )
                            if contract_success:
                                any_fixed = True
                                active_conflicts.clear()

            # 如果所有方法都失败，清空 active_conflicts 防止死循环
            if not any_fixed:
                active_conflicts.clear()

        return {
            "day_plans": plans,
            "any_fixed": any_fixed,
        }

    # ==============================================================
    # 【改造方案 4.2】冲突招标
    # ==============================================================

    async def _call_for_bids(
        self,
        conflict: Dict[str, Any],
        day_plans: List[dict],
        structured_requirement: dict,
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """
        【改造方案 4.2.5】向各 Agent 发布冲突招标

        将冲突作为"标的"招标，各 Agent 根据其领域知识竞标，
        返回各自的解决建议和预期效用。

        Args:
            conflict: 冲突信息
            day_plans: 当前行程
            structured_requirement: 结构化需求
            session_id: 会话ID

        Returns:
            投标列表，每个元素:
            {
                "agent_id": str,
                "strategy": str,
                "params": dict,
                "expected_utility": float,
                "plan_after": List[dict] (模拟应用后的行程),
            }
        """
        from src.services.negotiation_event_bus import agent_message_bus, AgentMessageType

        conflict_type = conflict.get("type", "")
        day_num = conflict.get("day", 1)

        # 向所有 Agent 发送招标请求
        payload = {
            "action": "conflict_bid",
            "conflict": conflict,
            "session_id": session_id,
            "day_num": day_num,
        }

        responses = await agent_message_bus.broadcast(
            from_agent="dispatcher",
            message={
                "type": AgentMessageType.COORDINATE_REQUEST,
                "payload": payload,
            },
            session_id=session_id,
        )

        bids = []
        for agent_id, response in responses.items():
            if not isinstance(response, dict):
                continue
            strategy = response.get("strategy") or response.get("suggested_strategy")
            if not strategy:
                continue
            bids.append({
                "agent_id": agent_id,
                "strategy": strategy,
                "params": response.get("params", {}),
                "expected_utility": response.get("expected_utility", 0.5),
                "plan_after": response.get("plan_after"),
            })

        return bids

    async def _evaluate_bids(
        self,
        bids: List[Dict[str, Any]],
        conflict: Dict[str, Any],
        day_plans: List[dict],
        day_idx: int,
        structured_requirement: dict,
    ) -> Optional[Dict[str, Any]]:
        """
        【改造方案 4.2.5】评标 — 选择最优投标

        Args:
            bids: 投标列表
            conflict: 冲突信息
            day_plans: 当前行程
            day_idx: 当前 day 索引
            structured_requirement: 结构化需求

        Returns:
            选中标的信息，None 表示无有效标
        """
        from src.services.negotiation_utility import utility_evaluator

        if not bids:
            return None

        best_bid = None
        best_utility = -1.0

        for bid in bids:
            try:
                # 如果有 plan_after，直接评估其效用
                plan_after = bid.get("plan_after")
                if plan_after and isinstance(plan_after, list):
                    from .conflict_detector import detect_conflicts
                    detection = detect_conflicts(plan_after, structured_requirement)
                    utility = utility_evaluator.evaluate(
                        plan_after, structured_requirement,
                        conflicts=detection.conflicts,
                    )
                    bid_utility = utility.overall_with_penalty
                else:
                    bid_utility = float(bid.get("expected_utility", 0.3))

                if bid_utility > best_utility:
                    best_utility = bid_utility
                    best_bid = {**bid, "utility": bid_utility}

            except Exception as e:
                logger.debug(f"[评标] 评估失败: {e}")
                continue

        return best_bid

    # ==============================================================
    # LLM 仲裁
    # ==============================================================

    async def _try_llm_arbitration(
        self,
        plans: List[dict],
        day_idx: int,
        day_num: int,
        conflict: dict,
        conflict_type: str,
        structured_requirement: dict,
        session_id: str,
        iteration: int,
        negotiation_log: List[dict],
    ) -> bool:
        """
        尝试 LLM 仲裁解决冲突

        Returns:
            True: LLM 仲裁成功
        """
        from src.services.negotiation_llm_arbiter import llm_arbiter
        from .event_publisher import event_publisher

        logger.info(
            f"[协商] 第{iteration + 1}轮, day{day_num}: "
            f"所有确定性策略失败，尝试LLM仲裁者..."
        )

        try:
            llm_result = await llm_arbiter.arbitrate(
                day_plans=plans,
                structured_requirement=structured_requirement,
                conflicts=[conflict],
                negotiation_log=negotiation_log,
                session_id=session_id,
            )

            if llm_result and llm_result.get("day_plans"):
                plans[:] = llm_result["day_plans"]
                adjustments = llm_result.get("adjustments", [])
                analysis = llm_result.get("analysis", "")
                solution_type = llm_result.get("solution_type", "")

                negotiation_log.append({
                    "iteration": iteration + 1,
                    "day": day_num,
                    "action": f"LLM仲裁({solution_type})",
                    "target": conflict.get("activities", []),
                    "type": conflict_type,
                    "adjustments": adjustments,
                    "analysis": analysis,
                })

                await event_publisher.publish_llm_arbitration(
                    session_id=session_id,
                    analysis=analysis,
                    adjustments=adjustments,
                    solution_type=solution_type,
                )

                logger.info(
                    f"[协商] ✅ LLM仲裁成功: {analysis}, "
                    f"生成{len(adjustments)}项调整"
                )

                # 防震荡
                from .conflict_detector import detect_conflicts
                fresh = detect_conflicts(plans, structured_requirement)
                logger.info(
                    f"[协商] LLM仲裁后重新检测: 剩余 {fresh.error_count} 个error冲突"
                    f"（留待下一轮处理）"
                )
                return True

            logger.info(f"[协商] ⚠️ LLM仲裁未返回有效方案")
            return False

        except Exception as e:
            logger.warning(f"[协商] LLM仲裁异常: {e}")
            return False

    # ==============================================================
    # 【P2增强】LLM多Agent协商
    # ==============================================================

    async def _try_llm_negotiation(
        self,
        plans: List[dict],
        day_num: int,
        conflict: dict,
        conflict_type: str,
        structured_requirement: dict,
        session_id: str,
        iteration: int,
        negotiation_log: List[dict],
    ) -> bool:
        """
        【P2增强】LLM驱动多Agent协商回合

        当确定性策略 + LLM仲裁 + 反提案全部失败后，
        将各Agent的否决理由传递给LLM，让LLM充当主持人
        生成兼顾各方利益的折中方案。

        Returns:
            True: 协商成功
        """
        from src.services.negotiation_llm_arbiter import llm_arbiter
        from .event_publisher import event_publisher
        from .repair_validator import repair_validator

        logger.info(
            f"[协商] 第{iteration + 1}轮, day{day_num}: "
            f"反提案失败，尝试LLM多Agent协商..."
        )

        # 从协商日志中提取Agent投票历史（否决理由）
        agent_vote_history = []
        for log_entry in negotiation_log:
            if log_entry.get("action") in ("Agent否决详情",):
                veto_reasons = log_entry.get("veto_reasons", [])
                for vr in veto_reasons:
                    if isinstance(vr, dict):
                        agent_vote_history.append({
                            "agent_id": vr.get("agent_id", "unknown"),
                            "strategy_name": vr.get("strategy", ""),
                            "vote": "veto",
                            "reason": vr.get("reason", ""),
                        })

        try:
            llm_nego_result = await llm_arbiter.negotiate_with_llm(
                day_plans=plans,
                structured_requirement=structured_requirement,
                conflicts=[conflict],
                session_id=session_id,
                negotiation_log=negotiation_log,
                agent_vote_history=agent_vote_history,
            )

            if llm_nego_result and llm_nego_result.get("adjustments"):
                # 应用协商结果
                modified_plans = llm_nego_result.get("day_plans")
                if modified_plans:
                    plans.clear()
                    plans.extend(modified_plans)

                adjustments = llm_nego_result.get("adjustments", [])
                analysis = llm_nego_result.get("analysis", "")
                solution_type = llm_nego_result.get("solution_type", "")
                agent_satisfaction = llm_nego_result.get("agent_satisfaction", {})

                negotiation_log.append({
                    "iteration": iteration + 1,
                    "day": day_num,
                    "action": f"LLM多Agent协商({solution_type})",
                    "target": conflict.get("activities", []),
                    "type": conflict_type,
                    "adjustments": adjustments,
                    "analysis": analysis,
                    "agent_satisfaction": agent_satisfaction,
                })

                await event_publisher.publish_llm_arbitration(
                    session_id=session_id,
                    analysis=analysis,
                    adjustments=adjustments,
                    solution_type=solution_type,
                )

                logger.info(
                    f"[协商] ✅ LLM多Agent协商成功: {analysis}, "
                    f"生成{len(adjustments)}项调整"
                )

                # 防震荡
                from .conflict_detector import detect_conflicts
                fresh = detect_conflicts(plans, structured_requirement)
                logger.info(
                    f"[协商] LLM多Agent协商后重新检测: "
                    f"剩余 {fresh.error_count} 个error冲突"
                )
                return True

            logger.info(f"[协商] ⚠️ LLM多Agent协商未返回有效方案")
            return False

        except Exception as e:
            logger.warning(f"[协商] LLM多Agent协商异常: {e}")
            return False

    # ==============================================================
    # 【T6增强】Contract Net 兜底
    # ==============================================================

    async def _try_contract_net(
        self,
        plans: List[dict],
        day_idx: int,
        day_num: int,
        conflict: dict,
        conflict_type: str,
        structured_requirement: dict,
        session_id: str,
        iteration: int,
        negotiation_log: List[dict],
    ) -> bool:
        """
        【T6增强】尝试 Contract Net Protocol 兜底解决冲突

        当确定性策略 + LLM仲裁 + 反提案 + LLM多Agent协商全部失败后，
        使用规则化的合同网协议进行招标→投标→评标→授标。

        Returns:
            True: Contract Net 成功
        """
        from src.services.negotiation_llm_arbiter import contract_net_protocol
        from .event_publisher import event_publisher
        from .conflict_detector import detect_conflicts

        logger.info(
            f"[协商] 第{iteration + 1}轮, day{day_num}: "
            f"LLM协商失败，尝试Contract Net兜底..."
        )

        try:
            contract_result = await contract_net_protocol.run_round(
                day_plans=plans,
                structured_requirement=structured_requirement,
                conflicts=[conflict],
                session_id=session_id,
            )

            if contract_result and contract_result.get("adjustments"):
                # 应用 Contract Net 结果
                modified_plans = contract_result.get("day_plans")
                if modified_plans:
                    plans.clear()
                    plans.extend(modified_plans)

                adjustments = contract_result.get("adjustments", [])
                winning_agent = contract_result.get("winning_agent", "unknown")

                negotiation_log.append({
                    "iteration": iteration + 1,
                    "day": day_num,
                    "action": f"Contract Net(中标:{winning_agent})",
                    "target": conflict.get("activities", []),
                    "type": conflict_type,
                    "adjustments": adjustments,
                })

                await event_publisher.publish_counter(
                    session_id=session_id,
                    strategy_name=f"Contract Net-{winning_agent}",
                    conflict_activities=conflict.get("activities", []),
                    adjustments=adjustments,
                    target_agent=str(winning_agent),
                    day_num=day_num,
                )

                logger.info(
                    f"[协商] ✅ Contract Net兜底成功: 中标Agent={winning_agent}, "
                    f"生成{len(adjustments)}项调整"
                )

                # 防震荡
                fresh = detect_conflicts(plans, structured_requirement)
                logger.info(
                    f"[协商] Contract Net后重新检测: "
                    f"剩余 {fresh.error_count} 个error冲突"
                )
                return True

            logger.info(f"[协商] ⚠️ Contract Net 未返回有效方案")
            return False

        except Exception as e:
            logger.warning(f"[协商] Contract Net异常: {e}")
            return False

    # ==============================================================
    # 初始路线优化
    # ==============================================================

    async def _do_initial_route_optimization(
        self,
        current_plans: List[dict],
        use_real_traffic: bool,
        session_id: str,
        structured_requirement: Optional[dict] = None,
    ) -> List[dict]:
        """
        协商开始前执行一次路线优化（防震荡：只做一次，不在每轮做）

        【第三阶段改进】以综合效用作为优化目标：
        原版仅按纬度排序（交通时间最短的单目标），
        新版评估多个候选顺序，选择综合效用最高的方案。

        Args:
            current_plans: 当前行程
            use_real_traffic: 是否使用真实交通数据
            session_id: 会话ID
            structured_requirement: 结构化需求（用于效用评估）

        Returns:
            优化后的行程计划
        """
        from .event_publisher import event_publisher
        from src.services.negotiation_utility import utility_evaluator
        from .conflict_detector import detect_conflicts

        plans = copy.deepcopy(current_plans)
        logger.info("[协商] 开始前执行一次路线优化（效用驱动）...")

        for d_idx in range(len(plans)):
            day_plan = plans[d_idx]

            if use_real_traffic:
                from src.services.negotiation_service import optimize_real_route
                plans[d_idx] = await optimize_real_route(day_plan, mode="transit")
            else:
                # === 效用驱动的路线排序优化 ===
                optimized = _sort_by_utility(
                    day_plan, structured_requirement=structured_requirement,
                )
                if optimized is not None:
                    plans[d_idx] = optimized

        # 收集 long_distance_warnings
        all_long_distance_warnings = []
        for d_idx, plan in enumerate(plans):
            warnings = plan.pop("_long_distance_warnings", None)
            if warnings:
                for w in warnings:
                    w["day"] = d_idx + 1
                all_long_distance_warnings.extend(warnings)

        if all_long_distance_warnings:
            await event_publisher.publish_route_optimization(
                session_id=session_id,
                long_distance_warnings=all_long_distance_warnings,
            )

        logger.info("[协商] 路线优化完成")
        return plans
    
    # ==============================================================
    # 无修复情况处理
    # ==============================================================

    async def _handle_no_fix_situation(
        self,
        current_plans: List[dict],
        structured_requirement: dict,
        iteration: int,
        session_id: str,
        negotiation_log: List[dict],
    ) -> bool:
        """
        处理本轮无修复的情况

        当连续 N 轮无修复时:
        - 第1轮无修复: 触发全局重排
        - 第2轮无修复: 提前终止

        Returns:
            True: 应提前终止; False: 继续迭代
        """
        from .event_publisher import event_publisher
        from .conflict_detector import detect_conflicts

        self.no_fix_streak += 1

        detection = detect_conflicts(current_plans, structured_requirement)
        has_remaining_errors = detection.has_error

        if has_remaining_errors and self.no_fix_streak == 1:
            # 第1轮无修复 → 全局重排
            logger.info(f"[协商] 第{iteration + 1}轮无修复，触发局部搜索重排尝试...")
            self._do_global_reshuffle(current_plans, structured_requirement)
            negotiation_log.append({
                "iteration": iteration + 1,
                "action": "局部搜索重排（无有效局部修复策略）",
            })
            await event_publisher.publish_global_reshuffle(session_id=session_id)
            return False  # 不终止，继续迭代

        elif has_remaining_errors and self.no_fix_streak >= 2:
            # 连续两轮无修复 → 提前终止
            logger.warning(
                f"[协商] 第{iteration + 1}轮无任何修复"
                f"（连续{self.no_fix_streak}轮），提前终止"
            )
            negotiation_log.append({
                "iteration": iteration + 1,
                "action": f"提前终止（连续{self.no_fix_streak}轮无有效修复策略）",
            })
            await event_publisher.publish_reject(
                session_id=session_id,
                reason=f"连续{self.no_fix_streak}轮无有效修复策略",
            )
            return True  # 终止

        else:
            # 无 error 冲突，继续
            logger.info(f"[协商] 第{iteration + 1}轮无修复，但已无error冲突，继续迭代")
            return False

    def _do_global_reshuffle(
        self,
        day_plans: List[dict],
        structured_requirement: dict,
    ) -> None:
        """全局重排 - 委托给模块级函数"""
        local_search_reshuffle(day_plans, structured_requirement)

    # ==============================================================
    # 最终结果构建
    # ==============================================================

    def _build_result(
        self,
        current_plans: List[dict],
        negotiation_log: List[dict],
        iteration_count: int,
        fully_resolved: bool,
        structured_requirement: dict,
        session_id: str,
    ) -> dict:
        """
        构建最终结果

        【第三阶段】在返回结果中增加 utility_history
        """
        from .conflict_detector import detect_conflicts
        from src.services.negotiation_utility import compute_utility_dict
        from src.services.negotiation_event_bus import event_bus, agent_message_bus, AgentMessageType
        from .event_publisher import event_publisher

        # 最终校验
        final_detection = detect_conflicts(current_plans, structured_requirement)
        final_error = final_detection.has_error

        # 收集 long_distance_warnings
        transport_time_threshold = structured_requirement.get("transport_time_threshold_min", 90)
        final_long_distance_warnings = self._collect_long_distance_warnings(
            current_plans, transport_time_threshold
        )

                # 发布最终事件（安全创建异步任务）
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(event_publisher.publish_finalized(
                    session_id=session_id,
                    iteration_count=iteration_count,
                    fully_resolved=not final_error,
                    final_conflicts=final_detection.total_count,
                    long_distance_warnings=final_long_distance_warnings,
                    utility=compute_utility_dict(current_plans, structured_requirement),
                ))
        except RuntimeError:
            # 没有事件循环时（如同步测试），静默跳过
            pass

        # 通知所有 Agent（安全创建异步任务）
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                                asyncio.ensure_future(agent_message_bus.broadcast(
                    from_agent="dispatcher",
                    message={
                        "type": AgentMessageType.SCHEDULE_PROPOSAL,
                        "payload": {
                            "action": "negotiation_complete",
                            "session_id": session_id,
                            "fully_resolved": not final_error,
                            "total_conflicts": final_detection.total_count,
                            "final_plans_count": len(current_plans),
                        }
                    },
                    session_id=session_id,
                ))
        except RuntimeError:
            # 没有事件循环时（如同步测试），静默跳过
            pass
        negotiation_log.append({
            "iteration": iteration_count,
            "action": "广播协商完成",
            "fully_resolved": not final_error,
        })

         # === 【第三阶段】Pareto 分析 ===
        from .pareto_optimizer import pareto_optimizer
        from src.services.negotiation_utility import utility_evaluator

        pareto_analysis = None
        try:
            transport, penalty, utility = pareto_optimizer.compute_objectives(
                current_plans, structured_requirement,
                conflicts=final_detection.conflicts if hasattr(final_detection, 'conflicts') else None,
            )
            pareto_analysis = {
                "total_transport_time_min": round(transport, 1),
                "conflict_penalty": round(penalty, 4),
                "utility_score": round(utility, 4),
            }
            # 检查是否 Pareto 改进（相对于初始方案）
            if hasattr(self, '_initial_day_plans') and self._initial_day_plans:
                is_improvement = pareto_optimizer.is_pareto_improvement(
                    self._initial_day_plans, current_plans, structured_requirement,
                )
                pareto_analysis["is_pareto_improvement"] = is_improvement

            logger.info(
                f"[协商完成] Pareto分析: 交通={transport:.0f}min, "
                f"惩罚={penalty:.4f}, 效用={utility:.4f}"
            )
        except Exception as e:
            logger.warning(f"[协商完成] Pareto分析失败: {e}")

        # === 【第四阶段】生成人类可读的调整摘要 ===
        adjustments_summary = self._build_adjustments_summary(negotiation_log)

        # === 【第四阶段】生成景点冲突标记 ===
        activity_conflicts = self._build_activity_conflicts(
            current_plans, final_detection,
        )

        return {
            "day_plans": current_plans,
            "negotiation_log": negotiation_log,
            "iteration_count": iteration_count,
            "fully_resolved": not final_error,
            "validation": final_detection.to_dict(),
            "negotiation_events": event_bus.get_session_log(session_id),
            "utility_history": list(self.utility_history),  # 【第三阶段】效用历史
            "pareto_analysis": pareto_analysis,  # 【第三阶段】Pareto分析
            # ========== 【第四阶段】新增字段 ==========
            "status": "pending_confirmation",  # 协商完成但待用户确认
            "adjustments_summary": adjustments_summary,
            "user_options": ["accept", "adjust", "reject"],
            "activity_conflicts": activity_conflicts,  # 按景点聚合的冲突标记
        }

    # ==============================================================
    # 【第四阶段】辅助方法
    # ==============================================================

    def _build_adjustments_summary(
        self,
        negotiation_log: List[dict],
    ) -> List[str]:
        """
        从协商日志中提取人类可读的调整摘要列表

        遍历所有日志条目，收集每个条目中的 adjustments 的 human_readable 字段，
        去重后返回纯文本列表，供前端直接展示。

        Args:
            negotiation_log: 协商日志列表

        Returns:
            人类可读的调整摘要列表
            e.g. ["故宫游览时间从09:00调整为08:30", "午餐从全聚德(王府井)替换为全聚德(前门店)"]
        """
        from .explanation_templates import build_human_readable_from_adjustment

        summaries = []
        seen = set()

        for log_entry in negotiation_log:
            adjustments = log_entry.get("adjustments", [])
            if not isinstance(adjustments, list):
                continue

            for adj in adjustments:
                if not isinstance(adj, dict):
                    continue

                # 优先使用已有的 human_readable 字段
                hr = adj.get("human_readable", "").strip()
                if not hr:
                    # 兼容旧格式：使用模板生成
                    hr = build_human_readable_from_adjustment(adj)

                if hr and hr not in seen:
                    seen.add(hr)
                    summaries.append(hr)

        return summaries

    def _build_activity_conflicts(
        self,
        day_plans: List[dict],
        detection_result: Any,
    ) -> Dict[str, list]:
        """
        将冲突按"天 → 景点"聚合，输出每个景点的冲突标记列表

        输出格式:
        {
            "day_1": [
                {
                    "activity_name": "故宫",
                    "conflicts": [
                        {"type": "time_conflict", "severity": "warning", "description": "..."},
                    ]
                },
                ...
            ],
            "day_2": [...]
        }

        Args:
            day_plans: 行程计划
            detection_result: ConflictDetectionResult 实例

        Returns:
            按景点聚合的冲突字典
        """
        conflicts = getattr(detection_result, "conflicts", []) if detection_result is not None else []
        # 类型: day_key -> { activity_name -> { activity_name, conflicts: [...] } }
        activity_map: Dict[str, Dict[str, Dict[str, Any]]] = {}

        for conflict in conflicts:
            if not isinstance(conflict, dict):
                continue
            day = conflict.get("day", 1)
            activities = conflict.get("activities", [])

            if not activities or not isinstance(activities, list):
                continue

            day_key = f"day_{day}"
            if day_key not in activity_map:
                activity_map[day_key] = {}

            for activity_name in activities:
                if not isinstance(activity_name, str):
                    continue
                if activity_name not in activity_map[day_key]:
                    activity_map[day_key][activity_name] = {
                        "activity_name": activity_name,
                        "conflicts": [],
                    }

                # 类型安全地添加冲突
                activity_entry = activity_map[day_key][activity_name]
                if isinstance(activity_entry, dict):
                    conflict_list = activity_entry.get("conflicts", [])
                    if isinstance(conflict_list, list):
                        conflict_list.append({
                            "type": conflict.get("type", ""),
                            "severity": conflict.get("severity", "warning"),
                            "description": conflict.get("description", ""),
                        })

        # 转换为列表格式
        result: Dict[str, list] = {}
        for day_key, activities in activity_map.items():
            result[day_key] = list(activities.values())

        return result

    def _collect_long_distance_warnings(
        self,
        day_plans: List[dict],
        transport_time_threshold: int,
    ) -> List[dict]:
        """收集所有天中超远距离的路段警告"""
        warnings = []
        for d_idx, plan in enumerate(day_plans):
            attrs = plan.get("attractions", [])
            for i in range(len(attrs) - 1):
                loc_i = attrs[i].get("location", {})
                loc_j = attrs[i + 1].get("location", {})
                dist = _haversine_km(loc_i, loc_j)
                estimated_duration_min = int((dist / 25) * 60) if dist < float('inf') else 999
                if estimated_duration_min > transport_time_threshold:
                    warnings.append({
                        "day": d_idx + 1,
                        "from": attrs[i].get("name", ""),
                        "to": attrs[i + 1].get("name", ""),
                        "distance_km": round(dist, 1),
                        "estimated_duration_min": estimated_duration_min,
                        "threshold_min": transport_time_threshold,
                    })
        return warnings


# 全局单例
negotiation_orchestrator = NegotiationOrchestrator()
