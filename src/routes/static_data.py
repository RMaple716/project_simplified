"""静态数据相关路由"""
from typing import List, Optional
from fastapi import APIRouter, Query, Depends
from sqlalchemy.orm import Session
from src.database import get_db
from src.models.response import success_response
from src.models.static_data import Attraction, City, Location, StaticAttractionsResponse, StaticCitiesResponse, StaticLocationsResponse
from src.services.database_service import StaticDataService

router = APIRouter(prefix="/api/v1/static", tags=["静态数据"])


def _make_location(lat: Optional[float], lng: Optional[float]) -> Optional[dict]:
    """将数据库中的 lat/lng 转为前端需要的 {lat, lng} 对象格式"""
    if lat is not None and lng is not None:
        return {"lat": float(lat), "lng": float(lng)}
    return None


@router.get("/attractions")
async def get_attractions(
    category: Optional[str] = None, 
    tags: Optional[List[str]] = Query(None),
    min_rating: Optional[float] = Query(None, description="最低评分"),
    db: Session = Depends(get_db)
):
    """从数据库查询景点列表"""
    # 获取所有城市以构建城市列表
    cities = StaticDataService.get_all_cities(db)
    city_names = [city.city_name for city in cities]
    
    # 如果指定了类别或评分过滤，需要逐个查询
    if category or min_rating:
        all_attractions = []
        for city in cities:
            attractions = StaticDataService.get_attractions_by_city(
                db, 
                city.city_id, 
                category=category,
                min_rating=min_rating
            )
            all_attractions.extend(attractions)
    else:
        # 获取所有景点
        all_attractions = []
        for city in cities:
            attractions = StaticDataService.get_attractions_by_city(db, city.city_id)
            all_attractions.extend(attractions)
    
    attraction_list = [{
        "attraction_id": attr.attraction_id,
        "name": attr.name,
        "city_name": attr.city.city_name if attr.city else "",
        "category": attr.category,
        "description": attr.description,
        "address": attr.address,
        "location": _make_location(attr.latitude, attr.longitude),
        "opening_hours": attr.opening_hours,
        "ticket_price": attr.ticket_price,
        "recommended_duration": attr.recommended_duration,
        "tags": attr.tags or [],
        "rating": attr.rating,
        "images": attr.images or []
    } for attr in all_attractions]
    
    return success_response(
        data=StaticAttractionsResponse(
            total=len(attraction_list), 
            cities=city_names, 
            attractions=[Attraction(**a) for a in attraction_list]
        ).model_dump(), 
        msg="获取成功"
    )


@router.get("/attractions/{city_name}")
async def get_city_attractions(city_name: str, db: Session = Depends(get_db)):
    """从数据库查询指定城市的景点"""
    # 先找到城市
    city = StaticDataService.get_city_by_name(db, city_name)
    
    if not city:
        return success_response(
            data={"city_name": city_name, "total": 0, "attractions": []}, 
            msg="城市不存在"
        )
    
    # 查询该城市的所有景点
    attractions = StaticDataService.get_attractions_by_city(db, city.city_id)
    
    attraction_list = [{
        "attraction_id": attr.attraction_id,
        "name": attr.name,
        "city_name": city_name,
        "category": attr.category,
        "description": attr.description,
        "address": attr.address,
        "location": _make_location(attr.latitude, attr.longitude),
        "opening_hours": attr.opening_hours,
        "ticket_price": attr.ticket_price,
        "recommended_duration": attr.recommended_duration,
        "tags": attr.tags or [],
        "rating": attr.rating,
        "images": attr.images or []
    } for attr in attractions]
    
    return success_response(
        data={"city_name": city_name, "total": len(attraction_list), "attractions": attraction_list}, 
        msg="获取成功"
    )


@router.get("/cities")
async def get_cities(db: Session = Depends(get_db)):
    """从数据库查询城市列表"""
    cities = StaticDataService.get_all_cities(db)
    
    city_list = [{
        "city_id": city.city_id,
        "city_name": city.city_name,
        "province": city.province,
        "country": city.country,
        "description": city.description,
        "tags": city.tags or []
    } for city in cities]
    
    return success_response(
        data=StaticCitiesResponse(total=len(city_list), cities=[City(**c) for c in city_list]).model_dump(), 
        msg="获取成功"
    )


