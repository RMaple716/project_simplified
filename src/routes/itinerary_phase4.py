"""
行程相关路由 — 【第四阶段】用户体验闭环

新增 API:
- GET  /api/v1/itinerary/{id}/result          获取协商结果（含确认状态）
- POST /api/v1/itinerary/{id}/confirm          接受方案
- POST /api/v1/itinerary/{id}/reject           拒绝并重新协商
- POST /api/v1/itinerary/{id}/adjust           保存用户手动调整
- GET  /api/v1/itinerary/{id}/versions         获取历史版本列表
- GET  /api/v1/itinerary/{id}/versions/{version_id}  获取特定版本详情
- GET  /api/v1/itinerary/{id}/adjustments-summary  获取调整摘要列表
"""
import json
import copy
import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.response import success_response, error_response
from src.services.database_service import ItineraryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/itinerary", tags=["行程-用户体验闭环"])


# ==================== 协商结果查询（含确认状态） ====================

@router.get("/{itinerary_id}/result")
async def get_itinerary_result(
    itinerary_id: str,
    db: Session = Depends(get_db),
):
    """
    获取行程的协商结果（含确认状态）

    这是第四阶段"用户确认"环节的入口API。
    返回结果中包含 status、adjustments_summary、user_options 等字段。

    响应示例:
    {
        "code": 200,
        "data": {
            "status": "pending_confirmation",
            "day_plans": [...],
            "adjustments_summary": [
                "故宫游览时间从09:00调整为08:30",
                ...
            ],
            "conflicts": [...],
            "utility": {...},
            "pareto_analysis": {...},
            "user_options": ["accept", "adjust", "reject"]
        }
    }
    """
    itinerary = ItineraryService.get_itinerary(db, itinerary_id)
    if itinerary is None:
        return error_response(code=404, msg="行程不存在")

    # 确保 day_plans 是 Python list（非 Column 类型）
    raw_day_plans = itinerary.day_plans
    if isinstance(raw_day_plans, list):
        day_plans = raw_day_plans
    else:
        day_plans = []

    # 从 day_plans 中提取协商结果信息
    negotiation_info = {}
    if len(day_plans) > 0 and isinstance(day_plans[0], dict):
        neg = day_plans[0].get("negotiation", {})
        if isinstance(neg, dict):
            negotiation_info = neg

    # 解析 adjustments_summary（Column[Any] -> 实际值）
    raw_adjustments_summary = itinerary.adjustments_summary
    adjustments_summary = (
        raw_adjustments_summary
        if isinstance(raw_adjustments_summary, list)
        else negotiation_info.get("adjustments_summary", [])
    )

    # 检测当前冲突
    conflicts = []
    try:
        from src.models.db_models import UserRequirement
        from src.services.negotiation_core.conflict_detector import detect_conflicts
        requirement = db.query(UserRequirement).filter(
            UserRequirement.requirement_id == itinerary.requirement_id
        ).first()
        # 使用 dict() 确保 requirement_data 是 Python dict 而非 Column 类型
        if requirement is not None:
            req_data = requirement.requirement_data
            if isinstance(req_data, dict):
                detection = detect_conflicts(day_plans, req_data)
                conflicts = detection.conflicts
    except Exception as e:
        logger.warning(f"[协商结果] 冲突检测异常: {e}")
        conflicts = negotiation_info.get("conflicts", [])

    # 提取效用信息
    utility = negotiation_info.get("utility", {})
    pareto_analysis = negotiation_info.get("pareto_analysis")

    # 获取实际 status 值
    raw_status = itinerary.status
    resolved_status = str(raw_status) if raw_status is not None else "draft"
    if resolved_status not in ("pending_confirmation", "confirmed", "rejected", "adjusting"):
        resolved_status = "pending_confirmation"

    return success_response(
        data={
            "itinerary_id": itinerary.itinerary_id,
            "status": resolved_status,
            "day_plans": day_plans,
            "adjustments_summary": adjustments_summary,
            "conflicts": conflicts,
            "utility": utility,
            "pareto_analysis": pareto_analysis,
            "user_options": ["accept", "adjust", "reject"],
        },
        msg="获取协商结果成功"
    )


