from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_roles
from app.models import Exercise, User
from app.schemas import ExerciseOut, ReviewDecision, DifficultyCalibrationReportOut
from app.services.analytics import difficulty_calibration_report
from app.services.review import ReviewError, decide, exercise_detail, queue, review_counts

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/queue", response_model=list[ExerciseOut])
def get_queue(
    status: str = Query(default="draft,under_review"),
    skill_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> list[dict]:
    statuses = [item.strip() for item in status.split(",") if item.strip()]
    if not statuses:
        statuses = ["draft", "under_review"]
    return queue(db, statuses=statuses, skill_id=skill_id, limit=limit, offset=offset)


@router.get("/counts")
def get_counts(
    _: User = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    return review_counts(db)


@router.post("/exercises/{exercise_id}/decision", response_model=ExerciseOut)
def make_decision(
    exercise_id: str,
    payload: ReviewDecision,
    reviewer: User = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Soru bulunamadı")
    try:
        decide(db, exercise=exercise, reviewer=reviewer, action=payload.action, note=payload.note)
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return exercise_detail(db, exercise)


@router.get("/calibration", response_model=DifficultyCalibrationReportOut)
def get_calibration_report(
    _: User = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    return difficulty_calibration_report(db)
