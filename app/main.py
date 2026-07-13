import asyncio
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.config import settings
from app.database import engine, Base
from app.auth.router import router as auth_router
from app.events.router import router as events_router
from app.events.manager import manager
from app.cache import redis_pool

# Configure application logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("app.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan manager to orchestrate startup and shutdown tasks.
    Creates DB tables, runs the real-time WebSocket Redis subscriber, and closes connection pools.
    """
    logger.info("Starting up API services...")
    
    # 1. Automagic database tables setup for plug-and-play execution
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize database tables: {e}")

    # 2. Launch background Redis listener task for scaling WebSockets
    manager.pubsub_task = asyncio.create_task(manager.start_redis_listener())
    logger.info("WebSocket Redis Pub/Sub listener worker started.")

    yield

    logger.info("Shutting down API services...")

    # 3. Cancel the background Redis listener task
    if manager.pubsub_task:
        manager.pubsub_task.cancel()
        try:
            await manager.pubsub_task
        except asyncio.CancelledError:
            logger.info("WebSocket Redis listener worker exited cleanly.")

    # 4. Disconnect Redis pool
    await redis_pool.disconnect()
    logger.info("Redis connection pool closed. Shutdown complete.")

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="High-Concurrency Real-Time Analytics & Event Processing Engine",
    lifespan=lifespan
)

# Setup CORS to allow cross-origin API and WebSocket testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API endpoints
app.include_router(auth_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """
    Serve the real-time Tailwind-based monitoring dashboard.
    """
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as file:
            return file.read()
    return """
    <html>
        <head><title>Error</title></head>
        <body style="font-family:sans-serif; text-align:center; padding-top:50px;">
            <h1>Dashboard Template Not Found</h1>
            <p>Please ensure app/templates/index.html is created.</p>
        </body>
    </html>
    """
