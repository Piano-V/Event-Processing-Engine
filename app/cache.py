import json
import logging
from typing import Any, Optional
import redis.asyncio as aioredis
from app.config import settings

logger = logging.getLogger("app.cache")

# Redis connection pool for high-concurrency re-use
redis_pool = aioredis.ConnectionPool.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
    max_connections=50  # production-like pool limit
)

def get_redis_client() -> aioredis.Redis:
    """
    Return a Redis client from the shared connection pool.
    """
    return aioredis.Redis(connection_pool=redis_pool)

async def cache_get(key: str) -> Optional[Any]:
    """
    Get a deserialized JSON value from Redis.
    """
    client = get_redis_client()
    try:
        data = await client.get(key)
        if data:
            return json.loads(data)
    except Exception as e:
        logger.error(f"Redis cache_get error for key {key}: {e}")
    return None

async def cache_set(key: str, value: Any, ttl: int = 300) -> bool:
    """
    Set a serialized JSON value in Redis with a TTL.
    """
    client = get_redis_client()
    try:
        await client.set(key, json.dumps(value), ex=ttl)
        return True
    except Exception as e:
        logger.error(f"Redis cache_set error for key {key}: {e}")
        return False

async def increment_rolling_counter(key: str, increment: int = 1, ttl: int = 3600) -> int:
    """
    Increments a key and resets/updates its TTL. Useful for rolling time windows.
    """
    client = get_redis_client()
    try:
        # Run incr and expire in pipeline for atomicity and network efficiency
        async with client.pipeline(transaction=True) as pipe:
            pipe.incrby(key, increment)
            pipe.expire(key, ttl)
            res = await pipe.execute()
            return res[0]
    except Exception as e:
        logger.error(f"Redis increment_rolling_counter error for key {key}: {e}")
        return 0

async def publish_event(channel: str, message: Any) -> int:
    """
    Publishes a message to a Redis Pub/Sub channel.
    """
    client = get_redis_client()
    try:
        payload = json.dumps(message) if not isinstance(message, str) else message
        return await client.publish(channel, payload)
    except Exception as e:
        logger.error(f"Redis publish_event error on channel {channel}: {e}")
        return 0
