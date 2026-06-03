"""行程校验相关路由"""
from datetime import datetime, timedelta
from typing import List, Dict, Any
from fastapi import APIRouter
from src.models.response import success_response, error_response
from src.models.request import TimeConflictRequest, TimeConflictResponse, ItineraryValidateRequest, ItineraryValidateResponse, ConflictItem

router = APIRouter(prefix="/api/v1/validation", tags=["行程校验"])


# ============== 时间冲突检测核心算法 ==============

def parse_time_to_minutes(time_str: str) -> int:
    """
    将时间字符串转换为分钟数（从0点开始）
    
    支持格式:
    - "HH:MM" (如 "09:30")
    - "上午" -> 540 (9:00)
    - "中午" -> 720 (12:00)
    - "下午" -> 840 (14:00)
    - "晚上" -> 1080 (18:00)
    
    Args:
        time_str: 时间字符串
    
    Returns:
        分钟数
    """
    time_slots = {
        "morning": 540,    # 9:00
        "afternoon": 840,  # 14:00
        "evening": 1080,   # 18:00
        "上午": 540,
        "中午": 720,
        "下午": 840,
        "晚上": 1080
    }
    
    # 检查是否是预定义时间槽
    if time_str.lower() in time_slots:
        return time_slots[time_str.lower()]
    
    # 尝试解析 HH:MM 格式
    try:
        parts = time_str.split(":")
        if len(parts) == 2:
            hours = int(parts[0])
            minutes = int(parts[1])
            return hours * 60 + minutes
    except:
        pass
    
    # 默认返回9:00
    return 540


def parse_duration_to_minutes(duration_str: str) -> int:
    """
    将时长字符串转换为分钟数
    
    支持格式:
    - "2小时" -> 120
    - "30分钟" -> 30
    - "2-3小时" -> 150 (取平均值)
    - "半天" -> 240
    - "全天" -> 480
    
    Args:
        duration_str: 时长字符串
    
    Returns:
        分钟数
    """
    if not duration_str:
        return 120  # 默认2小时
    
    # 处理范围格式 "2-3小时"
    if "-" in duration_str and "小时" in duration_str:
        try:
            parts = duration_str.replace("小时", "").split("-")
            avg_hours = (float(parts[0]) + float(parts[1])) / 2
            return int(avg_hours * 60)
        except:
            pass
    
    # 处理单值小时格式 "2小时"
    if "小时" in duration_str:
        try:
            hours = float(duration_str.replace("小时", ""))
            return int(hours * 60)
        except:
            pass
    
    # 处理分钟格式 "30分钟"
    if "分钟" in duration_str:
        try:
            return int(duration_str.replace("分钟", ""))
        except:
            pass
    
    # 特殊处理
    if "半天" in duration_str:
        return 240
    if "全天" in duration_str:
        return 480
    
    # 默认返回2小时
    return 120


def check_time_overlap(start1: int, end1: int, start2: int, end2: int) -> bool:
    """
    检查两个时间区间是否重叠
    
    算法: 两个区间不重叠的条件是 end1 <= start2 或 end2 <= start1
    因此重叠的条件是: start1 < end2 AND start2 < end1
    
    Args:
        start1, end1: 第一个区间的起止时间（分钟）
        start2, end2: 第二个区间的起止时间（分钟）
    
    Returns:
        True表示有重叠，False表示无重叠
    """
    return start1 < end2 and start2 < end1


