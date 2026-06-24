from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    
    # Redis & Celery
    REDIS_URL: str
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    
    # Application
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = True
    
    # Workspaces
    WORKSPACES_DIR: Path = Path("./workspaces")
    CODECOME_ROOT: Path = Path("/codecome")
    
    # Security
    SECRET_KEY: str = "change-me-in-production"
    
    class Config:
        env_file = ".env"


settings = Settings()