# ==================== 用户确认 — 接受方案 ====================

@router.post("/{itinerary_id}/confirm")
async def confirm_itinerary(
    itinerary_id: str,
    db: Session = Depends(get_db),
):
    """
    用户接受协商方案

    将行程状态从 pending_confirmation 改为 confirmed，
    并保存当前 day_plans 到 version_history 中。

    响应:
    {
        "code": 200,
        "data": {
            "itinerary_id": "...",
            "status": "confirmed",
            "msg": "方案已确认"
        }
    }
    """
    itinerary = ItineraryService.get_itinerary(db, itinerary_id)
    if itinerary is None:
        return error_response(code=404, msg="行程不存在")

    # 获取实际 status 值（SQLAlchemy Column -> str）
    current_status = str(itinerary.status) if itinerary.status is not None else "draft"
    if current_status == "confirmed":
        return success_response(
            data={"itinerary_id": itinerary_id, "status": "confirmed"},
            msg="方案已被确认过"
        )

    if current_status == "rejected":
        return error_response(code=400, msg="方案已被拒绝，请重新协商")

    # 保存当前版本到历史记录（确保类型安全）
    raw_version_history = itinerary.version_history
    version_history = raw_version_history if isinstance(raw_version_history, list) else []
    version_id = str(uuid.uuid4())

    # 复制 day_plans
    raw_day_plans = itinerary.day_plans
    day_plans_copy = copy.deepcopy(raw_day_plans) if isinstance(raw_day_plans, list) else []

    # 复制 adjustments_summary
    raw_summary = itinerary.adjustments_summary
    summary_copy = raw_summary if isinstance(raw_summary, list) else []

    version_history.append({
        "version_id": version_id,
        "status": "confirmed",
        "day_plans": day_plans_copy,
        "adjustments_summary": summary_copy,
        "created_at": datetime.utcnow().isoformat(),
    })

    updates = {
        "status": "confirmed",
        "version_history": version_history,
    }
    ItineraryService.update_itinerary(db, itinerary_id, updates)

    return success_response(
        data={
            "itinerary_id": itinerary_id,
            "status": "confirmed",
            "version_id": version_id,
        },
        msg="方案已确认"
    )


# ==================== 用户拒绝 — 重新协商 ====================

@router.post("/{itinerary_id}/reject")
async def reject_itinerary(
    itinerary_id: str,
    reject_reason: Optional[str] = Body(None, description="拒绝原因（可选）"),
    db: Session = Depends(get_db),
):
    """
    用户拒绝方案，触发重新协商

    将行程状态设为 rejected，记录拒绝原因，
    返回一个标志位供前端触发重新协商。

    请求体（可选）:
    {
        "reject_reason": "时间安排太紧凑"
    }

    响应:
    {
        "code": 200,
        "data": {
            "itinerary_id": "...",
            "status": "rejected",
            "should_renegotiate": true,
            "msg": "方案已拒绝，可重新协商"
        }
    }
    """
    itinerary = ItineraryService.get_itinerary(db, itinerary_id)
    if itinerary is None:
        return error_response(code=404, msg="行程不存在")

    # 保存当前版本到历史记录（标记为 rejected）
    raw_version_history = itinerary.version_history
    version_history = raw_version_history if isinstance(raw_version_history, list) else []
    version_id = str(uuid.uuid4())

    # 复制 day_plans（确保类型安全）
    raw_day_plans = itinerary.day_plans
    day_plans_copy = copy.deepcopy(raw_day_plans) if isinstance(raw_day_plans, list) else []

    version_history.append({
        "version_id": version_id,
        "status": "rejected",
        "reject_reason": reject_reason or "",
        "day_plans": day_plans_copy,
        "created_at": datetime.utcnow().isoformat(),
    })

    updates = {
        "status": "rejected",
        "version_history": version_history,
    }
    ItineraryService.update_itinerary(db, itinerary_id, updates)

    return success_response(
        data={
            "itinerary_id": itinerary_id,
            "status": "rejected",
            "should_renegotiate": True,
            "version_id": version_id,
        },
        msg="方案已拒绝，可重新协商"
    )


