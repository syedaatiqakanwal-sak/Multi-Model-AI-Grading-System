from celery import Celery
from app.config import settings

celery_app = Celery(
    "gradepro_orchestrator",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "workers.grading",
        "workers.training",
        "app.tasks.analysis_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_routes={
        "workers.grading.*": {"queue": "grading_queue"},
        "workers.training.*": {"queue": "training_queue"},
        "workers.pdf.*": {"queue": "pdf_queue"},
        "app.tasks.analysis_tasks.*": {"queue": "analysis_queue"},
    },
)
