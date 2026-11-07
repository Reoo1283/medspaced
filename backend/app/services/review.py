from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ContentChunk,
    ContentFile,
    Exercise,
    ExerciseReviewEvent,
    SkillNode,
    User,
    utcnow,
)


class ReviewError(Exception):
    pass


ALLOWED_TRANSITIONS = {
    "draft": {"submit", "approve", "reject"},
    "under_review": {"approve", "reject"},
}


def _source(db: Session, exercise: Exercise) -> dict | None:
    chunk = db.get(ContentChunk, exercise.source_chunk_id)
    if chunk is None:
        return None
    content_file = db.get(ContentFile, chunk.file_id)
    return {
        "chunk_id": chunk.id,
        "file_id": chunk.file_id,
        "filename": content_file.filename if content_file else "",
        "section_title": chunk.section_title,
        "page_number": chunk.page_number,
        "snippet": chunk.raw_text[:1200],
    }


def exercise_detail(db: Session, exercise: Exercise) -> dict:
    skill = db.get(SkillNode, exercise.skill_id) if exercise.skill_id else None
    return {
        "id": exercise.id,
        "skill_id": exercise.skill_id,
        "skill_title": skill.title if skill else None,
        "concept_id": exercise.concept_id,
        "type": exercise.type,
        "status": exercise.status,
        "payload": exercise.payload,
        "difficulty": exercise.difficulty,
        "source": _source(db, exercise),
        "generation_meta": exercise.generation_meta,
        "reviewed_at": exercise.reviewed_at,
        "rejection_reason": exercise.rejection_reason,
        "created_at": exercise.created_at,
    }


def queue(
    db: Session,
    *,
    statuses: list[str] | None = None,
    skill_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    query = select(Exercise).where(Exercise.status.in_(statuses or ["draft", "under_review"]))
    if skill_id:
        query = query.where(Exercise.skill_id == skill_id)
    query = query.order_by(Exercise.created_at.desc()).offset(offset).limit(limit)
    return [exercise_detail(db, exercise) for exercise in db.scalars(query)]


def decide(
    db: Session,
    *,
    exercise: Exercise,
    reviewer: User,
    action: str,
    note: str | None,
) -> Exercise:
    allowed = ALLOWED_TRANSITIONS.get(exercise.status, set())
    if action not in allowed:
        raise ReviewError(
            f"'{exercise.status}' durumundaki soru için '{action}' işlemi yapılamaz"
        )
    if action == "reject" and not (note or "").strip():
        raise ReviewError("Red işlemi için gerekçe zorunludur")

    if action == "submit":
        exercise.status = "under_review"
    elif action == "approve":
        exercise.status = "approved"
        exercise.reviewed_by = reviewer.id
        exercise.reviewed_at = utcnow()
        exercise.rejection_reason = None
        # Record the difficulty at the time of approval for calibration reporting
        exercise.difficulty_at_approval = exercise.difficulty
    elif action == "reject":
        exercise.status = "rejected"
        exercise.reviewed_by = reviewer.id
        exercise.reviewed_at = utcnow()
        exercise.rejection_reason = note.strip()

    db.add(
        ExerciseReviewEvent(
            exercise_id=exercise.id,
            reviewer_id=reviewer.id,
            action=action,
            note=note,
            created_at=utcnow(),
        )
    )
    db.commit()
    db.refresh(exercise)
    return exercise


def review_counts(db: Session) -> dict:
    counts = {"draft": 0, "under_review": 0, "approved": 0, "rejected": 0}
    rows = db.execute(
        select(Exercise.status, Exercise.id).order_by(Exercise.status)
    ).all()
    for status, _ in rows:
        counts[status] = counts.get(status, 0) + 1
    return counts
