"""
数据库服务层 - 封装所有数据库操作
提供需求、任务、行程等业务数据的CRUD操作
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime
from src.models.db_models import (
    UserRequirement, Task, Itinerary,
    City, Attraction, Hotel, Restaurant, Location
)


# ============== 用户需求服务 ==============

class RequirementService:
    """用户需求管理服务"""

    @staticmethod
    def create_requirement(db: Session, user_id: str, requirement_data: Dict[str, Any]) -> UserRequirement:
        """创建新的用户需求"""
        requirement_id = f"req_{datetime.now().strftime('%Y%m%d%H%M%S')}_{id(requirement_data) % 10000}"

        requirement = UserRequirement(
            requirement_id=requirement_id,
            user_id=user_id,
            requirement_data=requirement_data,
            status="pending"
        )

        db.add(requirement)
        db.commit()
        db.refresh(requirement)
        return requirement

    @staticmethod
    def get_requirement(db: Session, requirement_id: str) -> Optional[UserRequirement]:
        """获取需求详情"""
        return db.query(UserRequirement).filter(
            UserRequirement.requirement_id == requirement_id
        ).first()

    @staticmethod
    def update_requirement_status(db: Session, requirement_id: str, status: str, parsed_keywords: Dict[str, Any] = None) -> Optional[UserRequirement]:
        """更新需求状态"""
        requirement = db.query(UserRequirement).filter(
            UserRequirement.requirement_id == requirement_id
        ).first()

        if requirement:
            requirement.status = status
            if parsed_keywords:
                requirement.parsed_keywords = parsed_keywords
            db.commit()
            db.refresh(requirement)

        return requirement


# ============== 任务服务 ==============

class TaskService:
    """任务管理服务"""

    @staticmethod
    def create_task(db: Session, batch_id: str, requirement_id: str, agent_type: str, parameters: Dict[str, Any]) -> Task:
        """创建新任务"""
        task_id = f"task_{datetime.now().strftime('%Y%m%d%H%M%S')}_{id(parameters) % 10000}"

        task = Task(
            task_id=task_id,
            batch_id=batch_id,
            requirement_id=requirement_id,
            agent_type=agent_type,
            parameters=parameters,
            status="pending",
            progress=0.0
        )

        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    @staticmethod
    def create_batch_tasks(db: Session, batch_id: str, requirement_id: str, subtasks: List[Dict[str, Any]]) -> List[Task]:
        """批量创建任务"""
        tasks = []
        for subtask in subtasks:
            task = TaskService.create_task(
                db=db,
                batch_id=batch_id,
                requirement_id=requirement_id,
                agent_type=subtask["agent_type"],
                parameters=subtask["parameters"]
            )
            tasks.append(task)

        return tasks

    @staticmethod
    def get_task(db: Session, task_id: str) -> Optional[Task]:
        """获取任务详情"""
        return db.query(Task).filter(Task.task_id == task_id).first()

    @staticmethod
    def get_batch_tasks(db: Session, batch_id: str) -> List[Task]:
        """获取批次的所有任务"""
        return db.query(Task).filter(Task.batch_id == batch_id).all()

    @staticmethod
    def update_task_result(db: Session, task_id: str, status: str, result: Dict[str, Any] = None, error: str = None) -> Optional[Task]:
        """更新任务结果"""
        task = db.query(Task).filter(Task.task_id == task_id).first()

        if task:
            task.status = status
            task.result = result
            task.error = error
            task.updated_at = datetime.utcnow()

            # 如果是成功完成，设置进度为100%
            if status == "success":
                task.progress = 100.0

            db.commit()
            db.refresh(task)

        return task

    @staticmethod
    def calculate_batch_progress(db: Session, batch_id: str) -> Dict[str, Any]:
        """计算批次任务的总体进度"""
        tasks = TaskService.get_batch_tasks(db, batch_id)

        if not tasks:
            return {"status": "pending", "progress": 0.0, "completed": 0, "total": 0}

        completed = sum(1 for task in tasks if task.status == "success")
        total = len(tasks)
        progress = (completed / total) * 100 if total > 0 else 0

        # 确定批次状态
        if completed == total:
            status = "completed"
        elif any(task.status == "failed" for task in tasks):
            status = "failed"
        elif any(task.status == "running" for task in tasks):
            status = "running"
        else:
            status = "pending"

        return {
            "status": status,
            "progress": progress,
            "completed": completed,
            "total": total
        }


# ============== 行程服务 ==============

class ItineraryService:
    """行程管理服务"""

    @staticmethod
    def create_itinerary(db: Session, user_id: str, requirement_id: str, day_plans: List[Dict[str, Any]],
                        title: str = None, total_budget: float = None) -> Itinerary:
        """创建新行程"""
        import uuid
        itinerary_id = str(uuid.uuid4())

        itinerary = Itinerary(
            itinerary_id=itinerary_id,
            user_id=user_id,
            requirement_id=requirement_id,
            title=title or f"行程_{datetime.now().strftime('%Y%m%d')}",
            day_plans=day_plans,
            total_budget=total_budget,
            status="draft",
            is_favorite=False
        )

        db.add(itinerary)
        db.commit()
        db.refresh(itinerary)
        return itinerary

    @staticmethod
    def get_itinerary(db: Session, itinerary_id: str) -> Optional[Itinerary]:
        """获取行程详情"""
        return db.query(Itinerary).filter(Itinerary.itinerary_id == itinerary_id).first()

    @staticmethod
    def get_user_itineraries(db: Session, user_id: str, is_favorite: bool = None) -> List[Itinerary]:
        """获取用户的行程列表"""
        query = db.query(Itinerary).filter(Itinerary.user_id == user_id)

        if is_favorite is not None:
            query = query.filter(Itinerary.is_favorite == is_favorite)

        return query.order_by(Itinerary.created_at.desc()).all()

    @staticmethod
    def update_itinerary(db: Session, itinerary_id: str, updates: Dict[str, Any]) -> Optional[Itinerary]:
        """更新行程信息"""
        try:
            print(f"[update_itinerary] 开始更新: itinerary_id={itinerary_id}, updates={updates}")
            itinerary = db.query(Itinerary).filter(Itinerary.itinerary_id == itinerary_id).first()

            if not itinerary:
                print(f"[update_itinerary] 行程不存在: {itinerary_id}")
                return None

            # 更新各个字段
            for key, value in updates.items():
                if hasattr(itinerary, key):
                    print(f"[update_itinerary] 更新字段: {key}={value}")
                    setattr(itinerary, key, value)

            itinerary.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(itinerary)
            print(f"[update_itinerary] 更新成功: {itinerary.itinerary_id}")
            return itinerary
        except Exception as e:
            db.rollback()
            print(f"[update_itinerary] 更新失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def toggle_favorite(db: Session, itinerary_id: str) -> Optional[Itinerary]:
        """切换行程收藏状态"""
        itinerary = db.query(Itinerary).filter(Itinerary.itinerary_id == itinerary_id).first()

        if itinerary:
            itinerary.is_favorite = not itinerary.is_favorite
            db.commit()
            db.refresh(itinerary)

        return itinerary

    @staticmethod
    def delete_itinerary(db: Session, itinerary_id: str) -> bool:
        """删除行程"""
        itinerary = db.query(Itinerary).filter(Itinerary.itinerary_id == itinerary_id).first()

        if itinerary:
            db.delete(itinerary)
            db.commit()
            return True

        return False
