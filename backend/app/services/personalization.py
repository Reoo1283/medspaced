from __future__ import annotations

import math
from datetime import timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ReviewLog, User, UserLearningSettings, utcnow

RATING_TO_FSRS_NAME = {
    "again": "Again",
    "hard": "Hard",
    "good": "Good",
    "easy": "Easy",
}


def get_settings_row(db: Session, user_id: str) -> UserLearningSettings | None:
    return db.scalar(
        select(UserLearningSettings).where(UserLearningSettings.user_id == user_id)
    )


def _parameter_count(row: UserLearningSettings | None) -> int:
    if row is None:
        return 0
    parameters = (row.fsrs_parameters or {}).get("parameters")
    return len(parameters) if isinstance(parameters, list) else 0


def get_personalization(db: Session, user: User) -> dict:
    row = get_settings_row(db, user.id)
    if row is None:
        return {
            "desired_retention": 0.9,
            "strategy": "varsayılan",
            "reviews_analyzed": 0,
            "accuracy": None,
            "lapse_rate": None,
            "parameter_count": 0,
            "optimized_at": None,
            "model_version": 3,
            "min_reviews": settings.fsrs_optimizer_min_reviews,
            "meets_threshold": False,
            "can_rollback": True,
            "optimizer_enabled": settings.fsrs_optimizer_enabled,
        }
    parameters = row.fsrs_parameters or {}
    total = row.reviews_analyzed
    meets = total >= settings.fsrs_optimizer_min_reviews
    return {
        "desired_retention": row.desired_retention,
        "strategy": parameters.get("strategy", "heuristic"),
        "reviews_analyzed": row.reviews_analyzed,
        "accuracy": row.accuracy,
        "lapse_rate": row.lapse_rate,
        "parameter_count": _parameter_count(row),
        "optimized_at": row.optimized_at,
        "model_version": parameters.get("version", 3),
        "min_reviews": settings.fsrs_optimizer_min_reviews,
        "meets_threshold": meets,
        "can_rollback": True,
        "optimizer_enabled": settings.fsrs_optimizer_enabled,
    }


def _optimizer_available() -> bool:
    try:
        from fsrs.optimizer import Optimizer

        import pandas  # noqa: F401
        import torch  # noqa: F401
        import tqdm  # noqa: F401
    except ImportError:
        return False
    return hasattr(Optimizer, "compute_optimal_parameters")


def _to_fsrs_logs(rows: list[ReviewLog]) -> list[Any]:
    from fsrs import ReviewLog as FsrsReviewLog
    from fsrs import Rating

    ratings = {
        "again": Rating.Again,
        "hard": Rating.Hard,
        "good": Rating.Good,
        "easy": Rating.Easy,
    }
    card_ids: dict[str, int] = {}
    logs = []
    for row in sorted(rows, key=lambda item: item.reviewed_at):
        card_id = card_ids.setdefault(row.exercise_id, len(card_ids) + 1)
        reviewed_at = row.reviewed_at
        if reviewed_at.tzinfo is None:
            reviewed_at = reviewed_at.replace(tzinfo=timezone.utc)
        logs.append(
            FsrsReviewLog(
                card_id=card_id,
                rating=ratings.get(row.rating, Rating.Again),
                review_datetime=reviewed_at,
                review_duration=row.response_time_ms,
            )
        )
    return logs


def _full_parameters(rows: list[ReviewLog]) -> list[float] | None:
    try:
        from fsrs.optimizer import Optimizer
        from fsrs.scheduler import LOWER_BOUNDS_PARAMETERS, UPPER_BOUNDS_PARAMETERS

        parameters = Optimizer(_to_fsrs_logs(rows)).compute_optimal_parameters()
    except Exception:
        return None
    if not isinstance(parameters, list) or len(parameters) != len(LOWER_BOUNDS_PARAMETERS):
        return None
    for index, value in enumerate(parameters):
        if not math.isfinite(value):
            return None
        if value < LOWER_BOUNDS_PARAMETERS[index] or value > UPPER_BOUNDS_PARAMETERS[index]:
            return None
    return [round(float(value), 8) for value in parameters]


def _heuristic_retention(total: int, correct: int, lapses: int) -> float:
    accuracy = correct / total
    lapse_rate = lapses / total
    retention = 0.9
    if accuracy < 0.65 or lapse_rate > 0.3:
        retention = 0.93
    elif accuracy > 0.85 and lapse_rate < 0.1:
        retention = 0.86
    return round(max(0.75, min(0.97, retention)), 2)


def optimize_personalization(db: Session, user: User, window: int = 1000) -> dict:
    rows = list(
        db.scalars(
            select(ReviewLog)
            .where(ReviewLog.user_id == user.id)
            .order_by(ReviewLog.reviewed_at.desc())
            .limit(window)
        ).all()
    )
    if not rows:
        return get_personalization(db, user)

    total = len(rows)
    correct = sum(1 for row in rows if row.is_correct)
    lapses = sum(1 for row in rows if row.rating == "again")
    accuracy = correct / total
    lapse_rate = lapses / total
    retention = _heuristic_retention(total, correct, lapses)

    parameters: list[float] | None = None
    strategy = "heuristic"
    optimizer_error: str | None = None
    if settings.fsrs_optimizer_enabled and total >= settings.fsrs_optimizer_min_reviews:
        if _optimizer_available():
            parameters = _full_parameters(rows)
            if parameters is not None:
                strategy = "fsrs_optimizer"
            else:
                optimizer_error = "optimizer_failed"
        else:
            optimizer_error = "optimizer_unavailable"

    row = get_settings_row(db, user.id)
    if row is None:
        row = UserLearningSettings(user_id=user.id)
        db.add(row)
    row.desired_retention = retention
    row.reviews_analyzed = total
    row.accuracy = round(accuracy, 4)
    row.lapse_rate = round(lapse_rate, 4)
    row.optimized_at = utcnow()
    row.fsrs_parameters = {
        "strategy": strategy,
        "window": window,
        "version": 2,
        "parameters": parameters,
        "parameter_count": len(parameters) if parameters else 0,
        "optimizer": "fsrs.optimizer" if parameters else None,
        "fallback_reason": optimizer_error,
        "signals": {
            "accuracy": round(accuracy, 4),
            "lapse_rate": round(lapse_rate, 4),
        },
    }
    db.commit()
    return get_personalization(db, user)


def reset_personalization(db: Session, user: User) -> dict:
    row = get_settings_row(db, user.id)
    if row is None:
        return get_personalization(db, user)
    row.desired_retention = 0.9
    row.fsrs_parameters = None
    row.reviews_analyzed = 0
    row.accuracy = None
    row.lapse_rate = None
    row.optimized_at = None
    db.commit()
    return get_personalization(db, user)