# ==================== 用户手动调整 ====================

@router.post("/{itinerary_id}/adjust")
async def adjust_itinerary(
    itinerary_id: str,
    adjustments: dict = Body(..., description="用户手动调整内容"),
    db: Session = Depends(get_db),
):
    """
    用户手动调整行程方案

    保存用户手动修改后的 day_plans，
    验证修改后行程是否有新的冲突，
    如果有冲突则返回警告列表但允许用户强制保存。

    请求体示例:
    {
        "day_plans": [修改后的行程数组],
        "force": false  // true=强制保存（忽略冲突警告）
    }

    响应:
    {
        "code": 200,
        "data": {
            "itinerary_id": "...",
            "status": "adjusting",
            "warnings": [...],     // 新产生的冲突警告
            "has_new_conflicts": false
        }
    }
    """
    itinerary = ItineraryService.get_itinerary(db, itinerary_id)
    if itinerary is None:
        return error_response(code=404, msg="行程不存在")

    new_day_plans = adjustments.get("day_plans")
    force = adjustments.get("force", False)

    if not new_day_plans:
        return error_response(code=400, msg="缺少 day_plans 字段")

    # 验证修改后的行程
    warnings = []
    has_new_conflicts = False

    try:
        from src.models.db_models import UserRequirement
        from src.services.negotiation_core.conflict_detector import detect_conflicts
        requirement = db.query(UserRequirement).filter(
            UserRequirement.requirement_id == itinerary.requirement_id
        ).first()
        # 确保 requirement_data 是 dict 而非 Column 类型
        req_data = requirement.requirement_data if requirement is not None else None
        if isinstance(req_data, dict):
            detection = detect_conflicts(new_day_plans, req_data)
            if detection.has_conflict:
                has_new_conflicts = True
                warnings = [
                    {
                        "type": c.get("type", ""),
                        "severity": c.get("severity", "warning"),
                        "description": c.get("description", ""),
                        "day": c.get("day", 1),
                    }
                    for c in detection.conflicts
                    if c.get("severity") == "warning"
                ]
    except Exception as e:
        logger.warning(f"[手动调整] 冲突检测异常: {e}")

    if has_new_conflicts and not force:
        # 不强制保存，返回警告
        return success_response(
            data={
                "itinerary_id": itinerary_id,
                "status": "adjusting",
                "warnings": warnings,
                "has_new_conflicts": True,
                "message": "修改后的行程存在冲突，请确认或强制保存",
            },
            msg="行程存在冲突警告"
        )

    # 保存当前版本到历史记录（确保类型安全）
    raw_version_history = itinerary.version_history
    version_history = raw_version_history if isinstance(raw_version_history, list) else []
    version_id = str(uuid.uuid4())
    version_history.append({
        "version_id": version_id,
        "status": "adjusting",
        "day_plans": copy.deepcopy(new_day_plans),
        "created_at": datetime.utcnow().isoformat(),
    })

    # 更新行程
    updates = {
        "day_plans": new_day_plans,
        "status": "adjusting",
        "version_history": version_history,
    }
    ItineraryService.update_itinerary(db, itinerary_id, updates)

    return success_response(
        data={
            "itinerary_id": itinerary_id,
            "status": "adjusting",
            "version_id": version_id,
            "warnings": warnings,
            "has_new_conflicts": has_new_conflicts,
        },
        msg="行程手动调整已保存"
    )


# ==================== 历史版本管理 ====================

