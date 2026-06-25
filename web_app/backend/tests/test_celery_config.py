from app.config import settings
from app.workers.celery_app import celery_app


def test_celery_hard_limit_disabled_by_default():
    assert settings.CELERY_TASK_TIME_LIMIT == 0
    assert celery_app.conf.task_time_limit in (None, 0)


def test_celery_soft_limit_disabled_by_default():
    assert settings.CELERY_TASK_SOFT_TIME_LIMIT == 0
    assert celery_app.conf.task_soft_time_limit in (None, 0)
