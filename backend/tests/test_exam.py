from app.models import ContentChunk, ContentFile, Exercise, SkillNode
from tests.conftest import register


def _seed(db, user_id: str) -> None:
    content_file = ContentFile(
        uploaded_by=user_id,
        filename="sinav.md",
        storage_path="/tmp/sinav.md",
    )
    db.add(content_file)
    db.flush()
    chunk = ContentChunk(file_id=content_file.id, chunk_index=0, raw_text="Sınav içeriği.")
    db.add(chunk)
    db.flush()
    skill = SkillNode(title="Sınav Yeteneği", category="genel")
    db.add(skill)
    db.flush()
    for index in range(3):
        db.add(
            Exercise(
                skill_id=skill.id,
                type="mcq",
                payload={
                    "stem": f"Soru {index}",
                    "options": [
                        {"text": "Doğru", "is_correct": True},
                        {"text": "Yanlış", "is_correct": False},
                    ],
                    "explanation": "Açıklama",
                },
                status="approved",
                source_chunk_id=chunk.id,
                dedupe_hash=f"exam-{index}",
            )
        )
    db.commit()


def test_exam_start_and_submit_scores_answers(client, db):
    student = register(client, email="sinav@example.com")
    _seed(db, student["user"]["id"])

    started = client.post(
        "/api/v1/exam/start",
        json={"count": 3, "duration_minutes": 30},
        headers=student["headers"],
    )
    assert started.status_code == 200, started.text
    session = started.json()
    assert len(session["questions"]) == 3
    assert session["expires_at"] > session["started_at"]
    assert all("is_correct" not in str(question["payload"]) for question in session["questions"])

    answers = []
    for question in session["questions"]:
        exercise = db.get(Exercise, question["exercise_id"])
        correct = next(
            index
            for index, option in enumerate(exercise.payload["options"])
            if option["is_correct"]
        )
        answers.append(
            {
                "exercise_id": question["exercise_id"],
                "answer": {"option_index": correct},
            }
        )

    result = client.post(
        "/api/v1/exam/submit",
        json={"session_id": session["session_id"], "answers": answers},
        headers=student["headers"],
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["score"] == 100.0
    assert body["correct_count"] == 3
    assert body["total"] == 3
    assert body["xp_awarded"] > 0
    assert len(body["details"]) == 3


def test_exam_rejects_tampered_or_foreign_session(client, db):
    student = register(client, email="sinav2@example.com")
    other = register(client, email="sinav3@example.com")
    _seed(db, student["user"]["id"])

    started = client.post(
        "/api/v1/exam/start",
        json={"count": 3, "duration_minutes": 30},
        headers=student["headers"],
    ).json()

    foreign = client.post(
        "/api/v1/exam/submit",
        json={"session_id": started["session_id"], "answers": []},
        headers=other["headers"],
    )
    assert foreign.status_code == 400

    tampered = client.post(
        "/api/v1/exam/submit",
        json={"session_id": started["session_id"] + "x", "answers": []},
        headers=student["headers"],
    )
    assert tampered.status_code == 400
