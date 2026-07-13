import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.models import User
from app.auth.dependencies import get_current_user, get_current_user_websocket
from app.events.schemas import EventCreate, EventOut, AnalyticsSummary
from app.events.service import create_event_record, get_analytics_summary
from app.events.manager import manager
from app.workers.tasks import validate_event_logs

logger = logging.getLogger("app.events.router")

router = APIRouter(prefix="/events", tags=["events"])

@router.post("/ingest", response_model=EventOut, status_code=status.HTTP_201_CREATED)
async def ingest_event(
    event_in: EventCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Ingest a streaming event from an authenticated client.
    Persists data, updates hot-path cache, broadcasts live stream,
    and offloads long-running validation tasks to background worker queue.
    """
    # Create the event record in DB & Redis
    db_event = await create_event_record(db, event_in, user_id=current_user.id)
    
    # Offload log validation and anomaly analysis to Celery background task
    try:
        validate_event_logs.delay(db_event.id, db_event.payload)
    except Exception as e:
        logger.warning(f"Could not queue Celery task for event {db_event.id}: {e}. Celery worker might be offline.")

    return db_event

@router.get("/analytics", response_model=AnalyticsSummary)
async def get_analytics(db: AsyncSession = Depends(get_db)):
    """
    Get aggregated analytics statistics. High-performance endpoint reading from Redis hot-path cache.
    """
    summary = await get_analytics_summary(db)
    return summary

@router.websocket("/stream")
async def websocket_stream(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for real-time bi-directional streaming of events.
    Requires authentication via token query parameter.
    """
    user = await get_current_user_websocket(token, db)
    if not user:
        logger.warning("Unauthenticated WebSocket connection attempt rejected.")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket)
    try:
        # Keep connection open and listen for user messages
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
        manager.disconnect(websocket)
