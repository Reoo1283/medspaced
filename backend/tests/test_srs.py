from datetime import timedelta

from app.models import UserCardState, utcnow
from app.services.srs import _apply_fsrs, _apply_sm2, compute_retrievability


def _state(**overrides) -> UserCardState:
    values = {
        "user_id": "u1",
        "exercise_id": "e1",
        "scheduler": "sm2",
        "ease_factor": 2.5,
        "interval_days": 0,
        "repetitions": 0,
        "state": "new",
        "review_count": 0,
        "lapse_count": 0,
    }
    values.update(overrides)
    return UserCardState(**values)


def test_sm2_progression():
    now = utcnow()
    state = _state()
    _apply_sm2(state, "good", now)
    assert state.repetitions == 1
    assert state.interval_days == 1
    assert state.due_at == now + timedelta(days=1)

    _apply_sm2(state, "good", now)
    assert state.repetitions == 2
    assert state.interval_days == 6

    _apply_sm2(state, "good", now)
    assert state.repetitions == 3
    assert state.interval_days > 6


def test_sm2_lapse_resets_repetitions():
    now = utcnow()
    state = _state(repetitions=4, interval_days=15, state="review")
    _apply_sm2(state, "again", now)
    assert state.repetitions == 0
    assert state.interval_days == 1
    assert state.state == "relearning"
    assert state.lapse_count == 1
    assert state.ease_factor >= 1.3


def test_fsrs_schedule_sets_card_and_due():
    now = utcnow()
    state = _state(scheduler="fsrs")
    _apply_fsrs(state, "good", now)
    assert state.fsrs_card is not None
    assert state.due_at is not None
    assert state.due_at > now


def test_retrievability_bounds():
    state = _state(interval_days=10, last_review_at=utcnow() - timedelta(days=5))
    value = compute_retrievability(state)
    assert 0.0 <= value <= 1.0
    assert compute_retrievability(_state()) == 0.0


def test_irt_updates_ability_and_difficulty(client, db):
    from app.models import ContentChunk, ContentFile, Exercise
    from app.services.irt import update_from_review
    from tests.conftest import register

    user = register(client, email="irt@example.com")
    content_file = ContentFile(
        uploaded_by=user["user"]["id"],
        filename="irt.md",
        storage_path="/tmp/irt.md",
    )
    db.add(content_file)
    db.flush()
    chunk = ContentChunk(
        file_id=content_file.id,
        chunk_index=0,
        raw_text="IRT kalibrasyon testi.",
    )
    db.add(chunk)
    db.flush()
    exercise = Exercise(
        type="mcq",
        payload={"stem": "IRT testi", "options": []},
        difficulty=0.5,
        discrimination=1.0,
        guessing=0.0,
        status="approved",
        source_chunk_id=chunk.id,
        created_by_ai=True,
        dedupe_hash="irt-test-hash",
    )
    db.add(exercise)
    db.commit()

    correct = update_from_review(
        db,
        user_id=user["user"]["id"],
        exercise=exercise,
        is_correct=True,
    )
    assert correct["theta"] > 0
    assert correct["exercise_difficulty"] < 0.5

    wrong = update_from_review(
        db,
        user_id=user["user"]["id"],
        exercise=exercise,
        is_correct=False,
    )
    assert wrong["theta"] < correct["theta"]
    assert wrong["exercise_difficulty"] > correct["exercise_difficulty"]
    assert 0.05 <= wrong["exercise_difficulty"] <= 0.95


def test_league_promotes_with_weekly_xp(client, db):
    from datetime import timedelta

    from app.models import UserXP
    from app.services.gamification import award_review_xp, get_stats, league_for
    from tests.conftest import register

    assert league_for(0) == "bronz"
    assert league_for(99) == "bronz"
    assert league_for(100) == "gümüş"
    assert league_for(300) == "altın"
    assert league_for(700) == "platin"

    user = register(client, email="league@example.com")
    for _ in range(7):
        award_review_xp(db, user["user"]["id"], "good", True)
    db.commit()
    assert get_stats(db, user["user"]["id"])["league"] == "gümüş"

    xp = db.query(UserXP).filter_by(user_id=user["user"]["id"]).one()
    xp.week_start = xp.week_start - timedelta(days=7)
    db.commit()
    award_review_xp(db, user["user"]["id"], "again", False)
    db.commit()
    stats = get_stats(db, user["user"]["id"])
    assert stats["weekly_xp"] == 10
    assert stats["league"] == "bronz"
