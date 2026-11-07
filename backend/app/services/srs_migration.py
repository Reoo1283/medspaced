from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import SrsMigrationAudit, UserCardState, utcnow
from app.services.srs import compute_retrievability

FSRS_MODEL_VERSION = 3


def _sm2_state_to_fsrs_card(state: UserCardState, now: datetime) -> dict[str, Any] | None:
    """Convert an SM-2 state to an initial FSRS Card dict."""
    if state.fsrs_card is not None:
        return None  # already has FSRS card
    if state.scheduler == "fsrs":
        return None  # already using FSRS

    # Map SM-2 state to FSRS State
    from fsrs import State

    if state.state == "review":
        fsrs_state = State.Review
    elif state.state == "relearning":
        fsrs_state = State.Relearning
    else:
        fsrs_state = State.Learning

    # Stability from interval (days)
    stability = max(0.1, float(state.interval_days or 1.0))

    # Difficulty from ease_factor (2.5 default)
    # Map ease_factor ~2.5 to difficulty ~5.0, lower ease -> higher difficulty
    ease = state.ease_factor or 2.5
    difficulty = round(max(1.0, min(10.0, 5.0 + (2.5 - ease) * 2.0)), 2)

    due = state.due_at or now
    if due.tzinfo is not None:
        due = due.replace(tzinfo=None)

    last_review = state.last_review_at
    if last_review is not None and last_review.tzinfo is not None:
        last_review = last_review.replace(tzinfo=None)

    return {
        "card_id": 0,  # will be set by FSRS
        "state": fsrs_state.value,
        "step": None,
        "stability": stability,
        "difficulty": difficulty,
        "due": due.isoformat(),
        "last_review": last_review.isoformat() if last_review else None,
    }


def _card_snapshot(state: UserCardState) -> dict[str, Any]:
    """Create a serializable snapshot of the card state."""
    return {
        "scheduler": state.scheduler,
        "fsrs_card": state.fsrs_card,
        "stability": state.stability,
        "difficulty": state.difficulty,
        "due_at": state.due_at.isoformat() if state.due_at else None,
        "state": state.state,
        "interval_days": state.interval_days,
        "retrievability": state.retrievability,
    }


def _apply_fsrs_card(state: UserCardState, card_dict: dict[str, Any], now: datetime) -> None:
    """Apply an FSRS card dict to the state."""
    state.scheduler = "fsrs"
    state.fsrs_card = card_dict
    state.stability = card_dict.get("stability")
    state.difficulty = card_dict.get("difficulty")
    state.due_at = datetime.fromisoformat(card_dict["due"]) if card_dict.get("due") else None
    state.state = card_dict.get("state", "learning").lower()
    if state.due_at and state.due_at > now:
        state.interval_days = max(0, (state.due_at - now).days)
    else:
        state.interval_days = 0
    state.retrievability = compute_retrievability(state, now)


def _apply_before_state(state: UserCardState, snap: dict[str, Any]) -> None:
    """Restore state from a before snapshot."""
    state.scheduler = snap.get("scheduler", "sm2")
    state.fsrs_card = snap.get("fsrs_card")
    state.stability = snap.get("stability")
    state.difficulty = snap.get("difficulty")
    state.due_at = datetime.fromisoformat(snap["due_at"]) if snap.get("due_at") else None
    state.state = snap.get("state", "new")
    state.interval_days = snap.get("interval_days", 0)
    state.retrievability = snap.get("retrievability")


