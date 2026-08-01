from celery import Celery

from legal_workbench.config import get_settings

settings = get_settings()

celery_app = Celery(
    "legal_workbench",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["legal_workbench.workers.tasks"],
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Singapore",
    enable_utc=True,
    beat_schedule={
        "publish-outbox-every-five-seconds": {
            "task": "outbox.publish",
            "schedule": 5.0,
        }
    },
)
