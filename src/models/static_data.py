"""静态数据模型定义"""
from typing import List, Optional
from pydantic import BaseModel, Field


class Attraction(BaseModel):
    """景点模型"""
    attraction_id: str
    name: str
    city_name: str
    category: str  # scenic_spot/museum/park/beach/mountain/temple
    description: Optional[str] = None
    address: Optional[str] = None
    location: Optional[dict] = None  # {lat, lng}
    opening_hours: Optional[str] = None
    ticket_price: Optional[float] = None
    recommended_duration: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    rating: Optional[float] = None
    images: List[str] = Field(default_factory=list)


class City(BaseModel):
    """城市模型"""
    city_id: str
    city_name: str
    province: Optional[str] = None
    country: str = "中国"
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class Location(BaseModel):
    """地点模型"""
    location_id: str
    name: str
    city_name: str
    category: str  # airport/train_station/bus_station/metro/shopping/food
    address: Optional[str] = None
    location: Optional[dict] = None
    description: Optional[str] = None


class StaticAttractionsResponse(BaseModel):
    """景点列表响应"""
    total: int
    cities: List[str]
    attractions: List[Attraction]


class StaticCitiesResponse(BaseModel):
    """城市列表响应"""
    total: int
    cities: List[City]


class StaticLocationsResponse(BaseModel):
    """地点库响应"""
    city_name: str
    total: int
    locations: List[Location]