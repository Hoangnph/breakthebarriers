import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "break_the_barriers",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["backend.app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_queues={
        "celery-high": {"exchange": "celery-high", "routing_key": "celery-high"},
        "celery-low":  {"exchange": "celery-low",  "routing_key": "celery-low"},
    },
    task_default_queue="celery-high",
)
