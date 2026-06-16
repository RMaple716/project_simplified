#!/usr/bin/env python
"""
替换 negotiation_service.py 中的硬编码策略链为动态策略选择器 + LLM仲裁者
"""
import re

def main():
    with open("src/services/negotiation_service.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Find the section to replace
    start_marker = "# 尝试策略1~5（按优先级），一旦某个策略成功就标记 fixed 并继续下一个 conflict\n                conflict_fixed = False"
    start_idx = content.find(start_marker)
    if start_idx == -1:
        print("ERROR: Could not find start marker")
        # Try partial match
        alt_marker = "冲突成功就标记 fixed"
        alt_idx = content.find(alt_marker)
        print(f"alt_idx={alt_idx}")
        if alt_idx >= 0:
            print(f"Context: {content[alt_idx-50:alt_idx+100]}")
        exit(1)

    # Find the end marker
    end_marker = "                if conflict_fixed:\n                    any_fixed = True\n\n        if not any_fixed:"
    end_idx = content.find(end_marker, start_idx)
    if end_idx == -1:
        print("ERROR: Could not find end marker")
        exit(1)

    replacement_end = end_idx + len("                if conflict_fixed:\n                    any_fixed = True")

    print(f"Found section: {start_idx} -> {replacement_end}")
    print(f"Length to replace: {replacement_end - start_idx} chars")

    # Build the replacement code
    replacement = r"""                # ========== 【P0改进】使用动态策略选择器 + LLM仲裁者 ==========
                # 替换原有的15个硬编码 if/elif 策略块，
                # 改用 strategy_selector 根据冲突类型动态推荐策略，
                # 所有确定性策略失败后调用 LLM仲裁者 作为兜底。
                conflict_fixed = False
                conflict_type = conflict.get("type", "")
                conflict_activities = conflict.get("activities", [])

                # 步骤1: 用动态策略选择器获取适用于该冲突类型的策略列表
                selected_strategies = strategy_selector.select_strategies(
                    conflict_type=conflict_type,
                    top_n=8,
                )

                if selected_strategies:
                    logger.info(
                        f"[协商] 第{iteration + 1}轮, day{day_num}, "
                        f"冲突类型={conflict_type}, "
                        f"策略选择器推荐: {[s['name'] for s in selected_strategies]}"
                    )
                else:
                    logger.info(
                        f"[协商] 第{iteration + 1}轮, day{day_num}, "
                        f"冲突类型={conflict_type}: 策略选择器无推荐, 回退原始策略链"
                    )
                    # 如果策略选择器没有推荐，回退到默认策略集
                    selected_strategies = []
                    for fallback_name in [
                        "strategy_time_shift", "strategy_adjust_opening_hours",
                        "strategy_swap_time_slot", "strategy_compress_duration",
                        "strategy_replace_activity", "strategy_cross_day_move",
                    ]:
                        registry = strategy_selector.registry
                        if fallback_name in registry._strategies:
                            info = registry._strategies[fallback_name]
                            selected_strategies.append({
                                "name": fallback_name,
                                "func": info["func"],
                                "priority": info["priority"],
                                "description": info.get("description", ""),
                                "is_async": info.get("is_async", False),
                                "conflict_types": info.get("conflict_types", []),
                            })

                # 步骤2: 按策略选择器推荐的顺序逐一尝试策略
                for strategy_info in selected_strategies:
                    if conflict_fixed:
                        break

                    strategy_name = strategy_info["name"]

                    plan_before_snapshot = copy.deepcopy(current_plans[day_idx])
                    plans_before_snapshot_multi = copy.deepcopy(current_plans)

                    try:
                        result = None

                        if strategy_name == "strategy_time_shift":
                            result = strategy_time_shift(current_plans[day_idx], conflict, margin=15)
                        elif strategy_name == "strategy_adjust_opening_hours":
                            result = strategy_adjust_opening_hours(current_plans[day_idx], conflict)
                        elif strategy_name == "strategy_swap_time_slot":
                            result = strategy_swap_time_slot(current_plans[day_idx], conflict)
                        elif strategy_name == "strategy_compress_duration":
                            result = strategy_compress_duration(current_plans[day_idx], conflict)
                        elif strategy_name == "strategy_replace_activity":
                            if backup_attractions:
                                result = strategy_replace_activity(
                                    current_plans[day_idx], conflict, backup_attractions
                                )
                        elif strategy_name == "strategy_cross_day_move":
                            if len(current_plans) > 1:
                                result = strategy_cross_day_move(current_plans, conflict)
                        elif strategy_name == "strategy_closed_day_resolve":
                            if len(current_plans) > 1 and conflict_type == "closed_day":
                                result = strategy_closed_day_resolve(
                                    current_plans, conflict, structured_requirement
                                )
                        elif strategy_name == "strategy_transport_split":
                            if conflict_type == "time_overlap" and conflict_activities:
                                transport = current_plans[day_idx].get("transport")
                                if isinstance(transport, dict):
                                    transport_name = f"前往{transport.get('to', '')}"
                                    meals = current_plans[day_idx].get("meals", [])
                                    for meal in meals:
                                        if isinstance(meal, dict):
                                            meal_name = meal.get("name", "")
                                            if transport_name in conflict_activities and meal_name in conflict_activities:
                                                result = strategy_transport_split(current_plans[day_idx], conflict)
                                                break
                        elif strategy_name == "strategy_geo_distance_split":
                            if conflict_type in ("geo_distance",) and len(current_plans) > 1:
                                result = strategy_geo_distance_split(
                                    current_plans, conflict, structured_requirement
                                )
                        elif strategy_name == "strategy_geo_distance_replace":
                            if conflict_type in ("geo_distance",) and backup_attractions:
                                result = strategy_geo_distance_replace(
                                    current_plans[day_idx], conflict, backup_attractions
                                )

                        # 处理策略结果
                        if result is not None and result is not False:
                            is_multi_day = strategy_name in (
                                "strategy_cross_day_move", "strategy_closed_day_resolve",
                                "strategy_geo_distance_split",
                            )

                            if is_multi_day and len(current_plans) > 1:
                                adjustments = []
                                for d_idx in range(len(current_plans)):
                                    old_plan = plans_before_snapshot_multi[d_idx] if d_idx < len(plans_before_snapshot_multi) else {}
                                    new_plan = result[d_idx] if d_idx < len(result) else {}
                                    adj = _build_adjustment_details(old_plan, new_plan, strategy_name)
                                    adjustments.extend(adj)
                                current_plans = result
                            else:
                                if isinstance(result, dict) and result.get("attractions") is not None:
                                    current_plans[day_idx] = result
                                    adjustments = _build_adjustment_details(plan_before_snapshot, result, strategy_name) if plan_before_snapshot else []
                                else:
                                    adjustments = []

                            # 记录日志
                            action_name = strategy_name.replace("strategy_", "").replace("_", "\u00b7")
                            negotiation_log.append({
                                "iteration": iteration + 1, "day": day_num,
                                "action": f"动态策略-{action_name}",
                                "target": conflict_activities,
                                "type": conflict_type,
                                "adjustments": adjustments,
                            })

                            # 发布事件
                            target_agent = "all_vehicles" if is_multi_day else f"day_{day_num}"
                            await event_bus.publish(session_id, create_negotiation_event(
                                event_type=NegotiationEventType.COUNTER,
                                session_id=session_id,
                                from_agent="dispatcher",
                                to_agent=target_agent,
                                phase=NegotiationPhase.NEGOTIATE,
                                proposal={
                                    "action": f"动态策略-{action_name}",
                                    "target": conflict_activities,
                                    "adjustments": adjustments,
                                },
                                utility={"dispatcher": 0.6, "vehicle": 0.5},
                                route_preview=build_route_preview(vehicle_id=f"day{day_num}", coordinates=[]),
                            ))

                            strategy_selector.record_success(strategy_name)
                            conflict_fixed = True
                        else:
                            strategy_selector.record_failure(strategy_name)

                    except Exception as e:
                        logger.warning(f"[协商] 策略 {strategy_name} 执行异常: {e}")
                        strategy_selector.record_failure(strategy_name)
                        continue

                # ========== 【P0改进】步骤3: 所有确定性策略失败 → 调用LLM仲裁者 ==========
                if not conflict_fixed:
                    logger.info(
                        f"[协商] 第{iteration + 1}轮, day{day_num}: "
                        f"所有确定性策略失败，尝试LLM仲裁者..."
                    )
                    try:
                        llm_result = await llm_arbiter.arbitrate(
                            day_plans=current_plans,
                            structured_requirement=structured_requirement,
                            conflicts=[conflict],
                            negotiation_log=negotiation_log,
                            session_id=session_id,
                        )

                        if llm_result and llm_result.get("day_plans"):
                            current_plans = llm_result["day_plans"]
                            adjustments = llm_result.get("adjustments", [])
                            analysis = llm_result.get("analysis", "")
                            solution_type = llm_result.get("solution_type", "")

                            negotiation_log.append({
                                "iteration": iteration + 1, "day": day_num,
                                "action": f"LLM仲裁({solution_type})",
                                "target": conflict_activities,
                                "type": conflict_type,
                                "adjustments": adjustments,
                                "analysis": analysis,
                            })

                            await event_bus.publish(session_id, create_negotiation_event(
                                event_type=NegotiationEventType.COUNTER,
                                session_id=session_id,
                                from_agent="llm_arbiter",
                                to_agent="dispatcher",
                                phase=NegotiationPhase.NEGOTIATE,
                                proposal={
                                    "action": f"LLM仲裁({solution_type})",
                                    "analysis": analysis,
                                    "adjustments": adjustments,
                                },
                                utility={"dispatcher": 0.4, "vehicle": 0.4},
                            ))

                            logger.info(
                                f"[协商] LLM仲裁成功: {analysis}, "
                                f"生成{len(adjustments)}项调整"
                            )
                            conflict_fixed = True
                        else:
                            logger.info(
                                f"[协商] LLM仲裁未返回有效方案"
                            )
                    except Exception as e:
                        logger.warning(f"[协商] LLM仲裁异常: {e}")

                # 步骤4: 记录本轮结果
                if conflict_fixed:
                    any_fixed = True
                    logger.info(
                        f"[协商] 第{iteration + 1}轮, day{day_num}: "
                        f"冲突已解决 (冲突类型={conflict_type})"
                    )
                else:
                    logger.info(
                        f"[协商] 第{iteration + 1}轮, day{day_num}: "
                        f"所有策略(含LLM)均失败 (冲突类型={conflict_type})"
                    )"""

    new_content = content[:start_idx] + replacement + content[replacement_end:]

    with open("src/services/negotiation_service.py", "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"Replacement complete! New file written.")
    print(f"Old section: {replacement_end - start_idx} chars")
    print(f"New section: {len(replacement)} chars")

if __name__ == "__main__":
    main()
