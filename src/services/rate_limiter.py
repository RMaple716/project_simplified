"""
全局QPS限速器（令牌桶算法）
确保所有高德API调用的总QPS不超过上限，避免触发QPS超限错误

使用方式：
    from src.services.rate_limiter import amap_rate_limiter

    async with amap_rate_limiter:
        # 调用高德API
        ...
"""
import asyncio
import time
import logging

logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """
    令牌桶限速器

    - capacity: 桶容量（最大突发请求数）
    - fill_rate: 每秒补充的令牌数（即QPS上限）
    - 每次请求消耗1个令牌，令牌不足时等待
    """

    def __init__(self, capacity: int = 3, fill_rate: float = 3.0):
        self.capacity = float(capacity)
        self.fill_rate = fill_rate
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self):
        """补充令牌"""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
        self.last_refill = now

    async def acquire(self):
        """
        获取一个令牌
        如果令牌不足，等待直到有可用令牌
        """
        while True:
            async with self._lock:
                self._refill()
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                # 还需等待多久才能有1个令牌
                wait_time = (1.0 - self.tokens) / self.fill_rate if self.fill_rate > 0 else 0.5

            # 在锁外等待，避免阻塞其他协程获取锁
            await asyncio.sleep(min(wait_time, 0.1))

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


# 全局共享的高德API限速器
# QPS=3，桶容量=3（允许短时突发3个请求）
amap_rate_limiter = TokenBucketRateLimiter(capacity=3, fill_rate=3.0)