@router.get("/{itinerary_id}/versions")
async def get_itinerary_versions(
    itinerary_id: str,
    db: Session = Depends(get_db),
):
    """
    获取行程的所有历史版本列表

    响应示例:
    {
        "code": 200,
        "data": {
            "versions": [
                {
                    "version_id": "xxx",
                    "status": "confirmed",
                    "created_at": "2024-01-01T00:00:00",
                    "day_plans_summary": "3天行程，含6个景点"
                },
                ...
            ]
        }
    }
    """
    itinerary = ItineraryService.get_itinerary(db, itinerary_id)
    if itinerary is None:
        return error_response(code=404, msg="行程不存在")

    raw_version_history = itinerary.version_history
    version_history = raw_version_history if isinstance(raw_version_history, list) else []

    # 简化版本信息（不含完整 day_plans，仅摘要）
    versions = []
    for v in version_history:
        if not isinstance(v, dict):
            continue
        day_plans = v.get("day_plans", [])
        total_attractions = sum(
            len(p.get("attractions", [])) for p in (day_plans or []) if isinstance(p, dict)
        )
        versions.append({
            "version_id": v.get("version_id", ""),
            "status": v.get("status", ""),
            "created_at": v.get("created_at", ""),
            "reject_reason": v.get("reject_reason", ""),
            "day_count": len(day_plans) if isinstance(day_plans, list) else 0,
            "total_attractions": total_attractions,
        })

    return success_response(
        data={"versions": versions},
        msg=f"获取到 {len(versions)} 个版本"
    )


@router.get("/{itinerary_id}/versions/{version_id}")
async def get_itinerary_version_detail(
    itinerary_id: str,
    version_id: str,
    db: Session = Depends(get_db),
):
    """
    获取特定历史版本的详情

    响应:
    {
        "code": 200,
        "data": {
            "version_id": "xxx",
            "status": "confirmed",
            "day_plans": [...],
            "adjustments_summary": [...],
            "created_at": "2024-01-01T00:00:00"
        }
    }
    """
    itinerary = ItineraryService.get_itinerary(db, itinerary_id)
    if itinerary is None:
        return error_response(code=404, msg="行程不存在")

    raw_version_history = itinerary.version_history
    version_history = raw_version_history if isinstance(raw_version_history, list) else []
    for v in version_history:
        if not isinstance(v, dict):
            continue
        if v.get("version_id") == version_id:
            return success_response(
                data={
                    "version_id": version_id,
                    "status": v.get("status", ""),
                    "day_plans": v.get("day_plans", []),
                    "adjustments_summary": v.get("adjustments_summary", []),
                    "reject_reason": v.get("reject_reason", ""),
                    "created_at": v.get("created_at", ""),
                },
                msg="获取版本详情成功"
            )

    return error_response(code=404, msg="版本不存在")


# ==================== 获取方案调整摘要 ====================

@router.get("/{itinerary_id}/adjustments-summary")
async def get_adjustments_summary(
    itinerary_id: str,
    db: Session = Depends(get_db),
):
    """
    获取行程的调整摘要列表（人类可读）

    响应:
    {
        "code": 200,
        "data": {
            "adjustments_summary": [
                "故宫游览时间从09:00调整为08:30",
                ...
            ]
        }
    }
    """
    itinerary = ItineraryService.get_itinerary(db, itinerary_id)
    if itinerary is None:
        return error_response(code=404, msg="行程不存在")

    # 获取 adjustments_summary（确保是 Python list 而非 Column 类型）
    raw_summary = itinerary.adjustments_summary
    if isinstance(raw_summary, list) and len(raw_summary) > 0:
        adjustments_summary = raw_summary
    else:
        # 从 day_plans 中提取
        adjustments_summary = []
        raw_day_plans = itinerary.day_plans
        if isinstance(raw_day_plans, list) and len(raw_day_plans) > 0 and isinstance(raw_day_plans[0], dict):
            neg = raw_day_plans[0].get("negotiation", {})
            if isinstance(neg, dict):
                neg_summary = neg.get("adjustments_summary", [])
                if isinstance(neg_summary, list):
                    adjustments_summary = neg_summary

    return success_response(
        data={"adjustments_summary": adjustments_summary},
        msg=f"获取到 {len(adjustments_summary)} 条调整说明"
    )
