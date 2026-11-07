from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models import Exercise, User
from app.schemas import ExerciseOut
from app.services.review import exercise_detail

router = APIRouter(prefix="/exercises", tags=["exercises"])


@router.get("", response_model=list[ExerciseOut])
def list_exercises(
    status: str | None = None,
    exercise_type: str | None = Query(default=None, alias="type"),
    skill_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(Exercise)
    if user.role == "student":
        query = query.where(Exercise.status == "approved")
    elif status:
        query = query.where(Exercise.status == status)
    if exercise_type:
        query = query.where(Exercise.type == exercise_type)
    if skill_id:
        query = query.where(Exercise.skill_id == skill_id)
    query = query.order_by(Exercise.created_at.desc()).offset(offset).limit(limit)
    return [exercise_detail(db, exercise) for exercise in db.scalars(query)]


@router.get("/{exercise_id}", response_model=ExerciseOut)
def get_exercise(
    exercise_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Soru bulunamadı")
    if user.role == "student" and exercise.status != "approved":
        raise HTTPException(status_code=404, detail="Soru bulunamadı")
    return exercise_detail(db, exercise)
