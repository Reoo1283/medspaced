from app.models import UserSkillProgress
from tests.conftest import make_reviewer, register


def _skill(client, reviewer, title: str, parent_id: str | None = None) -> dict:
    response = client.post(
        "/api/v1/skills",
        json={"title": title, "category": "test", "parent_id": parent_id},
        headers=reviewer["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_prerequisite_gates_unlock(client, db):
    reviewer = make_reviewer(client, db)
    student = register(client, email="kilit@example.com")

    first = _skill(client, reviewer, "Temel")
    second = _skill(client, reviewer, "İleri")

    link = client.post(
        f"/api/v1/skills/{second['id']}/prerequisites",
        json={"prerequisite_id": first["id"]},
        headers=reviewer["headers"],
    )
    assert link.status_code == 200, link.text
    assert first["id"] in link.json()["prerequisites"]

    items = {
        item["id"]: item
        for item in client.get("/api/v1/skills", headers=student["headers"]).json()
    }
    assert items[first["id"]]["unlocked"] is True
    assert items[second["id"]]["unlocked"] is False

    progress = UserSkillProgress(
        user_id=student["user"]["id"],
        skill_id=first["id"],
        mastery_score=90.0,
    )
    db.add(progress)
    db.commit()

    items = {
        item["id"]: item
        for item in client.get("/api/v1/skills", headers=student["headers"]).json()
    }
    assert items[second["id"]]["unlocked"] is True


def test_prerequisite_cycle_rejected(client, db):
    reviewer = make_reviewer(client, db)
    first = _skill(client, reviewer, "Alfa")
    second = _skill(client, reviewer, "Beta")

    response = client.post(
        f"/api/v1/skills/{second['id']}/prerequisites",
        json={"prerequisite_id": first["id"]},
        headers=reviewer["headers"],
    )
    assert response.status_code == 200

    cycle = client.post(
        f"/api/v1/skills/{first['id']}/prerequisites",
        json={"prerequisite_id": second["id"]},
        headers=reviewer["headers"],
    )
    assert cycle.status_code == 400

    self_link = client.post(
        f"/api/v1/skills/{first['id']}/prerequisites",
        json={"prerequisite_id": first["id"]},
        headers=reviewer["headers"],
    )
    assert self_link.status_code == 400


def test_skill_tree_nesting(client, db):
    reviewer = make_reviewer(client, db)
    root = _skill(client, reviewer, "Kök")
    child = _skill(client, reviewer, "Dal", parent_id=root["id"])

    tree = client.get("/api/v1/skills/tree", headers=reviewer["headers"]).json()
    root_node = next(node for node in tree if node["id"] == root["id"])
    assert any(node["id"] == child["id"] for node in root_node["children"])


def test_skill_parent_update_and_cycle_rejected(client, db):
    reviewer = make_reviewer(client, db)
    root = _skill(client, reviewer, "Kök")
    child = _skill(client, reviewer, "Dal", parent_id=root["id"])
    leaf = _skill(client, reviewer, "Yaprak", parent_id=child["id"])

    cycle = client.patch(
        f"/api/v1/skills/{root['id']}",
        json={"parent_id": leaf["id"]},
        headers=reviewer["headers"],
    )
    assert cycle.status_code == 400

    cleared = client.patch(
        f"/api/v1/skills/{child['id']}",
        json={"parent_id": None, "title": "Dal Güncel"},
        headers=reviewer["headers"],
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["parent_id"] is None
    assert cleared.json()["title"] == "Dal Güncel"

    tree = client.get("/api/v1/skills/tree", headers=reviewer["headers"]).json()
    child_node = next(node for node in tree if node["id"] == child["id"])
    assert child_node["parent_id"] is None
    assert any(node["id"] == leaf["id"] for node in child_node["children"])
