"""
协商解释模板模块

定义每个策略和冲突类型的中文解释模板，
用于生成前端可展示的人类可读说明（human_readable 字段）。

使用方式:
    from .explanation_templates import format_strategy_explanation, format_conflict_explanation
    
    # 生成策略说明
    human_readable = format_strategy_explanation("strategy_time_shift", {
        "target": "故宫",
        "before": "09:00",
        "after": "08:30",
    })
    # → "调整了故宫的时间，从09:00改为08:30"

    # 生成冲突说明
    conflict_desc = format_conflict_explanation("time_conflict", {
        "description": "故宫(09:00-12:00)与天坛(09:30-11:30)时间重叠"
    })
    # → "时间冲突：故宫(09:00-12:00)与天坛(09:30-11:30)时间重叠"
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


# ==================== 策略 → 中文说明 ====================

STRATEGY_EXPLANATIONS: Dict[str, str] = {
    "strategy_time_shift": "调整了{target}的时间，从{before}改为{after}",
    "strategy_adjust_opening_hours": "将{target}的营业时间调整为{after}",
    "strategy_swap_time_slot": "互换了{target1}和{target2}的时间段",
    "strategy_compress_duration": "将{target}的游览时长从{before}压缩至{after}",
    "strategy_replace_activity": "用{new_activity}替换了{old_activity}",
    "strategy_cross_day_move": "将{target}从第{from_day}天移至第{to_day}天",
    "strategy_closed_day_resolve": "{target}在{day}闭馆，已调整至{new_day}",
    "strategy_transport_split": "将{target}从第{from_day}天拆分到第{to_day}天",
    "strategy_geo_distance_split": "拆分远距离景点{target}到第{to_day}天",
    "strategy_geo_distance_replace": "用备选景点{new_activity}替换远距离景点{old_activity}",
}

# 策略名称的中文映射（用于日志和显示）
STRATEGY_CHINESE_NAMES: Dict[str, str] = {
    "strategy_time_shift": "时间平移",
    "strategy_adjust_opening_hours": "营业时间调整",
    "strategy_swap_time_slot": "时间段互换",
    "strategy_compress_duration": "时长压缩",
    "strategy_replace_activity": "活动替换",
    "strategy_cross_day_move": "跨天移动",
    "strategy_closed_day_resolve": "闭馆处理",
    "strategy_transport_split": "交通拆分",
    "strategy_geo_distance_split": "远距离拆分",
    "strategy_geo_distance_replace": "远距离替换",
}


# ==================== 冲突类型 → 中文说明 ====================

CONFLICT_EXPLANATIONS: Dict[str, str] = {
    "time_conflict": "时间冲突：{description}",
    "overloaded_day": "当日行程过满：{description}",
    "geo_distance_warning": "景点间距离过远：{description}",
    "unreasonable_meal_time": "用餐时间不合理：{description}",
    "outside_opening_hours": "超出营业时间：{description}",
    "budget_exceeded": "超出预算：{description}",
    "visit_duration": "游览时长不合理：{description}",
    "transport_time_warning": "交通时间过长：{description}",
    "long_transport_time": "交通时间过长：{description}",
    "cross_day_transport_warning": "跨天交通不合理：{description}",
}


# ==================== 工具函数 ====================

def format_strategy_explanation(
    strategy_name: str,
    params: Dict[str, Any],
    fallback: Optional[str] = None,
) -> str:
    """
    根据策略名称和参数生成人类可读的中文说明

    Args:
        strategy_name: 策略名称（如 strategy_time_shift）
        params: 模板参数（如 {"target": "故宫", "before": "09:00", "after": "08:30"}）
        fallback: 当没有匹配模板时的默认说明

    Returns:
        中文说明字符串
    """
    template = STRATEGY_EXPLANATIONS.get(strategy_name)
    if template:
        try:
            return template.format(**params)
        except KeyError as e:
            logger.warning(
                f"[解释模板] 策略 '{strategy_name}' 参数不足: 缺失 {e}, params={params}"
            )
            # 用已有参数尽量拼装
            partial = template
            for k, v in params.items():
                placeholder = "{" + k + "}"
                if placeholder in partial:
                    partial = partial.replace(placeholder, str(v))
            # 移除未填充的占位符
            import re
            partial = re.sub(r"\{[^}]+\}", "?", partial)
            return partial
        except Exception as e:
            logger.warning(f"[解释模板] 策略 '{strategy_name}' 格式化异常: {e}")

    # 没有模板时的 fallback
    if fallback:
        return fallback

    chinese_name = STRATEGY_CHINESE_NAMES.get(strategy_name, strategy_name)
    # 从 params 中提取有用信息构建基本描述
    target = params.get("target") or params.get("item_name", "")
    before = params.get("before", "")
    after = params.get("after", "")
    if target and before and after:
        return f"{chinese_name}: {target} 从 {before} 调整为 {after}"
    elif target:
        return f"{chinese_name}: 涉及 {target}"
    else:
        return f"执行了{chinese_name}策略"


def format_conflict_explanation(
    conflict_type: str,
    params: Dict[str, Any],
) -> str:
    """
    根据冲突类型生成人类可读的中文说明

    Args:
        conflict_type: 冲突类型（如 time_conflict）
        params: 模板参数（如 {"description": "..."}）

    Returns:
        中文说明字符串
    """
    template = CONFLICT_EXPLANATIONS.get(conflict_type)
    if template:
        try:
            return template.format(**params)
        except KeyError:
            # 回退到直接使用 description
            desc = params.get("description", "")
            if desc:
                return desc
            return f"冲突类型: {conflict_type}"
        except Exception:
            return params.get("description", f"冲突类型: {conflict_type}")

    # 没有模板时回退到 description
    return params.get("description", f"冲突类型: {conflict_type}")


def build_human_readable_from_adjustment(adj: Dict[str, Any]) -> str:
    """
    从单个 adjustment 条目生成人类可读说明

    Args:
        adj: adjustment 字典，包含 field, item_name, before, after, strategy 字段

    Returns:
        中文说明字符串
    """
    strategy_name = adj.get("strategy", "")
    item_name = adj.get("item_name", "")
    before = adj.get("before", "")
    after_val = adj.get("after", "")
    field = adj.get("field", "")

    # 尝试使用策略模板
    params = {}
    if strategy_name == "strategy_time_shift":
        params = {"target": item_name, "before": before, "after": after_val}
    elif strategy_name == "strategy_compress_duration":
        params = {"target": item_name, "before": before, "after": after_val}
    elif strategy_name == "strategy_cross_day_move":
        # 尝试从 before/after 提取天信息
        params = {"target": item_name, "from_day": before, "to_day": after_val}
    elif strategy_name == "strategy_replace_activity":
        params = {"old_activity": before, "new_activity": after_val}
    elif strategy_name == "strategy_swap_time_slot":
        params = {"target1": item_name, "target2": after_val}
    elif strategy_name == "strategy_geo_distance_split":
        params = {"target": item_name, "to_day": after_val}
    elif strategy_name == "strategy_geo_distance_replace":
        params = {"old_activity": before, "new_activity": after_val}
    elif strategy_name == "strategy_closed_day_resolve":
        params = {"target": item_name, "day": before, "new_day": after_val}
    elif strategy_name == "strategy_transport_split":
        params = {"target": item_name, "from_day": before, "to_day": after_val}
    elif strategy_name == "strategy_adjust_opening_hours":
        params = {"target": item_name, "after": after_val}

    human_readable = format_strategy_explanation(strategy_name, params)

    # 如果格式化后还是策略名本身，构建通用描述
    if human_readable == f"执行了{STRATEGY_CHINESE_NAMES.get(strategy_name, strategy_name)}策略":
        # 构建通用描述
        if field in ("游览时间", "用餐时间"):
            return f"将{item_name}的{field}从{before}调整为{after_val}"
        elif field == "游览时长":
            return f"将{item_name}的游览时长从{before}改为{after_val}"
        elif field in ("新增景点", "移除景点"):
            return f"{field}: {item_name}"
        elif field == "时间段":
            return f"将{item_name}的时间段从{before}改为{after_val}"
        else:
            return f"{field}: {item_name} ({before} → {after_val})"

    return human_readable