def detect_time_conflicts(schedule: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    检测行程中的时间冲突
    
    Args:
        schedule: 活动列表，每个活动包含:
            - name: 活动名称
            - start_time: 开始时间 (HH:MM 或 时间槽)
            - end_time: 结束时间 (可选)
            - duration: 持续时间 (可选，如果没有end_time则使用duration计算)
            - activity_type: 活动类型 (attraction/meal/transport/accommodation)
            - location: 地点 (用于计算交通时间)
    
    Returns:
        {
            "has_conflict": bool,
            "conflicts": [
                {
                    "type": "time_overlap",
                    "description": "冲突描述",
                    "severity": "error",
                    "activities": ["活动1", "活动2"]
                }
            ]
        }
    """
    conflicts = []
    
    # 第一步: 解析所有活动的时间区间
    activities = []
    for idx, item in enumerate(schedule):
        name = item.get("name", f"活动{idx+1}")
        activity_type = item.get("activity_type", "unknown")
        
        # 解析开始时间
        start_time_str = item.get("start_time")
        if not start_time_str:
            # 如果没有指定开始时间，根据上一个活动的结束时间推算
            if activities:
                prev_end = activities[-1]["end_minutes"]
                # 预留30分钟交通/休息时间
                start_minutes = prev_end + 30
            else:
                start_minutes = 540  # 默认9:00开始
        else:
            start_minutes = parse_time_to_minutes(start_time_str)
        
        # 解析结束时间或持续时间
        end_time_str = item.get("end_time")
        duration_str = item.get("duration")
        
        if end_time_str:
            end_minutes = parse_time_to_minutes(end_time_str)
        elif duration_str:
            duration_minutes = parse_duration_to_minutes(duration_str)
            end_minutes = start_minutes + duration_minutes
        else:
            # 默认持续2小时
            end_minutes = start_minutes + 120
        
        activities.append({
            "index": idx,
            "name": name,
            "type": activity_type,
            "start_minutes": start_minutes,
            "end_minutes": end_minutes,
            "location": item.get("location", ""),
            "raw_data": item
        })
    
    # 第二步: 两两检查时间重叠
    for i in range(len(activities)):
        for j in range(i + 1, len(activities)):
            act1 = activities[i]
            act2 = activities[j]
            
            if check_time_overlap(act1["start_minutes"], act1["end_minutes"],
                                 act2["start_minutes"], act2["end_minutes"]):
                conflicts.append({
                    "type": "time_overlap",
                    "description": f"'{act1['name']}' ({format_minutes(act1['start_minutes'])}-{format_minutes(act1['end_minutes'])}) "
                                  f"与 '{act2['name']}' ({format_minutes(act2['start_minutes'])}-{format_minutes(act2['end_minutes'])}) 时间重叠",
                    "severity": "error",
                    "activities": [act1["name"], act2["name"]]
                })
    
    # 第三步: 检查活动时间合理性
    for act in activities:
        # 检查是否超过合理的一天时长（6:00-23:00）
        if act["start_minutes"] < 360:  # 早于6:00
            conflicts.append({
                "type": "unreasonable_time",
                "description": f"'{act['name']}' 开始时间过早 ({format_minutes(act['start_minutes'])})",
                "severity": "warning",
                "activities": [act["name"]]
            })
        
        if act["end_minutes"] > 1380:  # 晚于23:00
            conflicts.append({
                "type": "unreasonable_time",
                "description": f"'{act['name']}' 结束时间过晚 ({format_minutes(act['end_minutes'])})",
                "severity": "warning",
                "activities": [act["name"]]
            })
        
        # 检查景点游览时长是否合理
        if act["type"] == "attraction":
            duration = act["end_minutes"] - act["start_minutes"]
            if duration < 30:
                conflicts.append({
                    "type": "too_short_duration",
                    "description": f"'{act['name']}' 游览时间过短 ({duration}分钟)，建议至少1小时",
                    "severity": "warning",
                    "activities": [act["name"]]
                })
            elif duration > 480:  # 超过8小时
                conflicts.append({
                    "type": "too_long_duration",
                    "description": f"'{act['name']}' 游览时间过长 ({duration}分钟)，建议分多天游览",
                    "severity": "warning",
                    "activities": [act["name"]]
                })
    
    # 第四步: 检查每日总时长
    if activities:
        day_start = min(act["start_minutes"] for act in activities)
        day_end = max(act["end_minutes"] for act in activities)
        total_hours = (day_end - day_start) / 60
        
        if total_hours > 12:
            conflicts.append({
                "type": "overloaded_day",
                "description": f"当日行程总时长 {total_hours:.1f} 小时，建议不超过12小时",
                "severity": "warning",
                "activities": [act["name"] for act in activities]
            })
    
    return {
        "has_conflict": any(c["severity"] == "error" for c in conflicts),
        "conflicts": conflicts
    }


def format_minutes(minutes: int) -> str:
    """将分钟数转换为 HH:MM 格式"""
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def parse_opening_hours(opening_hours_str: str):
    """
    解析开放时间字符串为开始和结束时间（分钟）
    
    支持格式:
    - "08:00-17:00" -> (480, 1020)
    - "09:00-18:00" -> (540, 1080)
    - "全天开放" -> (0, 1440)
    - "不开放" -> None
    
    Args:
        opening_hours_str: 开放时间字符串
    
    Returns:
        (start_minutes, end_minutes) 或 None
    """
    if not opening_hours_str or opening_hours_str in ["不开放", "关闭", ""]:
        return None
    
    # 处理特殊格式
    if "全天" in opening_hours_str:
        return (0, 1440)
    
    # 尝试解析 "HH:MM-HH:MM" 格式
    try:
        parts = opening_hours_str.split("-")
        if len(parts) == 2:
            start_minutes = parse_time_to_minutes(parts[0].strip())
            end_minutes = parse_time_to_minutes(parts[1].strip())
            return (start_minutes, end_minutes)
    except:
        pass
    
    return None


def check_attraction_opening_hours(attraction: Dict[str, Any], visit_start: int, visit_end: int) -> List[Dict[str, Any]]:
    """
    检查景点游览时间是否在开放时间内
    
    Args:
        attraction: 景点信息（包含opening_hours字段）
        visit_start: 计划游览开始时间（分钟）
        visit_end: 计划游览结束时间（分钟）
    
    Returns:
        冲突列表
    """
    conflicts = []
    opening_hours_str = attraction.get("opening_hours")
    
    if not opening_hours_str:
        # 如果没有开放时间信息，跳过检查
        return conflicts
    
    open_times = parse_opening_hours(opening_hours_str)
    if not open_times:
        return conflicts
    
    open_start, open_end = open_times
    attraction_name = attraction.get("name", "未知景点")
    
    # 检查是否完全在开放时间外
    if visit_end <= open_start or visit_start >= open_end:
        conflicts.append({
            "type": "outside_opening_hours",
            "description": f"'{attraction_name}' 不在开放时间内（开放时间: {opening_hours_str}）",
            "severity": "error",
            "activities": [attraction_name]
        })
    # 检查是否部分在开放时间外
    elif visit_start < open_start or visit_end > open_end:
        conflicts.append({
            "type": "partial_outside_opening_hours",
            "description": f"'{attraction_name}' 部分游览时间超出开放范围（开放时间: {opening_hours_str}）",
            "severity": "warning",
            "activities": [attraction_name]
        })
    
    return conflicts


def calculate_transport_time(from_location: str, to_location: str) -> int:
    """
    估算两点之间的交通时间（简化版）
    
    实际应用中应调用地图API获取真实数据
    这里使用简化的规则：
    - 同一区域: 15分钟
    - 不同区域: 30-60分钟
    
    Args:
        from_location: 起点
        to_location: 终点
    
    Returns:
        预计交通时间（分钟）
    """
    if not from_location or not to_location:
        return 30  # 默认30分钟
    
    # 简化判断：如果地点相同或包含关系，认为距离较近
    if from_location == to_location or from_location in to_location or to_location in from_location:
        return 15
    
    # 其他情况默认30分钟
    return 30


def check_itinerary_conflicts(day_plans: List[Dict[str, Any]], structured_requirement: Dict[str, Any]) -> Dict[str, Any]:
    """
    完整的行程校验（包括时间冲突、预算等）
    
    Args:
        day_plans: 每日行程计划列表
        structured_requirement: 结构化需求（包含预算等信息）
    
    Returns:
        {
            "valid": bool,
            "conflicts": [...],
            "suggestions": [...]
        }
    """
    all_conflicts = []
    suggestions = []
    total_cost = 0
    
    # 遍历每一天的行程
    for day_idx, day_plan in enumerate(day_plans):
        day_num = day_idx + 1
        date = day_plan.get("date", f"第{day_num}天")
        
        # 收集当天的所有活动
        daily_activities = []
        
        # 添加景点活动
        for attraction in day_plan.get("attractions", []):
            if not isinstance(attraction, dict):
                continue
            daily_activities.append({
                "name": attraction.get("name", "未知景点"),
                "start_time": attraction.get("start_time") or attraction.get("visit_time", "上午"),
                "end_time": attraction.get("end_time"),
                "duration": attraction.get("visit_duration", "2小时"),
                "activity_type": "attraction",
                "location": attraction.get("address", ""),
                "cost": attraction.get("ticket_price", 0) if isinstance(attraction.get("ticket_price"), (int, float)) else 0
            })
            total_cost += attraction.get("ticket_price", 0) if isinstance(attraction.get("ticket_price"), (int, float)) else 0
        
        # 添加餐饮活动
        for meal in day_plan.get("meals", []):
            if not isinstance(meal, dict):
                continue
            daily_activities.append({
                "name": meal.get("name", "用餐"),
                "start_time": meal.get("start_time") or meal.get("time") or meal.get("meal_time", "中午"),
                "end_time": meal.get("end_time"),
                "duration": meal.get("duration", "1小时"),
                "activity_type": "meal",
                "location": meal.get("address", ""),
                "cost": meal.get("avg_price_per_person", 0) if isinstance(meal.get("avg_price_per_person"), (int, float)) else 0
            })
            total_cost += meal.get("avg_price_per_person", 0) if isinstance(meal.get("avg_price_per_person"), (int, float)) else 0
        
        # 添加交通活动
        if day_plan.get("transport"):
            transport = day_plan["transport"]
            if isinstance(transport, dict):
                daily_activities.append({
                    "name": f"前往{transport.get('to', '目的地')}",
                    "start_time": transport.get("departure_time", "上午"),
                    "duration": transport.get("duration", "1小时"),
                    "activity_type": "transport",
                    "location": "",
                    "cost": transport.get("price", 0) if isinstance(transport.get("price"), (int, float)) else 0
                })
                total_cost += transport.get("price", 0) if isinstance(transport.get("price"), (int, float)) else 0
        
        # 对该天的活动进行时间冲突检测
        if daily_activities:
            day_result = detect_time_conflicts(daily_activities)
            for conflict in day_result["conflicts"]:
                conflict["day"] = day_num
                conflict["date"] = date
                all_conflicts.append(conflict)
        
        # 检查景点开放时间
        for attraction in day_plan.get("attractions", []):
            if not isinstance(attraction, dict):
                continue
            # 解析游览时间
            start_time_str = attraction.get("start_time") or attraction.get("visit_time", "上午")
            start_minutes = parse_time_to_minutes(start_time_str)
            
            duration_str = attraction.get("visit_duration", "2小时")
            duration_minutes = parse_duration_to_minutes(duration_str)
            end_minutes = start_minutes + duration_minutes
            
            # 检查开放时间
            opening_conflicts = check_attraction_opening_hours(attraction, start_minutes, end_minutes)
            for conflict in opening_conflicts:
                conflict["day"] = day_num
                conflict["date"] = date
                all_conflicts.append(conflict)
    
    # 检查总预算
    budget_limit = structured_requirement.get("total_budget", 0)
    if budget_limit > 0 and total_cost > budget_limit:
        all_conflicts.append({
            "type": "budget_exceeded",
            "description": f"总花费 {total_cost} 元超出预算 {budget_limit} 元",
            "severity": "error",
            "activities": []
        })
        suggestions.append("建议调整部分景点或选择更经济的餐厅")
    
    # 生成建议
    if not all_conflicts:
        suggestions.append("行程安排合理，无时间冲突")
    
    has_error = any(c["severity"] == "error" for c in all_conflicts)
    
    return {
        "valid": not has_error,
        "conflicts": all_conflicts,
        "suggestions": suggestions,
        "total_cost": total_cost
    }



# ==============协商修复路由 ==============

@router.post("/negotiate")
async def negotiate_itinerary(request: ItineraryValidateRequest):
    """
    协商修复接口 - 自动检测冲突并尝试修复

    流程:
      1. 接收行程和需求
      2. 调用协商引擎进行多轮修复
      3. 返回修复后的行程和修复日志

    请求参数:
    {
        "day_plans": [...],
        "structured_requirement": {...}
    }

    响应:
    {
        "code": 200,
        "data": {
            "day_plans": [...],       // 修复后的行程
            "negotiation": {
                "log": [...],          // 修复日志
                "iteration_count": 3,
                "fully_resolved": true
            },
            "final_validation": {...}
        }
    }
    """
    if not request.day_plans:
        return error_response(code=400, msg="缺少行程计划数据")

    try:
        day_plans_dict = []
        for plan in request.day_plans:
            plan_dict = plan.model_dump()
            if plan_dict.get('attractions'):
                plan_dict['attractions'] = [
                    item if isinstance(item, dict) else item.model_dump()
                    if hasattr(item, 'model_dump') else item
                    for item in plan_dict['attractions']
                ]
            if plan_dict.get('meals'):
                plan_dict['meals'] = [
                    item if isinstance(item, dict) else item.model_dump()
                    if hasattr(item, 'model_dump') else item
                    for item in plan_dict['meals']
                ]
            if plan_dict.get('transport') and hasattr(plan_dict['transport'], 'model_dump'):
                plan_dict['transport'] = plan_dict['transport'].model_dump()
            day_plans_dict.append(plan_dict)

        structured_req = {}
        if hasattr(request, 'structured_requirement') and request.structured_requirement:
            structured_req = request.structured_requirement if isinstance(
                request.structured_requirement, dict
            ) else {}

        # 调用协商引擎
        from src.services.negotiation_service import negotiate_and_fix
        result = await negotiate_and_fix(
            day_plans=day_plans_dict,
            structured_requirement=structured_req,
            max_iterations=5
        )

        return success_response(
            data={
                "day_plans": result["day_plans"],
                "negotiation": result.get("negotiation_log", []),
                "iteration_count": result["iteration_count"],
                "fully_resolved": result["fully_resolved"],
                "final_validation": result.get("validation", {})
            },
            msg=f"协商{'成功' if result['fully_resolved'] else '完成（部分冲突未解决）'}"
        )

    except Exception as e:
        return error_response(code=500, msg=f"协商修复失败: {str(e)}")




# ============== API 路由 ==============

@router.post("/time-conflict")
async def check_time_conflict(request: TimeConflictRequest):
    """
    时间冲突检测接口
    
    请求参数:
    {
        "schedule": [
            {
                "name": "故宫博物院",
                "start_time": "09:00",
                "end_time": "12:00",
                "activity_type": "attraction",
                "location": "北京市东城区"
            },
            {
                "name": "午餐",
                "start_time": "11:30",
                "duration": "1小时",
                "activity_type": "meal",
                "location": "王府井"
            }
        ]
    }
    """
    result = detect_time_conflicts(request.schedule)
    
    return success_response(
        data={
            "has_conflict": result["has_conflict"],
            "conflicts": result["conflicts"]
        },
        msg="时间冲突检测完成"
    )


@router.post("/itinerary")
async def validate_itinerary(request: ItineraryValidateRequest):
    """
    完整行程校验接口
    
    请求参数:
    {
        "day_plans": [
            {
                "day": 1,
                "date": "2026-05-20",
                "attractions": [...],
                "meals": [...],
                "transport": {...}
            }
        ],
        "structured_requirement": {
            "total_budget": 5000,
            ...
        }
    }
    """
    if not request.day_plans:
        return error_response(code=400, msg="缺少行程计划数据")
    
    try:
        # 将 Pydantic 模型转换为字典列表（深度转换）
        day_plans_dict = []
        for plan in request.day_plans:
            plan_dict = plan.model_dump()
            # 确保嵌套对象也是字典格式
            if plan_dict.get('attractions'):
                plan_dict['attractions'] = [
                    item if isinstance(item, dict) else item.model_dump() if hasattr(item, 'model_dump') else item
                    for item in plan_dict['attractions']
                ]
            if plan_dict.get('meals'):
                plan_dict['meals'] = [
                    item if isinstance(item, dict) else item.model_dump() if hasattr(item, 'model_dump') else item
                    for item in plan_dict['meals']
                ]
            if plan_dict.get('transport') and hasattr(plan_dict['transport'], 'model_dump'):
                plan_dict['transport'] = plan_dict['transport'].model_dump()
            day_plans_dict.append(plan_dict)
        
        # 提取结构化需求（如果有）
        structured_req = {}
        if hasattr(request, 'structured_requirement') and request.structured_requirement:
            structured_req = request.structured_requirement if isinstance(request.structured_requirement, dict) else {}
        
        result = check_itinerary_conflicts(day_plans_dict, structured_req)
        
        # 转换冲突项为模型格式
        conflict_items = []
        for conflict in result["conflicts"]:
            conflict_items.append(ConflictItem(
                type=conflict["type"],
                description=conflict["description"],
                severity=conflict["severity"]
            ))
        
        return success_response(
            data=ItineraryValidateResponse(
                valid=result["valid"],
                conflicts=conflict_items,
                suggestions=result["suggestions"]
            ).model_dump(),
            msg="行程校验完成"
        )
    except Exception as e:
        return error_response(code=500, msg=f"行程校验失败: {str(e)}")
