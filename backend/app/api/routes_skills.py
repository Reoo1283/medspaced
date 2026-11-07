from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models import User
from app.schemas import (
    PrerequisiteRequest,
    SkillCreate,
    SkillOut,
    SkillProgressOut,
    SkillTreeNode,
    SkillUpdate,
)
from app.services.skills import (
    SkillError,
    add_prerequisite,
    create_skill,
    delete_skill,
    list_skills,
    progress_list,
    remove_prerequisite,
    skill_tree,
    update_skill,
)

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=list[SkillOut])
def get_skills(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    return list_skills(db, user.id)


@router.get("/tree", response_model=list[SkillTreeNode])
def get_tree(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    return skill_tree(db, user.id)


@router.get("/progress", response_model=list[SkillProgressOut])
def get_progress(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    return progress_list(db, user.id)


@router.post("", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
def create(
    payload: SkillCreate,
    user: User = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        skill = create_skill(
            db,
            title=payload.title,
            category=payload.category,
            description=payload.description,
            parent_id=payload.parent_id,
        )
    except SkillError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "id": skill.id,
        "title": skill.title,
        "category": skill.category,
        "description": skill.description,
        "parent_id": skill.parent_id,
        "prerequisites": [],
        "mastery_score": 0.0,
        "unlocked": True,
    }


@router.patch("/{skill_id}", response_model=SkillOut)
def update(
    skill_id: str,
    payload: SkillUpdate,
    user: User = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        skill = update_skill(db, skill_id, payload.model_dump(exclude_unset=True))
        items = {item["id"]: item for item in list_skills(db, user.id)}
    except SkillError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return items[skill.id]


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    skill_id: str,
    _: User = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> None:
    try:
        delete_skill(db, skill_id)
    except SkillError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{skill_id}/prerequisites", response_model=SkillOut)
def add_prereq(
    skill_id: str,
    payload: PrerequisiteRequest,
    user: User = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        add_prerequisite(db, skill_id, payload.prerequisite_id)
        items = {item["id"]: item for item in list_skills(db, user.id)}
    except SkillError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return items[skill_id]


@router.delete("/{skill_id}/prerequisites/{prerequisite_id}", response_model=SkillOut)
def remove_prereq(
    skill_id: str,
    prerequisite_id: str,
    user: User = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    remove_prerequisite(db, skill_id, prerequisite_id)
    items = {item["id"]: item for item in list_skills(db, user.id)}
    if skill_id not in items:
        raise HTTPException(status_code=404, detail="Skill bulunamadı")
    return items[skill_id]
