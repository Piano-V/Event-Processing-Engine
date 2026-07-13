from celery import Celery
from app.config import settings

# Initialize Celery app instance using configured Redis URLs
celery = Celery(
    "event_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

# Apply typical enterprise configurations
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Auto-load tasks file on startup
    imports=["app.workers.tasks"]
)
