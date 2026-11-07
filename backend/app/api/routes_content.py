from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models import ContentChunk, ContentFile, Exercise, Job, User
from app.schemas import ChunkOut, ContentFileDetail, ContentFileOut, GenerateRequest, JobOut
from app.services.content import ContentError, process_file, store_upload
from app.services.jobs import (
    create_job,
    generate_exercises_job,
    process_content_job,
)
from app.services.queue import enqueue_task
from app.services.skills import SkillError, get_skill

router = APIRouter(prefix="/content", tags=["content"])


@router.post("/files")
def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    original_name = (file.filename or "yuklenen").strip()
    try:
        target, size, checksum = store_upload(file, original_name)
    except ContentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record = ContentFile(
        uploaded_by=user.id,
        filename=original_name,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=size,
        checksum=checksum,
        storage_path=str(target),
        status="uploaded",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    job = create_job(
        db,
        kind="process_content",
        created_by=user.id,
        payload={"file_id": record.id},
    )
    enqueue_task(background_tasks, "medspaced.process_content", process_content_job, job.id, record.id)
    return {
        "file": ContentFileOut.model_validate(record).model_dump(),
        "job": JobOut.model_validate(job).model_dump(),
    }


@router.get("/files", response_model=list[ContentFileDetail])
def list_files(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    files = list(db.scalars(select(ContentFile).order_by(ContentFile.created_at.desc())))
    chunk_counts = dict(
        db.execute(
            select(ContentChunk.file_id, func.count(ContentChunk.id)).group_by(ContentChunk.file_id)
        ).all()
    )
    exercise_counts = dict(
        db.execute(
            select(ContentChunk.file_id, func.count(Exercise.id))
            .join(Exercise, Exercise.source_chunk_id == ContentChunk.id)
            .group_by(ContentChunk.file_id)
        ).all()
    )
    return [
        {
            **ContentFileOut.model_validate(record).model_dump(),
            "chunk_count": chunk_counts.get(record.id, 0),
            "exercise_count": exercise_counts.get(record.id, 0),
        }
        for record in files
    ]


@router.get("/files/{file_id}", response_model=ContentFileDetail)
def get_file(
    file_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    record = db.get(ContentFile, file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dosya bulunamadı")
    chunk_count = int(
        db.scalar(select(func.count(ContentChunk.id)).where(ContentChunk.file_id == file_id)) or 0
    )
    exercise_count = int(
        db.scalar(
            select(func.count(Exercise.id))
            .join(ContentChunk, Exercise.source_chunk_id == ContentChunk.id)
            .where(ContentChunk.file_id == file_id)
        )
        or 0
    )
    return {
        **ContentFileOut.model_validate(record).model_dump(),
        "chunk_count": chunk_count,
        "exercise_count": exercise_count,
    }


@router.get("/files/{file_id}/chunks", response_model=list[ChunkOut])
def get_chunks(
    file_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ContentChunk]:
    if db.get(ContentFile, file_id) is None:
        raise HTTPException(status_code=404, detail="Dosya bulunamadı")
    return list(
        db.scalars(
            select(ContentChunk)
            .where(ContentChunk.file_id == file_id)
            .order_by(ContentChunk.chunk_index)
        )
    )


@router.post("/files/{file_id}/process")
def reprocess_file(
    file_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    record = db.get(ContentFile, file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dosya bulunamadı")
    job = create_job(
        db,
        kind="process_content",
        created_by=user.id,
        payload={"file_id": record.id},
    )
    enqueue_task(background_tasks, "medspaced.process_content", process_content_job, job.id, record.id)
    return {"job": JobOut.model_validate(job).model_dump()}


@router.post("/files/{file_id}/generate")
def generate(
    file_id: str,
    payload: GenerateRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    record = db.get(ContentFile, file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dosya bulunamadı")
    if record.status not in {"extracted"}:
        raise HTTPException(
            status_code=400,
            detail=f"Dosya henüz işlenmedi (durum: {record.status})",
        )
    try:
        get_skill(db, payload.skill_id)
    except SkillError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    job = create_job(
        db,
        kind="generate_exercises",
        created_by=user.id,
        payload={
            "file_id": file_id,
            "skill_id": payload.skill_id,
            "exercise_types": payload.exercise_types,
            "max_chunks": payload.max_chunks,
        },
    )
    enqueue_task(
        background_tasks,
        "medspaced.generate_exercises",
        generate_exercises_job,
        job.id,
        file_id,
        payload.skill_id,
        payload.exercise_types,
        payload.max_chunks,
    )
    return {"job": JobOut.model_validate(job).model_dump()}


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(
    job_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job bulunamadı")
    return job
