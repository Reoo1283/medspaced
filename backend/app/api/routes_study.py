from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas import (
    AbilityProfileOut,
    LearningMetricsOut,
    LearningPolicyOut,
    LearningPolicyUpdate,
    PersonalizationOut,
    ReviewResult,
    ReviewSubmit,
    RotationOut,
    RotationUpdate,
    StudyItem,
    StudyStats,
)
from app.services.analytics import learning_metrics
from app.services.irt import ability_profile
from app.services.learning_policy import get_policy, update_policy
from app.services.personalization import get_personalization, optimize_personalization
from app.services.study import (
    StudyError,
    active_rotation,
    clear_rotation,
    due_items,
    set_rotation,
    study_stats,
    submit_review,
)

router = APIRouter(prefix="/study", tags=["study"])


@router.get("/due", response_model=list[StudyItem])
def get_due(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    return due_items(db, user, limit=limit)


@router.post("/reviews", response_model=ReviewResult)
def post_review(
    payload: ReviewSubmit,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return submit_review(
            db,
            user,
            exercise_id=payload.exercise_id,
            answer=payload.answer,
            rating=payload.rating,
            response_time_ms=payload.response_time_ms,
        )
    except StudyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stats", response_model=StudyStats)
def get_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return study_stats(db, user)


def _rotation_out(rotation) -> dict | None:
    if rotation is None:
        return None
    return {
        "id": rotation.id,
        "name": rotation.name,
        "starts_on": rotation.starts_on,
        "ends_on": rotation.ends_on,
        "active": True,
    }


@router.get("/rotation", response_model=RotationOut | None)
def get_rotation(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict | None:
    return _rotation_out(active_rotation(db, user.id))


@router.put("/rotation", response_model=RotationOut)
def put_rotation(
    payload: RotationUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        rotation = set_rotation(db, user, payload.model_dump())
    except StudyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _rotation_out(rotation)


@router.get("/personalization", response_model=PersonalizationOut)
def read_personalization(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return get_personalization(db, user)


@router.post("/personalization/optimize", response_model=PersonalizationOut)
def optimize(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return optimize_personalization(db, user)


@router.delete("/rotation")
def delete_rotation(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return {"cleared": clear_rotation(db, user)}


@router.get("/ability", response_model=AbilityProfileOut)
def get_ability_profile(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return ability_profile(db, user.id)


@router.get("/metrics", response_model=LearningMetricsOut)
def get_learning_metrics(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return learning_metrics(db, user)


@router.get("/settings", response_model=LearningPolicyOut)
def get_learning_settings(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return get_policy(db, user.id)


@router.put("/settings", response_model=LearningPolicyOut)
def update_learning_settings(
    payload: LearningPolicyUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return update_policy(
        db,
        user.id,
        mastery_threshold=payload.mastery_threshold,
        daily_new_card_limit=payload.daily_new_card_limit,
    )


@router.post("/personalization/rollback", response_model=PersonalizationOut)
def rollback_personalization(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.personalization import reset_personalization
    return reset_personalization(db, user)
