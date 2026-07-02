from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")

    # Database
    DATABASE_URL: str
    
    # Redis & Celery
    REDIS_URL: str
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    CELERY_TASK_TIME_LIMIT: int = 0
    CELERY_TASK_SOFT_TIME_LIMIT: int = 0
    
    # Application
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = True
    
    # Workspaces
    WORKSPACES_DIR: Path = Path("./workspaces")
    CODECOME_ROOT: Path = Path("/codecome")
    CODE_SERVER_BIND_ADDR: str = "127.0.0.1"
    CODE_SERVER_PUBLIC_BASE_URL: str = ""
    
    # Security
    SECRET_KEY: str = "change-me-in-production"
    WORKER_REGISTRATION_TOKEN: str = ""
    

settings = Settings()
