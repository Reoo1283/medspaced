from app.core.db import SessionLocal
from app.models import Exercise
from tests.conftest import make_reviewer, register

CONTENT = """# Solunum Fizyolojisi

Solunum sistemi oksijen alımı ve karbondioksit atılımından sorumludur. Alveoller gaz değişiminin gerçekleştiği temel yapılardır. Surfaktan alveollerin yüzey gerilimini azaltarak kollapsı önler.

# Anestezi İndüksiyonu

Propofol hızlı etkili intravenöz anestezik ajanlardan biridir. İndüksiyon sırasında hipotansiyon görülebilir. Havayolu güvenliği sağlanmadan cerrahi işleme başlanmamalıdır.
"""


def _create_skill(client, reviewer, title="Solunum") -> str:
    response = client.post(
        "/api/v1/skills",
        json={"title": title, "category": "fizyoloji"},
        headers=reviewer["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _upload(client, reviewer, filename="solunum.md", content=CONTENT) -> dict:
    response = client.post(
        "/api/v1/content/files",
        files={"file": (filename, content.encode("utf-8"), "text/markdown")},
        headers=reviewer["headers"],
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_full_content_to_study_flow(client, db):
    reviewer = make_reviewer(client, db)
    student = register(client, email="ogrenci@example.com")
    skill_id = _create_skill(client, reviewer)

    upload = _upload(client, reviewer)
    file_id = upload["file"]["id"]
    process_job = client.get(
        f"/api/v1/content/jobs/{upload['job']['id']}", headers=reviewer["headers"]
    ).json()
    assert process_job["status"] == "completed", process_job
    assert process_job["result"]["chunks"] >= 1

    chunks = client.get(
        f"/api/v1/content/files/{file_id}/chunks", headers=reviewer["headers"]
    ).json()
    assert chunks

    generation = client.post(
        f"/api/v1/content/files/{file_id}/generate",
        json={
            "skill_id": skill_id,
            "exercise_types": ["mcq", "cloze"],
            "max_chunks": 3,
        },
        headers=reviewer["headers"],
    )
    assert generation.status_code == 200, generation.text
    generate_job = client.get(
        f"/api/v1/content/jobs/{generation.json()['job']['id']}",
        headers=reviewer["headers"],
    ).json()
    assert generate_job["status"] == "completed", generate_job
    assert generate_job["result"]["exercises_created"] >= 1

    queue = client.get(
        "/api/v1/review/queue?status=under_review", headers=reviewer["headers"]
    ).json()
    assert queue
    mcqs = [item for item in queue if item["type"] == "mcq"]
    assert mcqs
    for item in mcqs:
        decision = client.post(
            f"/api/v1/review/exercises/{item['id']}/decision",
            json={"action": "approve", "note": "Kaynakla uyumlu"},
            headers=reviewer["headers"],
        )
        assert decision.status_code == 200, decision.text
        assert decision.json()["status"] == "approved"

    due = client.get("/api/v1/study/due", headers=student["headers"]).json()
    assert due
    assert all(item["type"] == "mcq" for item in due)
    target = due[0]

    session = SessionLocal()
    try:
        exercise = session.get(Exercise, target["exercise_id"])
        correct_index = next(
            index
            for index, option in enumerate(exercise.payload["options"])
            if option["is_correct"]
        )
    finally:
        session.close()

    review = client.post(
        "/api/v1/study/reviews",
        json={
            "exercise_id": target["exercise_id"],
            "answer": {"option_index": correct_index},
            "response_time_ms": 4200,
        },
        headers=student["headers"],
    )
    assert review.status_code == 200, review.text
    result = review.json()
    assert result["is_correct"] is True
    assert result["xp_awarded"] > 0
    assert result["current_streak"] == 1
    assert result["mastery_score"] is not None
    assert result["ability_theta"] > 0
    assert result["exercise_difficulty"] <= 0.5

    session = SessionLocal()
    try:
        from app.models import UserCardState

        state = session.query(UserCardState).filter_by(
            user_id=student["user"]["id"], exercise_id=target["exercise_id"]
        ).one()
        assert state.scheduler == "fsrs"
        assert state.fsrs_card is not None
    finally:
        session.close()

    stats = client.get("/api/v1/study/stats", headers=student["headers"]).json()
    assert stats["reviews_today"] == 1
    assert stats["total_xp"] == result["total_xp"]
    assert stats["approved_exercise_count"] >= 1
    assert stats["ability_theta"] == result["ability_theta"]


def test_student_cannot_access_review_queue(client, db):
    make_reviewer(client, db)
    student = register(client, email="ogrenci2@example.com")
    response = client.get("/api/v1/review/queue", headers=student["headers"])
    assert response.status_code == 403


def test_reject_requires_note(client, db):
    reviewer = make_reviewer(client, db)
    skill_id = _create_skill(client, reviewer, title="Red Testi")
    upload = _upload(client, reviewer, filename="red.md")
    client.post(
        f"/api/v1/content/files/{upload['file']['id']}/generate",
        json={"skill_id": skill_id, "exercise_types": ["mcq"], "max_chunks": 1},
        headers=reviewer["headers"],
    )
    queue = client.get("/api/v1/review/queue", headers=reviewer["headers"]).json()
    assert queue
    response = client.post(
        f"/api/v1/review/exercises/{queue[0]['id']}/decision",
        json={"action": "reject"},
        headers=reviewer["headers"],
    )
    assert response.status_code == 400


def test_completed_jobs_are_idempotent(client, db):
    from app.services.jobs import generate_exercises_job, process_content_job

    reviewer = make_reviewer(client, db, email="idempotent@example.com")
    skill_id = _create_skill(client, reviewer, title="Idempotent")
    upload = _upload(client, reviewer, filename="idempotent.md")
    file_id = upload["file"]["id"]
    process_job_id = upload["job"]["id"]

    chunks_url = f"/api/v1/content/files/{file_id}/chunks"
    chunks_before = client.get(chunks_url, headers=reviewer["headers"]).json()
    process_content_job(process_job_id, file_id)
    chunks_after = client.get(chunks_url, headers=reviewer["headers"]).json()
    assert len(chunks_after) == len(chunks_before)

    generation = client.post(
        f"/api/v1/content/files/{file_id}/generate",
        json={"skill_id": skill_id, "exercise_types": ["mcq"], "max_chunks": 1},
        headers=reviewer["headers"],
    )
    generation_job_id = generation.json()["job"]["id"]
    queue_url = "/api/v1/review/queue?status=under_review"
    before = client.get(queue_url, headers=reviewer["headers"]).json()
    generate_exercises_job(generation_job_id, file_id, skill_id, ["mcq"], 1)
    after = client.get(queue_url, headers=reviewer["headers"]).json()
    assert len(after) == len(before)
