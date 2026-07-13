import asyncio
import json
import logging
from typing import List
from fastapi import WebSocket
from app.cache import get_redis_client

logger = logging.getLogger("app.events.manager")

class ConnectionManager:
    def __init__(self):
        # Local cache of active websocket connections on this server instance
        self.active_connections: List[WebSocket] = []
        self.pubsub_task: asyncio.Task | None = None

    async def connect(self, websocket: WebSocket):
        """
        Accept and register a new WebSocket client.
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """
        Unregister a WebSocket client.
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Active: {len(self.active_connections)}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """
        Send a direct message to a single connected client.
        """
        try:
            await websocket.send_json(message)
        except Exception:
            self.disconnect(websocket)

    async def broadcast(self, message: dict):
        """
        Broadcast a message to all locally connected WebSocket clients.
        """
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        
        # Cleanup any broken connections
        for conn in disconnected:
            self.disconnect(conn)

    async def start_redis_listener(self):
        """
        Asynchronous listener loop. Subscribes to Redis Pub/Sub and
        broadcasts messages to all active clients. This allows horizontal scaling
        across multiple FastAPI instances since they share the same Redis message broker.
        """
        client = get_redis_client()
        pubsub = client.pubsub()
        await pubsub.subscribe("events_channel")
        logger.info("Subscribed to Redis channel 'events_channel' for real-time WebSocket broadcasting.")
        
        try:
            while True:
                # Poll with timeout to allow cooperative context switching and loop cancellations
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message:
                    try:
                        data = json.loads(message["data"])
                        await self.broadcast(data)
                    except Exception as e:
                        logger.error(f"Error parsing/broadcasting message from Redis Pub/Sub: {e}")
                # Brief sleep to yield control to the event loop
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            logger.info("Redis listener background task cancelled.")
        except Exception as e:
            logger.error(f"Unexpected error in Redis listener task: {e}")
        finally:
            await pubsub.unsubscribe("events_channel")
            await pubsub.close()

# Singleton instance
manager = ConnectionManager()
