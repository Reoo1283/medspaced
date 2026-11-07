from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Exercise,
    SkillConcept,
    SkillNode,
    SkillPrerequisite,
    UserSkillProgress,
    utcnow,
)
from app.services.learning_policy import get_policy


class SkillError(Exception):
    pass


def get_skill(db: Session, skill_id: str) -> SkillNode:
    skill = db.get(SkillNode, skill_id)
    if skill is None:
        raise SkillError("Skill bulunamadı")
    return skill


def create_skill(db: Session, *, title: str, category: str, description: str, parent_id: str | None) -> SkillNode:
    if parent_id:
        get_skill(db, parent_id)
    skill = SkillNode(
        title=title.strip(),
        category=(category or "genel").strip(),
        description=(description or "").strip(),
        parent_id=parent_id,
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


def update_skill(db: Session, skill_id: str, values: dict) -> SkillNode:
    skill = get_skill(db, skill_id)
    if "parent_id" in values:
        parent_id = values["parent_id"]
        if parent_id:
            if parent_id == skill_id:
                raise SkillError("Bir skill kendi ebeveyni olamaz")
            get_skill(db, parent_id)
            if _is_descendant(db, skill_id, parent_id):
                raise SkillError("Ebeveyn değişikliği döngü oluşturur")
        skill.parent_id = parent_id
    for field in ("title", "category", "description"):
        if field in values and values[field] is not None:
            setattr(skill, field, values[field])
    db.commit()
    db.refresh(skill)
    return skill


def _is_descendant(db: Session, ancestor_id: str, candidate_id: str) -> bool:
    """True when candidate_id is ancestor_id itself or sits below it in the tree."""
    current: str | None = candidate_id
    visited: set[str] = set()
    while current and current not in visited:
        if current == ancestor_id:
            return True
        visited.add(current)
        node = db.get(SkillNode, current)
        if node is None:
            return False
        current = node.parent_id
    return False


def delete_skill(db: Session, skill_id: str) -> None:
    skill = get_skill(db, skill_id)
    exercise_count = db.scalar(select(Exercise.id).where(Exercise.skill_id == skill_id).limit(1))
    if exercise_count is not None:
        raise SkillError("Bu skill'e bağlı sorular var; önce onları silin veya taşıyın")
    db.query(SkillPrerequisite).filter(
        (SkillPrerequisite.skill_id == skill_id)
        | (SkillPrerequisite.prerequisite_id == skill_id)
    ).delete(synchronize_session=False)
    db.query(SkillConcept).filter(SkillConcept.skill_id == skill_id).delete(synchronize_session=False)
    db.query(UserSkillProgress).filter(UserSkillProgress.skill_id == skill_id).delete(
        synchronize_session=False
    )
    db.query(SkillNode).filter(SkillNode.parent_id == skill_id).update(
        {"parent_id": None}, synchronize_session=False
    )
    db.delete(skill)
    db.commit()


def add_prerequisite(db: Session, skill_id: str, prerequisite_id: str) -> None:
    get_skill(db, skill_id)
    get_skill(db, prerequisite_id)
    if skill_id == prerequisite_id:
        raise SkillError("Bir skill kendi önkoşulu olamaz")
    existing = db.scalar(
        select(SkillPrerequisite).where(
            SkillPrerequisite.skill_id == skill_id,
            SkillPrerequisite.prerequisite_id == prerequisite_id,
        )
    )
    if existing is not None:
        return
    if _depends_on(db, prerequisite_id, skill_id):
        raise SkillError("Bu önkoşul döngü oluşturur")
    db.add(SkillPrerequisite(skill_id=skill_id, prerequisite_id=prerequisite_id))
    db.commit()


def remove_prerequisite(db: Session, skill_id: str, prerequisite_id: str) -> None:
    link = db.scalar(
        select(SkillPrerequisite).where(
            SkillPrerequisite.skill_id == skill_id,
            SkillPrerequisite.prerequisite_id == prerequisite_id,
        )
    )
    if link is not None:
        db.delete(link)
        db.commit()


def _depends_on(db: Session, skill_id: str, candidate_id: str) -> bool:
    """True when skill_id transitively depends on candidate_id."""
    visited: set[str] = set()
    stack = [skill_id]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        prerequisites = db.scalars(
            select(SkillPrerequisite.prerequisite_id).where(SkillPrerequisite.skill_id == current)
        ).all()
        if candidate_id in prerequisites:
            return True
        stack.extend(prerequisites)
    return False


def _progress_map(db: Session, user_id: str) -> dict[str, float]:
    rows = db.scalars(select(UserSkillProgress).where(UserSkillProgress.user_id == user_id)).all()
    return {row.skill_id: row.mastery_score for row in rows}


def unlocked_skill_ids(db: Session, user_id: str) -> set[str]:
    nodes = db.scalars(select(SkillNode.id)).all()
    prerequisites: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    for link in db.scalars(select(SkillPrerequisite)).all():
        prerequisites.setdefault(link.skill_id, []).append(link.prerequisite_id)
    mastery = _progress_map(db, user_id)
    policy = get_policy(db, user_id)
    threshold = policy["mastery_threshold"]

    unlocked: set[str] = set()
    changed = True
    while changed:
        changed = False
        for node_id in nodes:
            if node_id in unlocked:
                continue
            if all(
                prerequisite in unlocked and mastery.get(prerequisite, 0.0) >= threshold
                for prerequisite in prerequisites.get(node_id, [])
            ):
                unlocked.add(node_id)
                changed = True
    return unlocked


def update_mastery(db: Session, user_id: str, skill_id: str | None, is_correct: bool) -> float | None:
    if not skill_id:
        return None
    progress = db.scalar(
        select(UserSkillProgress).where(
            UserSkillProgress.user_id == user_id,
            UserSkillProgress.skill_id == skill_id,
        )
    )
    if progress is None:
        progress = UserSkillProgress(
            user_id=user_id,
            skill_id=skill_id,
            mastery_score=0.0,
        )
        db.add(progress)
    alpha = 0.2
    target = 100.0 if is_correct else 0.0
    progress.mastery_score = round(
        max(0.0, min(100.0, progress.mastery_score * (1 - alpha) + target * alpha)), 2
    )
    progress.last_practiced_at = utcnow()
    db.flush()
    return progress.mastery_score


def skill_payload(db: Session, skill: SkillNode, *, mastery: float, unlocked: bool) -> dict:
    prerequisites = db.scalars(
        select(SkillPrerequisite.prerequisite_id).where(SkillPrerequisite.skill_id == skill.id)
    ).all()
    return {
        "id": skill.id,
        "title": skill.title,
        "category": skill.category,
        "description": skill.description,
        "parent_id": skill.parent_id,
        "prerequisites": list(prerequisites),
        "mastery_score": mastery,
        "unlocked": unlocked,
    }


def list_skills(db: Session, user_id: str) -> list[dict]:
    nodes = db.scalars(select(SkillNode).order_by(SkillNode.title)).all()
    mastery = _progress_map(db, user_id)
    unlocked = unlocked_skill_ids(db, user_id)
    return [
        skill_payload(
            db,
            node,
            mastery=mastery.get(node.id, 0.0),
            unlocked=node.id in unlocked,
        )
        for node in nodes
    ]


def skill_tree(db: Session, user_id: str) -> list[dict]:
    skills = list_skills(db, user_id)
    by_id = {item["id"]: {**item, "children": []} for item in skills}
    roots: list[dict] = []
    for item in by_id.values():
        parent_id = item.get("parent_id")
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(item)
        else:
            roots.append(item)
    return roots


def progress_list(db: Session, user_id: str) -> list[dict]:
    nodes = db.scalars(select(SkillNode).order_by(SkillNode.title)).all()
    progress = {
        row.skill_id: row
        for row in db.scalars(select(UserSkillProgress).where(UserSkillProgress.user_id == user_id))
    }
    unlocked = unlocked_skill_ids(db, user_id)
    return [
        {
            "skill_id": node.id,
            "title": node.title,
            "category": node.category,
            "mastery_score": progress[node.id].mastery_score if node.id in progress else 0.0,
            "unlocked": node.id in unlocked,
            "last_practiced_at": progress[node.id].last_practiced_at if node.id in progress else None,
        }
        for node in nodes
    ]
