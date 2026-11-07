from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery("medspaced", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task(
    name="medspaced.process_content",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def process_content_task(job_id: str, file_id: str) -> None:
    from app.services.jobs import process_content_job

    process_content_job(job_id, file_id)


@celery_app.task(
    name="medspaced.generate_exercises",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def generate_exercises_task(
    job_id: str,
    file_id: str,
    skill_id: str,
    exercise_types: list[str],
    max_chunks: int | None,
) -> None:
    from app.services.jobs import generate_exercises_job

    generate_exercises_job(job_id, file_id, skill_id, exercise_types, max_chunks)
