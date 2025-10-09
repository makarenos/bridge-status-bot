"""
Redis client for caching and rate limiting
Uses redis-py with async support
"""

from typing import Any, Optional
import json
from redis.asyncio import Redis

from app.config import settings
from app.utils.logger import logger


class RedisClient:
    """Wrapper around Redis client with convenient methods"""

    def __init__(self):
        self.redis: Optional[Redis] = None

    async def connect(self):
        """Connect to Redis"""
        try:
            self.redis = await Redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,  # auto-decode responses to strings
            )
            # quick sanity check - is Redis alive?
            await self.redis.ping()
            logger.info("Connected to Redis successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def close(self):
        """Close the connection"""
        if self.redis:
            await self.redis.close()
            logger.info("Redis connection closed")

    async def get(self, key: str) -> Optional[str]:
        """Get value by key"""
        if not self.redis:
            return None
        return await self.redis.get(key)

    async def set(self, key: str, value: Any, ex: int = None) -> bool:
        """
        Set a value

        Args:
            key: the key
            value: value to store (auto-serializes to JSON if not a string)
            ex: TTL in seconds
        """
        if not self.redis:
            return False

        # if value isn't a string - serialize it to JSON
        if not isinstance(value, str):
            value = json.dumps(value)

        return await self.redis.set(key, value, ex=ex)

    async def delete(self, key: str) -> bool:
        """Delete a key"""
        if not self.redis:
            return False
        return await self.redis.delete(key) > 0

    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        if not self.redis:
            return False
        return await self.redis.exists(key) > 0

    async def setex(self, key: str, seconds: int, value: Any) -> bool:
        """Set value with TTL (alias for set with ex)"""
        return await self.set(key, value, ex=seconds)

    async def incr(self, key: str) -> int:
        """Increment counter"""
        if not self.redis:
            return 0
        return await self.redis.incr(key)

    async def expire(self, key: str, seconds: int) -> bool:
        """Set TTL for existing key"""
        if not self.redis:
            return False
        return await self.redis.expire(key, seconds)

    async def get_json(self, key: str) -> Optional[dict]:
        """Get and parse JSON value"""
        value = await self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON from Redis key: {key}")
                return None
        return None


# global Redis client instance
redis_client = RedisClient()