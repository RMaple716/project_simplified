"""
高德地图API响应缓存服务
使用PostgreSQL数据库存储缓存数据，避免重复请求高德API导致QPS超限
"""
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session
from src.database import SessionLocal
from src.models.db_models import AmapCache

logger = logging.getLogger(__name__)

# 各API类型的缓存TTL（秒）
CACHE_TTL = {
    "direction": 86400 * 7,    # 导航路线：缓存7天（两地间交通耗时相对稳定）
    "geocode":   86400 * 30,   # 地理编码：缓存30天（地址到坐标几乎不变）
    "weather":   3600,         # 天气：缓存1小时（天气实时变化）
}


def _make_cache_key(api_type: str, params: Dict[str, Any]) -> str:
    """
    生成缓存键
    先将参数按key排序后JSON序列化再md5，保证相同参数的请求命中相同键
    """
    sorted_params = json.dumps(params, sort_keys=True, ensure_ascii=False)
    raw = f"{api_type}:{sorted_params}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def get_cached_response(api_type: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    从数据库查询缓存

    Args:
        api_type: API类型 direction/geocode/weather
        params: 请求参数字典

    Returns:
        缓存的响应数据JSON，不存在或已过期返回None
    """
    cache_key = _make_cache_key(api_type, params)
    db: Session = SessionLocal()
    try:
        row = db.query(AmapCache).filter(
            AmapCache.cache_key == cache_key,
            AmapCache.api_type == api_type,
            AmapCache.expires_at > datetime.utcnow()
        ).first()
        if row:
            logger.info(f"[AmapCache] 命中缓存 api_type={api_type} cache_key={cache_key[:16]}...")
            return row.response_data   #type:ignore
        logger.info(f"[AmapCache] 缓存未命中 api_type={api_type} cache_key={cache_key[:16]}...")
        return None
    except Exception as e:
        logger.warning(f"[AmapCache] 查询缓存异常: {e}")
        return None
    finally:
        db.close()


def set_cached_response(api_type: str, params: Dict[str, Any], response_data: Dict[str, Any]) -> None:
    """
    将API响应写入数据库缓存

    Args:
        api_type: API类型 direction/geocode/weather
        params: 请求参数字典
        response_data: API响应数据
    """
    cache_key = _make_cache_key(api_type, params)
    ttl_seconds = CACHE_TTL.get(api_type, 3600)
    expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

    db: Session = SessionLocal()
    try:
        existing = db.query(AmapCache).filter(
            AmapCache.cache_key == cache_key,
            AmapCache.api_type == api_type
        ).first()

        if existing:
            # 更新已有缓存
            existing.response_data = response_data  #type:ignore
            existing.created_at = datetime.utcnow() #type:ignore
            existing.expires_at = expires_at #type:ignore
            existing.request_params = params #type:ignore
        else:
            # 新建缓存记录
            cache = AmapCache(
                cache_key=cache_key,
                api_type=api_type,
                request_params=params,
                response_data=response_data,
                expires_at=expires_at
            )
            db.add(cache)

        db.commit()
        logger.info(f"[AmapCache] 写入缓存 api_type={api_type} cache_key={cache_key[:16]}... TTL={ttl_seconds}s")
    except Exception as e:
        logger.warning(f"[AmapCache] 写入缓存异常: {e}")
        db.rollback()
    finally:
        db.close()


def clear_expired_cache() -> int:
    """
    清理所有过期的缓存记录

    Returns:
        删除的记录数
    """
    db: Session = SessionLocal()
    try:
        result = db.query(AmapCache).filter(
            AmapCache.expires_at <= datetime.utcnow()
        ).delete()
        db.commit()
        if result:
            logger.info(f"[AmapCache] 清理过期缓存 {result} 条")
        return result
    except Exception as e:
        logger.warning(f"[AmapCache] 清理过期缓存异常: {e}")
        db.rollback()
        return 0
    finally:
        db.close()