def plan_srs_migration(db: Session, limit: int | None = None) -> dict:
    """Plan the SM-2 -> FSRS migration: count candidates, show sample conversions."""
    query = select(UserCardState).where(
        (UserCardState.scheduler != "fsrs") | (UserCardState.fsrs_card.is_(None))
    ).order_by(UserCardState.created_at)
    if limit:
        query = query.limit(limit)
    candidates = list(db.scalars(query).all())

    by_scheduler: dict[str, int] = {}
    for c in candidates:
        by_scheduler[c.scheduler] = by_scheduler.get(c.scheduler, 0) + 1

    sample = []
    now = utcnow()
    for state in candidates[:5]:
        card = _sm2_state_to_fsrs_card(state, now)
        if card:
            sample.append(
                {
                    "card_id": state.id,
                    "user_id": state.user_id,
                    "exercise_id": state.exercise_id,
                    "current": _card_snapshot(state),
                    "proposed_fsrs": card,
                }
            )

    return {
        "candidates": len(candidates),
        "by_scheduler": by_scheduler,
        "sample": sample,
    }


def apply_srs_migration(db: Session, limit: int | None = None, batch_id: str | None = None) -> dict:
    """Apply the SM-2 -> FSRS migration for candidate cards."""
    import uuid

    if batch_id is None:
        batch_id = str(uuid.uuid4())

    query = select(UserCardState).where(
        (UserCardState.scheduler != "fsrs") | (UserCardState.fsrs_card.is_(None))
    ).order_by(UserCardState.created_at)
    if limit:
        query = query.limit(limit)
    candidates = list(db.scalars(query).all())

    now = utcnow()
    applied = 0
    skipped = 0
    for state in candidates:
        before = _card_snapshot(state)
        card = _sm2_state_to_fsrs_card(state, now)
        if card is None:
            skipped += 1
            continue
        _apply_fsrs_card(state, card, now)
        after = _card_snapshot(state)

        audit = SrsMigrationAudit(
            batch_id=batch_id,
            card_id=state.id,
            before_state=before,
            after_state=after,
            status="applied",
            created_at=utcnow(),
        )
        db.add(audit)
        applied += 1

    db.commit()
    return {
        "batch_id": batch_id,
        "applied": applied,
        "skipped": skipped,
    }


def validate_srs_migration(db: Session, batch_id: str | None = None) -> dict:
    """Validate a migration batch: check that cards have valid FSRS state."""
    query = select(SrsMigrationAudit).where(SrsMigrationAudit.status == "applied")
    if batch_id:
        query = query.where(SrsMigrationAudit.batch_id == batch_id)
    audits = list(db.scalars(query).all())

    valid = 0
    invalid = 0
    issues: list[dict] = []

    for audit in audits:
        state = db.get(UserCardState, audit.card_id)
        if state is None:
            invalid += 1
            issues.append({"card_id": audit.card_id, "issue": "card_missing"})
            continue
        if state.scheduler != "fsrs" or state.fsrs_card is None:
            invalid += 1
            issues.append(
                {
                    "card_id": audit.card_id,
                    "issue": "not_fsrs",
                    "scheduler": state.scheduler,
                    "has_card": state.fsrs_card is not None,
                }
            )
            continue
        card = state.fsrs_card
        if (
            card.get("stability") is None
            or card.get("stability", 0) <= 0
            or card.get("difficulty") is None
            or not (1.0 <= card["difficulty"] <= 10.0)
            or card.get("due") is None
        ):
            invalid += 1
            issues.append({"card_id": audit.card_id, "issue": "invalid_card_fields", "card": card})
            continue
        valid += 1

    return {
        "batch_id": batch_id,
        "total_audits": len(audits),
        "valid": valid,
        "invalid": invalid,
        "issues": issues[:20],
    }


def rollback_srs_migration(db: Session, batch_id: str) -> dict:
    """Rollback a migration batch by restoring before_state."""
    audits = list(
        db.scalars(
            select(SrsMigrationAudit).where(
                SrsMigrationAudit.batch_id == batch_id,
                SrsMigrationAudit.status == "applied",
            )
        ).all()
    )

    rolled_back = 0
    for audit in audits:
        state = db.get(UserCardState, audit.card_id)
        if state is None:
            continue
        _apply_before_state(state, audit.before_state)
        audit.status = "rolled_back"
        audit.rolled_back_at = utcnow()
        rolled_back += 1

    db.commit()
    return {
        "batch_id": batch_id,
        "rolled_back": rolled_back,
    }