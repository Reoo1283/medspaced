from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fsrs import Card, Rating, Scheduler
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import UserCardState, utcnow

RATING_TO_FSRS = {
    "again": Rating.Again,
    "hard": Rating.Hard,
    "good": Rating.Good,
    "easy": Rating.Easy,
}
SM2_QUALITY = {"again": 1, "hard": 3, "good": 4, "easy": 5}

_schedulers: dict[tuple[float, tuple[float, ...] | None], Scheduler] = {}


def _scheduler_for(
    desired_retention: float,
    parameters: list[float] | None = None,
) -> Scheduler:
    key = (
        round(desired_retention, 2),
        tuple(round(value, 8) for value in parameters) if parameters else None,
    )
    scheduler = _schedulers.get(key)
    if scheduler is None:
        scheduler = Scheduler(
            parameters=parameters or Scheduler().parameters,
            desired_retention=key[0],
        )
        _schedulers[key] = scheduler
    return scheduler


def _learning_preferences(
    db: Session, user_id: str
) -> tuple[float, list[float] | None]:
    from app.models import UserLearningSettings

    settings_row = db.scalar(
        select(UserLearningSettings).where(UserLearningSettings.user_id == user_id)
    )
    if settings_row is None:
        return 0.9, None
    retention = max(0.75, min(0.97, float(settings_row.desired_retention or 0.9)))
    stored = (settings_row.fsrs_parameters or {}).get("parameters")
    parameters = None
    if isinstance(stored, list) and len(stored) == len(Scheduler().parameters):
        parameters = [float(value) for value in stored]
    return retention, parameters


def get_or_create_state(db: Session, user_id: str, exercise_id: str) -> UserCardState:
    state = db.scalar(
        select(UserCardState).where(
            UserCardState.user_id == user_id,
            UserCardState.exercise_id == exercise_id,
        )
    )
    if state is None:
        state = UserCardState(
            user_id=user_id,
            exercise_id=exercise_id,
            scheduler=settings.srs_algorithm,
            ease_factor=2.5,
            interval_days=0,
            repetitions=0,
            state="new",
            review_count=0,
            lapse_count=0,
        )
        db.add(state)
        db.flush()
    return state


def apply_review(
    db: Session,
    state: UserCardState,
    rating: str,
    now: datetime | None = None,
) -> UserCardState:
    now = now or utcnow()
    if state.scheduler == "fsrs":
        _apply_fsrs(state, rating, now, db=db)
    else:
        _apply_sm2(state, rating, now)
    state.review_count += 1
    state.last_review_at = now
    state.retrievability = compute_retrievability(state, now)
    db.flush()
    return state


def _apply_sm2(state: UserCardState, rating: str, now: datetime) -> None:
    quality = SM2_QUALITY.get(rating, 1)
    if quality < 3:
        state.repetitions = 0
        state.interval_days = 1
        state.lapse_count += 1
        state.state = "relearning"
    else:
        if state.repetitions == 0:
            interval = 1
        elif state.repetitions == 1:
            interval = 6
        else:
            interval = max(1, round(state.interval_days * state.ease_factor))
        state.repetitions += 1
        state.interval_days = interval
        state.state = "review"
    state.ease_factor = max(
        1.3,
        state.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)),
    )
    state.due_at = now + timedelta(days=state.interval_days)
    state.difficulty = round(1.0 / state.ease_factor, 4)


def _apply_fsrs(
    state: UserCardState,
    rating: str,
    now: datetime,
    db: Session | None = None,
) -> None:
    card = None
    if state.fsrs_card:
        try:
            card = Card.from_dict(state.fsrs_card)
        except Exception:
            card = None
    if card is None:
        card = Card()
    if db is not None:
        retention, parameters = _learning_preferences(db, state.user_id)
    else:
        retention, parameters = 0.9, None
    scheduler = _scheduler_for(retention, parameters)
    new_card, _review_log = scheduler.review_card(card, RATING_TO_FSRS.get(rating, Rating.Again))
    state.fsrs_card = new_card.to_dict()
    state.stability = new_card.stability
    state.difficulty = new_card.difficulty
    due = new_card.due
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    state.due_at = due.astimezone(timezone.utc).replace(tzinfo=None)
    state.state = new_card.state.name.lower()
    state.interval_days = max(0, (state.due_at - now).days)
    if rating == "again":
        state.lapse_count += 1


def compute_retrievability(state: UserCardState, now: datetime | None = None) -> float:
    now = now or utcnow()
    if state.last_review_at is None:
        return 0.0
    elapsed_days = max(0.0, (now - state.last_review_at).total_seconds() / 86400)
    if state.scheduler == "fsrs" and state.stability and state.stability > 0:
        return round((1 + elapsed_days / (9 * state.stability)) ** -1, 4)
    if state.interval_days and state.interval_days > 0:
        return round(0.9 ** (elapsed_days / state.interval_days), 4)
    return 0.0


def state_snapshot(state: UserCardState) -> dict:
    return {
        "scheduler": state.scheduler,
        "difficulty": state.difficulty,
        "stability": state.stability,
        "ease_factor": state.ease_factor,
        "interval_days": state.interval_days,
        "repetitions": state.repetitions,
        "due_at": state.due_at.isoformat() if state.due_at else None,
        "state": state.state,
        "review_count": state.review_count,
        "lapse_count": state.lapse_count,
        "retrievability": state.retrievability,
    }
