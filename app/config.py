"""
Configuration management using Pydantic Settings.
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/voice_ai_db"
    
    # Application
    APP_NAME: str = "Voice AI Microservice"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # API
    API_V1_PREFIX: str = "/v1"
    MAX_PACKET_LATENCY_MS: int = 50
    
    # AI Service
    AI_SERVICE_FAILURE_RATE: float = 0.25
    AI_SERVICE_MIN_LATENCY: float = 1.0
    AI_SERVICE_MAX_LATENCY: float = 3.0
    
    # Retry Configuration
    MAX_RETRY_ATTEMPTS: int = 5
    RETRY_MIN_WAIT: int = 1
    RETRY_MAX_WAIT: int = 60
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
