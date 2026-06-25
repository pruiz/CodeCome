from celery import Celery
from app.config import settings

celery_app = Celery(
    "codecome_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

config = dict(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    include=[
        'app.workers.phase_tasks',
        'app.workers.ai_tasks',
    ]
)

if settings.CELERY_TASK_TIME_LIMIT > 0:
    config["task_time_limit"] = settings.CELERY_TASK_TIME_LIMIT
if settings.CELERY_TASK_SOFT_TIME_LIMIT > 0:
    config["task_soft_time_limit"] = settings.CELERY_TASK_SOFT_TIME_LIMIT

celery_app.conf.update(**config)
