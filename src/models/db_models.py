"""数据库模型定义"""
from sqlalchemy import Column, String, Float, Integer, Text, JSON, DateTime, ForeignKey, Boolean, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime
from src.database import Base


class City(Base):
    """城市表"""
    __tablename__ = "cities"
    
    city_id = Column(String(50), primary_key=True, comment="城市ID")
    city_name = Column(String(100), nullable=False, index=True, comment="城市名称")
    province = Column(String(100), comment="省份")
    country = Column(String(100), default="中国", comment="国家")
    description = Column(Text, comment="城市描述")
    tags = Column(JSON, default=list, comment="标签列表")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关系
    attractions = relationship("Attraction", back_populates="city", cascade="all, delete-orphan")
    locations = relationship("Location", back_populates="city", cascade="all, delete-orphan")
    hotels = relationship("Hotel", back_populates="city", cascade="all, delete-orphan")
    restaurants = relationship("Restaurant", back_populates="city", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<City(city_id='{self.city_id}', name='{self.city_name}')>"


class Attraction(Base):
    """景点表"""
    __tablename__ = "attractions"
    
    attraction_id = Column(String(50), primary_key=True, comment="景点ID")
    name = Column(String(200), nullable=False, index=True, comment="景点名称")
    city_id = Column(String(50), ForeignKey("cities.city_id"), nullable=False, index=True, comment="城市ID")
    category = Column(String(50), nullable=False, comment="类别：scenic_spot/museum/park/beach/mountain/temple")
    description = Column(Text, comment="景点描述")
    address = Column(String(500), comment="地址")
    latitude = Column(Float, comment="纬度")
    longitude = Column(Float, comment="经度")
    opening_hours = Column(String(200), comment="开放时间")
    ticket_price = Column(Float, default=0, comment="门票价格")
    recommended_duration = Column(String(50), comment="建议游览时长（小时）")
    tags = Column(JSON, default=list, comment="标签列表")
    rating = Column(Float, comment="评分（0-5）")
    images = Column(JSON, default=list, comment="图片URL列表")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关系
    city = relationship("City", back_populates="attractions")
    
    def __repr__(self):
        return f"<Attraction(attraction_id='{self.attraction_id}', name='{self.name}')>"


class Location(Base):
    """地点表（交通枢纽、商业区等）"""
    __tablename__ = "locations"
    
    location_id = Column(String(50), primary_key=True, comment="地点ID")
    name = Column(String(200), nullable=False, index=True, comment="地点名称")
    city_id = Column(String(50), ForeignKey("cities.city_id"), nullable=False, index=True, comment="城市ID")
    category = Column(String(50), nullable=False, comment="类别：airport/train_station/bus_station/metro/shopping/food")
    address = Column(String(500), comment="地址")
    latitude = Column(Float, comment="纬度")
    longitude = Column(Float, comment="经度")
    description = Column(Text, comment="描述")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关系
    city = relationship("City", back_populates="locations")
    
    def __repr__(self):
        return f"<Location(location_id='{self.location_id}', name='{self.name}')>"


class Hotel(Base):
    """酒店表"""
    __tablename__ = "hotels"
    
    hotel_id = Column(String(50), primary_key=True, comment="酒店ID")
    name = Column(String(200), nullable=False, index=True, comment="酒店名称")
    city_id = Column(String(50), ForeignKey("cities.city_id"), nullable=False, index=True, comment="城市ID")
    address = Column(String(500), comment="地址")
    latitude = Column(Float, comment="纬度")
    longitude = Column(Float, comment="经度")
    star_rating = Column(Integer, comment="星级（1-5）")
    price_range = Column(String(50), comment="价格区间：budget/mid-range/luxury")
    min_price = Column(Float, comment="最低价格")
    max_price = Column(Float, comment="最高价格")
    amenities = Column(JSON, default=list, comment="设施列表")
    description = Column(Text, comment="描述")
    rating = Column(Float, comment="评分（0-5）")
    images = Column(JSON, default=list, comment="图片URL列表")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关系
    city = relationship("City", back_populates="hotels")
    
    def __repr__(self):
        return f"<Hotel(hotel_id='{self.hotel_id}', name='{self.name}')>"


class Restaurant(Base):
    """餐厅表"""
    __tablename__ = "restaurants"
    
    restaurant_id = Column(String(50), primary_key=True, comment="餐厅ID")
    name = Column(String(200), nullable=False, index=True, comment="餐厅名称")
    city_id = Column(String(50), ForeignKey("cities.city_id"), nullable=False, index=True, comment="城市ID")
    cuisine_type = Column(String(100), comment="菜系类型")
    address = Column(String(500), comment="地址")
    latitude = Column(Float, comment="纬度")
    longitude = Column(Float, comment="经度")
    price_level = Column(String(50), comment="价格等级：$/$$/$$$/$$$$")
    avg_price = Column(Float, comment="人均消费")
    specialties = Column(JSON, default=list, comment="特色菜品")
    description = Column(Text, comment="描述")
    rating = Column(Float, comment="评分（0-5）")
    opening_hours = Column(String(200), comment="营业时间")
    images = Column(JSON, default=list, comment="图片URL列表")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关系
    city = relationship("City", back_populates="restaurants")
    
    def __repr__(self):
        return f"<Restaurant(restaurant_id='{self.restaurant_id}', name='{self.name}')>"


class User(Base):
    """用户表"""
    __tablename__ = "users"
    
    user_id = Column(String(50), primary_key=True, comment="用户ID")
    username = Column(String(100), nullable=False, unique=True, index=True, comment="用户名")
    email = Column(String(200), unique=True, index=True, comment="邮箱")
    password_hash = Column(String(200), nullable=False, comment="密码哈希")
    avatar = Column(String(500), comment="头像URL")
    is_active = Column(Boolean, default=True, comment="是否激活")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关系
    itineraries = relationship("Itinerary", back_populates="user")
    requirements = relationship("UserRequirement", back_populates="user")
    
    def __repr__(self):
        return f"<User(user_id='{self.user_id}', username='{self.username}')>"




# ============== 业务数据表 ==============

class UserRequirement(Base):
    """用户需求表"""
    __tablename__ = "user_requirements"
    
    requirement_id = Column(String(50), primary_key=True, comment="需求ID")
    user_id = Column(String(50), ForeignKey("users.user_id"), nullable=False, index=True, comment="用户ID")
    requirement_data = Column(JSON, nullable=False, comment="需求数据JSON")
    status = Column(String(20), default="pending", comment="状态：pending/parsed/processing/completed")
    parsed_keywords = Column(JSON, comment="解析后的关键词")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关系
    user = relationship("User", back_populates="requirements")
    tasks = relationship("Task", back_populates="requirement", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<UserRequirement(requirement_id='{self.requirement_id}', status='{self.status}')>"


class Task(Base):
    """任务表"""
    __tablename__ = "tasks"
    
    task_id = Column(String(50), primary_key=True, comment="任务ID")
    batch_id = Column(String(50), nullable=False, index=True, comment="批次ID")
    requirement_id = Column(String(50), ForeignKey("user_requirements.requirement_id"), nullable=False, index=True, comment="需求ID")
    agent_type = Column(String(50), nullable=False, comment="智能体类型：attraction/accommodation/food/transport")
    parameters = Column(JSON, comment="任务参数")
    status = Column(String(20), default="pending", comment="状态：pending/running/success/failed")
    result = Column(JSON, comment="任务结果")
    error = Column(Text, comment="错误信息")
    progress = Column(Float, default=0.0, comment="进度百分比")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关系
    requirement = relationship("UserRequirement", back_populates="tasks")
    
    def __repr__(self):
        return f"<Task(task_id='{self.task_id}', agent='{self.agent_type}', status='{self.status}')>"


class Itinerary(Base):
    """行程表"""
    __tablename__ = "itineraries"
    
    itinerary_id = Column(String(50), primary_key=True, comment="行程ID")
    user_id = Column(String(50), ForeignKey("users.user_id"), nullable=False, index=True, comment="用户ID")
    requirement_id = Column(String(50), ForeignKey("user_requirements.requirement_id"), comment="关联需求ID")
    title = Column(String(200), comment="行程标题")
    day_plans = Column(JSON, nullable=False, comment="每日计划JSON数组")
    total_budget = Column(Float, comment="总预算")
    actual_cost = Column(Float, default=0, comment="实际花费")
    status = Column(String(20), default="draft", comment="状态：draft/saved/published")
    is_favorite = Column(Boolean, default=False, comment="是否收藏")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关系
    user = relationship("User", back_populates="itineraries")
    
    def __repr__(self):
        return f"<Itinerary(itinerary_id='{self.itinerary_id}', title='{self.title}')>"