@router.get("/locations/{city_name}")
async def get_city_locations(city_name: str, category: Optional[str] = None, db: Session = Depends(get_db)):
    """从数据库查询指定城市的地点库（交通枢纽等）"""
    city = StaticDataService.get_city_by_name(db, city_name)
    
    if not city:
        return success_response(
            data={"city_name": city_name, "total": 0, "locations": []}, 
            msg="城市不存在"
        )
    
    locations = StaticDataService.get_locations_by_city(db, city.city_id, category)
    
    location_list = [{
        "location_id": loc.location_id,
        "name": loc.name,
        "city_name": city_name,
        "category": loc.category,
        "address": loc.address,
        "location": _make_location(loc.latitude, loc.longitude),
        "description": loc.description
    } for loc in locations]
    
    return success_response(
        data={"city_name": city_name, "total": len(location_list), "locations": location_list},
        msg="获取成功"
    )


@router.get("/hotels/{city_name}")
async def get_city_hotels(
    city_name: str, 
    min_star: Optional[int] = Query(None, description="最低星级"),
    max_price: Optional[float] = Query(None, description="最高价格"),
    price_range: Optional[str] = Query(None, description="价格区间：budget/mid-range/luxury"),
    db: Session = Depends(get_db)
):
    """从数据库查询指定城市的酒店"""
    city = StaticDataService.get_city_by_name(db, city_name)
    
    if not city:
        return success_response(
            data={"city_name": city_name, "total": 0, "hotels": []}, 
            msg="城市不存在"
        )
    
    hotels = StaticDataService.get_hotels_by_city(
        db, 
        city.city_id, 
        min_star=min_star,
        max_price=max_price,
        price_range=price_range
    )
    
    hotel_list = [{
        "hotel_id": hotel.hotel_id,
        "name": hotel.name,
        "city_name": city_name,
        "location": _make_location(hotel.latitude, hotel.longitude),
        "address": hotel.address,
        "star_rating": hotel.star_rating,
        "price_range": hotel.price_range,
        "min_price": hotel.min_price,
        "max_price": hotel.max_price,
        "price_per_night": hotel.min_price if hotel.min_price else 0,
        "amenities": hotel.amenities or [],
        "description": hotel.description,
        "rating": hotel.rating,
        "images": hotel.images or []
    } for hotel in hotels]
    
    return success_response(
        data={"city_name": city_name, "total": len(hotel_list), "hotels": hotel_list},
        msg="获取成功"
    )


@router.get("/restaurants/{city_name}")
async def get_city_restaurants(
    city_name: str,
    cuisine_type: Optional[str] = Query(None, description="菜系类型"),
    max_price: Optional[float] = Query(None, description="最高人均消费"),
    db: Session = Depends(get_db)
):
    """从数据库查询指定城市的餐厅"""
    city = StaticDataService.get_city_by_name(db, city_name)
    
    if not city:
        return success_response(
            data={"city_name": city_name, "total": 0, "restaurants": []}, 
            msg="城市不存在"
        )
    
    restaurants = StaticDataService.get_restaurants_by_city(
        db,
        city.city_id,
        cuisine_type=cuisine_type,
        max_price=max_price
    )
    
    restaurant_list = [{
        "restaurant_id": rest.restaurant_id,
        "name": rest.name,
        "city_name": city_name,
        "location": _make_location(rest.latitude, rest.longitude),
        "cuisine_type": rest.cuisine_type,
        "address": rest.address,
        "price_level": rest.price_level,
        "avg_price": rest.avg_price,
        "specialties": rest.specialties or [],
        "description": rest.description,
        "rating": rest.rating,
        "opening_hours": rest.opening_hours,
        "images": rest.images or []
    } for rest in restaurants]
    
    return success_response(
        data={"city_name": city_name, "total": len(restaurant_list), "restaurants": restaurant_list},
        msg="获取成功"
    )