from celery import Celery
from app.config import settings

celery_app = Celery(
    "codecome_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=7200,  # 2 hour timeout
    task_soft_time_limit=6600,  # 110 minute soft timeout,
    include=[
        'app.workers.phase_tasks',
        'app.workers.ai_tasks',
    ]
)
