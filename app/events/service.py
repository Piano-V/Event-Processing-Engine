from datetime import datetime, timezone
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.events.models import Event
from app.events.schemas import EventCreate
from app.cache import get_redis_client, publish_event

logger = logging.getLogger("app.events.service")

async def create_event_record(db: AsyncSession, event_in: EventCreate, user_id: int | None = None) -> Event:
    """
    Asynchronously ingest and process an incoming event:
    1. Persist the event to PostgreSQL.
    2. Atomic hot-path metric increments and TTL updates in Redis.
    3. Publish to Redis Pub/Sub for live WebSocket broadcasting.
    """
    # 1. Create and persist the database record
    db_event = Event(
        event_type=event_in.event_type,
        user_id=user_id,
        payload=event_in.payload
    )
    db.add(db_event)
    await db.commit()
    await db.refresh(db_event)

    # Prepare serialization dictionary for WebSocket / PubSub
    event_payload = {
        "id": db_event.id,
        "event_type": db_event.event_type,
        "user_id": db_event.user_id,
        "timestamp": db_event.timestamp.isoformat(),
        "payload": db_event.payload
    }

    # 2. Update hot-path rolling analytics metrics in Redis
    client = get_redis_client()
    now_ts = datetime.now(timezone.utc).timestamp()
    try:
        async with client.pipeline(transaction=True) as pipe:
            # Increment total event counter (rolling/persistent)
            pipe.incrby("analytics:total_events", 1)
            # Increment type-specific count (expires in 1 hour)
            pipe.incrby(f"analytics:type:{db_event.event_type}", 1)
            pipe.expire(f"analytics:type:{db_event.event_type}", 3600)
            
            # If user is authenticated, track them in sliding window active users ZSET
            if user_id:
                pipe.zadd("analytics:active_users", {str(user_id): now_ts})
                # Clean up any users that haven't been active in the last 60 minutes
                pipe.zremrangebyscore("analytics:active_users", "-inf", now_ts - 3600)
                pipe.expire("analytics:active_users", 3600)
            await pipe.execute()
    except Exception as e:
        logger.error(f"Failed to update Redis hot-path metrics: {e}")

    # 3. Publish to Redis Pub/Sub so all connected WebSocket clients on all servers get the event
    await publish_event("events_channel", event_payload)

    return db_event

async def get_analytics_summary(db: AsyncSession) -> dict:
    """
    Get aggregated analytics statistics.
    Optimized for high-performance reading from hot Redis cache.
    Falls back gracefully to raw SQL queries on cache misses or Redis connection errors.
    """
    client = get_redis_client()
    try:
        # Check if total events key is present in cache
        total_events_val = await client.get("analytics:total_events")
        
        if total_events_val is None:
            logger.info("Cache miss: aggregating analytics from database.")
            # Cache miss: fetch total events count
            stmt_count = select(func.count(Event.id))
            res_count = await db.execute(stmt_count)
            total_events = res_count.scalar() or 0
            
            # Cache total events
            await client.set("analytics:total_events", total_events, ex=300)
            
            # Cache event type statistics
            stmt_types = select(Event.event_type, func.count(Event.id)).group_by(Event.event_type)
            res_types = await db.execute(stmt_types)
            event_types = {row[0]: row[1] for row in res_types.all()}
            for etype, count in event_types.items():
                await client.set(f"analytics:type:{etype}", count, ex=300)
        else:
            total_events = int(total_events_val)
            # Find and fetch active event types counters in Redis
            keys = await client.keys("analytics:type:*")
            event_types = {}
            for key in keys:
                etype = key.split(":")[-1]
                count = await client.get(key)
                if count:
                    event_types[etype] = int(count)

        # System metrics collection
        system_metrics = {
            "redis_connected_clients": 0,
            "redis_memory_used": "N/A",
            "db_engine": "PostgreSQL"
        }
        try:
            info = await client.info()
            system_metrics["redis_connected_clients"] = info.get("connected_clients", 0)
            system_metrics["redis_memory_used"] = info.get("used_memory_human", "N/A")
        except Exception:
            pass

        # Retrieve count of active users in the last hour using Redis Sorted Set
        now_ts = datetime.now(timezone.utc).timestamp()
        await client.zremrangebyscore("analytics:active_users", "-inf", now_ts - 3600)
        active_users_count = await client.zcard("analytics:active_users")

        return {
            "total_events": total_events,
            "event_types": event_types,
            "active_users_last_hour": active_users_count,
            "cached_at": datetime.now(timezone.utc),
            "system_metrics": system_metrics
        }

    except Exception as e:
        logger.error(f"Redis cache query failed. Falling back to DB: {e}")
        default_metrics = {"redis_connected_clients": 0, "redis_memory_used": "Offline", "db_engine": "PostgreSQL (Fallback)"}
        # Database Fallback
        try:
            stmt_count = select(func.count(Event.id))
            res_count = await db.execute(stmt_count)
            total_events = res_count.scalar() or 0

            stmt_types = select(Event.event_type, func.count(Event.id)).group_by(Event.event_type)
            res_types = await db.execute(stmt_types)
            event_types = {row[0]: row[1] for row in res_types.all()}

            return {
                "total_events": total_events,
                "event_types": event_types,
                "active_users_last_hour": 0,  # Cannot easily calculate sliding-window active users without ZSET
                "cached_at": datetime.now(timezone.utc),
                "system_metrics": default_metrics
            }
        except Exception as db_err:
            logger.critical(f"DB fallback query also failed: {db_err}")
            return {
                "total_events": 0,
                "event_types": {},
                "active_users_last_hour": 0,
                "cached_at": datetime.now(timezone.utc),
                "system_metrics": default_metrics
            }
