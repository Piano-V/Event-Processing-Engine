import asyncio
import logging
from app.workers.celery_app import celery
from app.database import SessionLocal
from app.events.models import Event
from sqlalchemy.future import select

logger = logging.getLogger("app.workers.tasks")

async def _async_validate_event_logs(event_id: int, payload: dict):
    """
    Perform async log analysis:
    1. Simulate deep CPU validation / AI anomaly detection.
    2. Check value thresholds.
    3. Update the event record in the PostgreSQL database with verification metadata.
    """
    logger.info(f"[Worker] Starting background validation for Event #{event_id}...")
    
    # Simulate a heavy, time-consuming analytical computation
    await asyncio.sleep(1.5)
    
    # Simple rule-based anomaly detection example
    is_anomaly = False
    if "value" in payload:
        try:
            val = float(payload["value"])
            if val > 10000.0:
                is_anomaly = True
                logger.warning(f"[Worker] ANOMALY DETECTED for Event #{event_id}: value ({val}) exceeds threshold.")
        except (ValueError, TypeError):
            pass

    # Open session to write status back to DB
    async with SessionLocal() as db:
        try:
            stmt = select(Event).where(Event.id == event_id)
            result = await db.execute(stmt)
            event = result.scalar_one_or_none()
            
            if event:
                # Update the payload with validation metadata
                updated_payload = dict(event.payload)
                updated_payload["_processing"] = {
                    "validated": True,
                    "anomaly_detected": is_anomaly,
                    "processed_by": "celery_worker_01"
                }
                event.payload = updated_payload
                # Mark dirty session and commit
                db.add(event)
                await db.commit()
                logger.info(f"[Worker] Validation completed for Event #{event_id}. Updated in DB.")
            else:
                logger.error(f"[Worker] Event #{event_id} not found in database.")
        except Exception as e:
            await db.rollback()
            logger.error(f"[Worker] Database error during Event #{event_id} validation: {e}")

@celery.task(name="app.workers.tasks.validate_event_logs")
def validate_event_logs(event_id: int, payload: dict):
    """
    Celery task wrapper. Launches asyncio loop to reuse async DB engine within Celery worker process.
    """
    try:
        asyncio.run(_async_validate_event_logs(event_id, payload))
    except Exception as e:
        logger.error(f"[Worker] Celery validate_event_logs execution failed: {e}")
