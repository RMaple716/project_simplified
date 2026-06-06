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
    def update_requirement_status(db: Session, requirement_id: str, status: str, parsed_keywords: Optional[Dict[str, Any]] = None) -> Optional[UserRequirement]:
        """更新需求状态"""
        requirement = db.query(UserRequirement).filter(
            UserRequirement.requirement_id == requirement_id
        ).first()
        
        if requirement:
            requirement.status = status  # type: ignore[attr-defined]
        if parsed_keywords:
            requirement.parsed_keywords = parsed_keywords  # type: ignore[attr-defined]
            requirement.updated_at = datetime.utcnow()  # type: ignore[attr-defined]
            db.commit()
            db.refresh(requirement)
        
        return requirement
    
    @staticmethod
    def get_user_requirements(db: Session, user_id: str, status: Optional[str] = None) -> List[UserRequirement]:
        """获取用户的所有需求"""
        query = db.query(UserRequirement).filter(UserRequirement.user_id == user_id)
        
        if status:
            query = query.filter(UserRequirement.status == status)
        
        return query.order_by(UserRequirement.created_at.desc()).all()


# ============== 任务服务 ==============

class TaskService:
    """任务管理服务"""
    
    @staticmethod
    def create_task(db: Session, batch_id: str, requirement_id: str, agent_type: str, parameters: Dict[str, Any], task_id: Optional[str] = None) -> Task:
        """创建新任务"""
        import uuid
        if task_id is None:
            task_id = str(uuid.uuid4())
        
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
        """批量创建子任务"""
        tasks = []
        for subtask in subtasks:
            task = TaskService.create_task(
                db=db,
                batch_id=batch_id,
                requirement_id=requirement_id,
                agent_type=subtask["agent_type"],
                parameters=subtask["parameters"],
                task_id=subtask["subtask_id"]  # 传递预生成的subtask_id
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
    def update_task_result(db: Session, task_id: str, status: str, result: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> Optional[Task]:
        """更新任务结果"""
        task = db.query(Task).filter(Task.task_id == task_id).first()
        
        if task:
            task.status = status  # type: ignore[attr-defined]
            task.result = result  #type: ignore[attr-defined]
            task.error = error  #type: ignore[attr-defined]
            task.updated_at = datetime.utcnow()  #type: ignore[attr-defined]
            
            # 如果是成功完成，设置进度为100%
            if status == "success":
                task.progress = 100.0  #type: ignore[attr-defined]
            
            db.commit()
            db.refresh(task)
        
        return task
    
    @staticmethod
    def calculate_batch_progress(db: Session, batch_id: str) -> Dict[str, Any]:
        """计算批次任务的总体进度"""
        tasks = TaskService.get_batch_tasks(db, batch_id)
        
        if not tasks:
            return {"status": "pending", "progress": 0.0, "completed": 0, "total": 0}
        
        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == "success")  #type: ignore[attr-defined]
        failed = sum(1 for t in tasks if t.status == "failed")  #type: ignore[attr-defined]
        
        progress = (completed / total * 100) if total > 0 else 0
        
        if failed > 0:
            status = "failed"
        elif completed == total:
            status = "success"
        else:
            status = "running"
        
        return {
            "status": status,
            "progress": round(progress, 2),
            "completed": completed,
            "failed": failed,
            "total": total
        }


# ============== 行程服务 ==============

class ItineraryService:
    """行程管理服务"""
    
    @staticmethod
    def create_itinerary(db: Session, user_id: str, day_plans: List[Dict[str, Any]], 
                        title: Optional[str] = None, total_budget: Optional[float] = None, 
                        requirement_id: Optional[str] = None) -> Itinerary:
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
    def get_user_itineraries(db: Session, user_id: str, is_favorite: Optional[bool] = None) -> List[Itinerary]:
        """获取用户的行程列表"""
        query = db.query(Itinerary).filter(Itinerary.user_id == user_id)
        
        if is_favorite is not None:
            query = query.filter(Itinerary.is_favorite == is_favorite)
        
        return query.order_by(Itinerary.created_at.desc()).all()
    
    @staticmethod
    def update_itinerary(db: Session, itinerary_id: str, updates: Dict[str, Any]) -> Optional[Itinerary]:
        """更新行程信息"""
        itinerary = db.query(Itinerary).filter(Itinerary.itinerary_id == itinerary_id).first()
        
        if itinerary:
            for key, value in updates.items():
                if hasattr(itinerary, key):
                    setattr(itinerary, key, value)
            
            itinerary.updated_at = datetime.utcnow() #type: ignore[attr-defined]
            db.commit()
            db.refresh(itinerary)
        
        return itinerary
    
    @staticmethod
    def toggle_favorite(db: Session, itinerary_id: str) -> Optional[Itinerary]:
        """切换收藏状态"""
        itinerary = db.query(Itinerary).filter(Itinerary.itinerary_id == itinerary_id).first()
        
        if itinerary:
            itinerary.is_favorite = not itinerary.is_favorite #type: ignore[attr-defined]
            itinerary.updated_at = datetime.utcnow()  #type: ignore[attr-defined]
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


# ============== 静态数据服务 ==============

class StaticDataService:
    """静态数据查询服务（景点、酒店、餐厅等）"""
    
    @staticmethod
    def get_all_cities(db: Session) -> List[City]:
        """获取所有城市"""
        return db.query(City).all()
    
    @staticmethod
    def get_city_by_id(db: Session, city_id: str) -> Optional[City]:
        """根据ID获取城市"""
        return db.query(City).filter(City.city_id == city_id).first()
    
    @staticmethod
    def get_city_by_name(db: Session, city_name: str) -> Optional[City]:
        """根据名称获取城市"""
        return db.query(City).filter(City.city_name == city_name).first()
    
    @staticmethod
    def get_attractions_by_city(db: Session, city_id: str, category: Optional[str] = None, 
                               min_rating: Optional[float] = None) -> List[Attraction]:
        """获取城市的景点列表"""
        query = db.query(Attraction).filter(Attraction.city_id == city_id)
        
        if category:
            query = query.filter(Attraction.category == category)
        
        if min_rating is not None:
            query = query.filter(Attraction.rating >= min_rating)
        
        return query.order_by(Attraction.rating.desc()).all()
    
    @staticmethod
    def search_attractions(db: Session, keyword: str, city_id: Optional[str] = None) -> List[Attraction]:
        """搜索景点（模糊匹配）"""
        query = db.query(Attraction).filter(Attraction.name.ilike(f"%{keyword}%"))
        
        if city_id:
            query = query.filter(Attraction.city_id == city_id)
        
        return query.all()
    
    @staticmethod
    def get_hotels_by_city(db: Session, city_id: str, min_star: Optional[int] = None, 
                          max_price: Optional[float] = None, price_range: Optional[str] = None) -> List[Hotel]:
    
        query = db.query(Hotel).filter(Hotel.city_id == city_id)
        
        if min_star:
            query = query.filter(Hotel.star_rating >= min_star)
        
        if max_price:
            query = query.filter(Hotel.min_price <= max_price)
        
        if price_range:
            query = query.filter(Hotel.price_range == price_range)
        
        return query.order_by(Hotel.rating.desc()).all()
    
    @staticmethod
    def get_restaurants_by_city(db: Session, city_id: str, cuisine_type: Optional[str] = None,
                               max_price: Optional[float] = None) -> List[Restaurant]:
        """获取城市的餐厅列表"""
        query = db.query(Restaurant).filter(Restaurant.city_id == city_id)
        
        if cuisine_type:
            query = query.filter(Restaurant.cuisine_type == cuisine_type)
        
        if max_price:
            query = query.filter(Restaurant.avg_price <= max_price)
        
        return query.order_by(Restaurant.rating.desc()).all()
    
    @staticmethod
    def get_locations_by_city(db: Session, city_id: str, category: Optional[str] = None) -> List[Location]:
        """获取城市的地点列表（交通枢纽等）"""
        query = db.query(Location).filter(Location.city_id == city_id)
        
        if category:
            query = query.filter(Location.category == category)
        
        return query.all()
