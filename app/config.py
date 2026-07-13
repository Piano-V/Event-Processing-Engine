from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    # Application settings
    APP_NAME: str = "Event Processing & Analytics Engine"
    
    # Database Configuration
    # Falls back to async SQLite if Postgres URL is not provided (useful for lightweight local testing)
    DATABASE_URL: str = "sqlite+aiosqlite:///./analytics.db"
    
    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Celery Configuration
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    
    # Security Settings
    SECRET_KEY: str = "super-secret-key-change-in-production-environments-93f8e12b"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    
    # Enable reading settings from environment variables and an optional .env file
    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=True)

settings = Settings()
