from datetime import timedelta

import pytest

from app.models import ContentChunk, ContentFile, Exercise, ReviewLog, SkillNode, utcnow
from tests.conftest import register


def _seed_reviews(db, user_id: str, count: int, correct: bool) -> None:
    content_file = ContentFile(
        uploaded_by=user_id,
        filename="kisisel.md",
        storage_path="/tmp/kisisel.md",
    )
    db.add(content_file)
    db.flush()
    chunk = ContentChunk(file_id=content_file.id, chunk_index=0, raw_text="Kişiselleştirme.")
    db.add(chunk)
    db.flush()
    skill = SkillNode(title="Kişisel Yetenek", category="genel")
    db.add(skill)
    db.flush()
    exercise = Exercise(
        skill_id=skill.id,
        type="mcq",
        payload={"stem": "Soru", "options": []},
        status="approved",
        source_chunk_id=chunk.id,
        dedupe_hash="kisisel-1",
    )
    db.add(exercise)
    db.flush()
    for _ in range(count):
        db.add(
            ReviewLog(
                user_id=user_id,
                exercise_id=exercise.id,
                rating="again" if not correct else "good",
                is_correct=correct,
                answer={"option_index": 0},
                reviewed_at=utcnow(),
                state_before={},
                state_after={},
            )
        )
    db.commit()


def test_personalization_optimizes_retention_from_reviews(client, db):
    student = register(client, email="kisisel@example.com")
    user_id = student["user"]["id"]

    default = client.get("/api/v1/study/personalization", headers=student["headers"])
    assert default.status_code == 200
    assert default.json()["desired_retention"] == 0.9
    assert default.json()["reviews_analyzed"] == 0

    _seed_reviews(db, user_id, 6, correct=False)
    optimized = client.post(
        "/api/v1/study/personalization/optimize", headers=student["headers"]
    )
    assert optimized.status_code == 200, optimized.text
    body = optimized.json()
    assert body["desired_retention"] == 0.93
    assert body["reviews_analyzed"] == 6
    assert body["accuracy"] == 0.0
    assert body["lapse_rate"] == 1.0

    reread = client.get("/api/v1/study/personalization", headers=student["headers"]).json()
    assert reread["desired_retention"] == 0.93


def _seed_optimizer_reviews(db, user_id: str, count: int) -> None:
    content_file = ContentFile(
        uploaded_by=user_id,
        filename="optimizer.md",
        storage_path="/tmp/optimizer.md",
    )
    db.add(content_file)
    db.flush()
    chunk = ContentChunk(file_id=content_file.id, chunk_index=0, raw_text="Optimizer.")
    db.add(chunk)
    db.flush()
    skill = SkillNode(title="Optimizer Yeteneği", category="genel")
    db.add(skill)
    db.flush()
    exercise = Exercise(
        skill_id=skill.id,
        type="mcq",
        payload={"stem": "Soru", "options": []},
        status="approved",
        source_chunk_id=chunk.id,
        dedupe_hash="optimizer-1",
    )
    db.add(exercise)
    db.flush()
    start = utcnow() - timedelta(days=count * 3)
    for index in range(count):
        db.add(
            ReviewLog(
                user_id=user_id,
                exercise_id=exercise.id,
                rating="again" if index % 4 == 0 else "good",
                is_correct=index % 4 != 0,
                answer={"option_index": 0},
                reviewed_at=start + timedelta(days=index * 3),
                state_before={},
                state_after={},
            )
        )
    db.commit()


def test_personalization_uses_fsrs_optimizer_with_enough_reviews(client, db):
    pytest.importorskip("torch")
    pytest.importorskip("pandas")
    student = register(client, email="optimizer@example.com")
    _seed_optimizer_reviews(db, student["user"]["id"], 600)

    response = client.post(
        "/api/v1/study/personalization/optimize", headers=student["headers"]
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["strategy"] == "fsrs_optimizer"
    assert body["parameter_count"] == 21
    assert body["reviews_analyzed"] == 600
