from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import UserLearningSettings

DEFAULT_MASTERY_THRESHOLD = 70.0
DEFAULT_DAILY_NEW_CARD_LIMIT = 20


def _get_settings_row(db: Session, user_id: str) -> UserLearningSettings | None:
    return db.query(UserLearningSettings).filter_by(user_id=user_id).first()


def get_policy(db: Session, user_id: str) -> dict:
    row = _get_settings_row(db, user_id)
    if row is None:
        return {
            "mastery_threshold": DEFAULT_MASTERY_THRESHOLD,
            "daily_new_card_limit": DEFAULT_DAILY_NEW_CARD_LIMIT,
        }
    return {
        "mastery_threshold": float(row.mastery_threshold or DEFAULT_MASTERY_THRESHOLD),
        "daily_new_card_limit": int(row.daily_new_card_limit or DEFAULT_DAILY_NEW_CARD_LIMIT),
    }


def update_policy(
    db: Session,
    user_id: str,
    *,
    mastery_threshold: float | None = None,
    daily_new_card_limit: int | None = None,
) -> dict:
    row = _get_settings_row(db, user_id)
    if row is None:
        row = UserLearningSettings(user_id=user_id)
        db.add(row)
        db.flush()
    if mastery_threshold is not None:
        row.mastery_threshold = max(50.0, min(95.0, mastery_threshold))
    if daily_new_card_limit is not None:
        row.daily_new_card_limit = max(5, min(100, daily_new_card_limit))
    db.commit()
    db.refresh(row)
    return get_policy(db, user_id)