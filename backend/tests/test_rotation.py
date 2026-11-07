from app.models import ContentChunk, ContentFile, Exercise, SkillNode
from tests.conftest import register


def _seed_exercises(db, user_id: str) -> tuple[str, str]:
    content_file = ContentFile(
        uploaded_by=user_id,
        filename="rotasyon.md",
        storage_path="/tmp/rotasyon.md",
    )
    db.add(content_file)
    db.flush()
    chunk = ContentChunk(file_id=content_file.id, chunk_index=0, raw_text="Rotasyon testi.")
    db.add(chunk)
    db.flush()
    cardio = SkillNode(title="Kardiyak Anestezi", category="kardiyoloji")
    respiratory = SkillNode(title="Solunum Fizyolojisi", category="fizyoloji")
    db.add_all([cardio, respiratory])
    db.flush()
    db.add_all(
        [
            Exercise(
                skill_id=cardio.id,
                type="mcq",
                payload={"stem": "Kardiyak soru", "options": []},
                status="approved",
                source_chunk_id=chunk.id,
                dedupe_hash="rotation-cardio",
            ),
            Exercise(
                skill_id=respiratory.id,
                type="mcq",
                payload={"stem": "Solunum sorusu", "options": []},
                status="approved",
                source_chunk_id=chunk.id,
                dedupe_hash="rotation-respiratory",
            ),
        ]
    )
    db.commit()
    return cardio.id, respiratory.id


def test_rotation_prioritizes_matching_skill(client, db):
    student = register(client, email="rotasyon@example.com")
    cardio_id, _ = _seed_exercises(db, student["user"]["id"])

    response = client.put(
        "/api/v1/study/rotation",
        json={"name": "Kardiyak"},
        headers=student["headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Kardiyak"

    due = client.get("/api/v1/study/due", headers=student["headers"]).json()
    assert due[0]["skill_id"] == cardio_id
    assert due[0]["rotation_match"] is True
    assert any(item["rotation_match"] is False for item in due[1:])

    stats = client.get("/api/v1/study/stats", headers=student["headers"]).json()
    assert stats["rotation"] == "Kardiyak"

    cleared = client.delete("/api/v1/study/rotation", headers=student["headers"])
    assert cleared.json() == {"cleared": True}
    stats = client.get("/api/v1/study/stats", headers=student["headers"]).json()
    assert stats["rotation"] is None


def test_rotation_rejects_inverted_dates(client):
    student = register(client, email="rotasyon2@example.com")
    response = client.put(
        "/api/v1/study/rotation",
        json={"name": "Kardiyak", "starts_on": "2026-02-01", "ends_on": "2026-01-01"},
        headers=student["headers"],
    )
    assert response.status_code == 400
