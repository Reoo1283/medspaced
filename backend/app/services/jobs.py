from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import ContentFile, Job, utcnow
from app.services.content import process_file
from app.services.generation import generate_for_file


def create_job(db: Session, *, kind: str, created_by: str | None, payload: dict) -> Job:
    job = Job(
        kind=kind,
        status="queued",
        progress=0,
        created_by=created_by,
        payload=payload,
        created_at=utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def process_content_job(job_id: str, file_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        content_file = db.get(ContentFile, file_id)
        if job is None or content_file is None or job.status == "completed":
            return
        job.status = "running"
        job.started_at = utcnow()
        job.progress = 10
        job.message = "Metin çıkarılıyor ve chunk'lanıyor"
        db.commit()

        result = process_file(db, content_file)
        job = db.get(Job, job_id)
        job.status = "completed"
        job.progress = 100
        job.message = "İçerik işleme tamamlandı"
        job.result = result
        job.finished_at = utcnow()
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(Job, job_id)
        content_file = db.get(ContentFile, file_id)
        if job is not None:
            job.status = "failed"
            job.message = str(exc)[:2000]
            job.finished_at = utcnow()
        if content_file is not None:
            content_file.status = "failed"
            content_file.error_message = str(exc)[:2000]
        db.commit()
        if settings.job_queue_backend == "celery":
            raise
    finally:
        db.close()


def generate_exercises_job(
    job_id: str,
    file_id: str,
    skill_id: str,
    exercise_types: list[str],
    max_chunks: int | None,
) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None or job.status == "completed":
            return
        job.status = "running"
        job.started_at = utcnow()
        job.progress = 5
        job.message = "Kavramlar ve sorular üretiliyor"
        db.commit()

        def progress(percent: int, message: str) -> None:
            current = db.get(Job, job_id)
            if current is not None:
                current.progress = max(5, min(99, percent))
                current.message = message
                db.commit()

        result = generate_for_file(
            db,
            file_id=file_id,
            skill_id=skill_id,
            exercise_types=exercise_types,
            max_chunks=max_chunks,
            progress=progress,
        )
        job = db.get(Job, job_id)
        job.status = "completed"
        job.progress = 100
        job.message = "Üretim tamamlandı; sorular inceleme kuyruğunda"
        job.result = result
        job.finished_at = utcnow()
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(Job, job_id)
        if job is not None:
            job.status = "failed"
            job.message = str(exc)[:2000]
            job.finished_at = utcnow()
        db.commit()
        if settings.job_queue_backend == "celery":
            raise
    finally:
        db.close()
