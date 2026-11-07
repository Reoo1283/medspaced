from __future__ import annotations

from datetime import date, datetime, time, timedelta
import random
import re
import unicodedata

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    ContentChunk,
    ContentFile,
    Exercise,
    ReviewLog,
    SkillNode,
    User,
    UserAbility,
    UserCardState,
    UserRotation,
    UserSkillProgress,
    utcnow,
)
from app.services import gamification, irt, vignette
from app.services.learning_policy import get_policy
from app.services.llm import LLMError, get_provider
from app.services.skills import unlocked_skill_ids, update_mastery
from app.services.srs import apply_review, compute_retrievability, get_or_create_state, state_snapshot


class StudyError(Exception):
    pass


def sanitize_payload(exercise: Exercise) -> dict:
    payload = exercise.payload or {}
    if exercise.type == "mcq":
        return {
            "stem": payload.get("stem", ""),
            "options": [option.get("text", "") for option in payload.get("options", [])],
        }
    if exercise.type == "cloze":
        return {"text": payload.get("text", "")}
    if exercise.type == "matching":
        lefts = [pair.get("left", "") for pair in payload.get("pairs", [])]
        rights = [pair.get("right", "") for pair in payload.get("pairs", [])]
        random.Random(exercise.id).shuffle(rights)
        return {"left": lefts, "right": rights}
    if exercise.type == "vignette":
        return {
            "vignette": payload.get("vignette", ""),
            "prompt": payload.get("prompt", ""),
        }
    clean = {key: value for key, value in payload.items() if key != "is_correct"}
    return clean


def _source_maps(db: Session, exercises: list[Exercise]) -> dict[str, dict]:
    chunk_ids = {exercise.source_chunk_id for exercise in exercises}
    if not chunk_ids:
        return {}
    chunks = {
        chunk.id: chunk
        for chunk in db.scalars(select(ContentChunk).where(ContentChunk.id.in_(chunk_ids)))
    }
    file_ids = {chunk.file_id for chunk in chunks.values()}
    files = {
        file.id: file
        for file in db.scalars(select(ContentFile).where(ContentFile.id.in_(file_ids)))
    }
    result: dict[str, dict] = {}
    for exercise in exercises:
        chunk = chunks.get(exercise.source_chunk_id)
        if chunk is None:
            continue
        content_file = files.get(chunk.file_id)
        result[exercise.id] = {
            "chunk_id": chunk.id,
            "file_id": chunk.file_id,
            "filename": content_file.filename if content_file else "",
            "section_title": chunk.section_title,
            "page_number": chunk.page_number,
            "snippet": chunk.raw_text[:280],
        }
    return result


def active_rotation(db: Session, user_id: str, today: date | None = None) -> UserRotation | None:
    today = today or utcnow().date()
    return db.scalar(
        select(UserRotation)
        .where(
            UserRotation.user_id == user_id,
            or_(UserRotation.starts_on.is_(None), UserRotation.starts_on <= today),
            or_(UserRotation.ends_on.is_(None), UserRotation.ends_on >= today),
        )
        .order_by(UserRotation.updated_at.desc())
    )


def set_rotation(db: Session, user: User, payload: dict) -> UserRotation:
    starts_on = payload.get("starts_on")
    ends_on = payload.get("ends_on")
    if starts_on and ends_on and starts_on > ends_on:
        raise StudyError("Rotasyon başlangıcı bitişten sonra olamaz")
    rotation = active_rotation(db, user.id)
    if rotation is None:
        rotation = UserRotation(user_id=user.id)
        db.add(rotation)
    rotation.name = payload["name"].strip()
    rotation.starts_on = starts_on
    rotation.ends_on = ends_on
    db.commit()
    db.refresh(rotation)
    return rotation


def clear_rotation(db: Session, user: User) -> bool:
    rotation = active_rotation(db, user.id)
    if rotation is None:
        return False
    rotation.ends_on = utcnow().date() - timedelta(days=1)
    db.commit()
    return True


def _normalize_word(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").casefold().strip()


def _rotation_matches(rotation: UserRotation, title: str, category: str) -> bool:
    rotation_text = _normalize_word(rotation.name)
    skill_text = f"{_normalize_word(title)} {_normalize_word(category)}"
    for token in re.split(r"[^\wçğıöşü]+", rotation_text):
        if len(token) >= 3 and token in skill_text:
            return True
    return rotation_text in skill_text


def due_items(db: Session, user: User, limit: int = 20) -> list[dict]:
    unlocked = unlocked_skill_ids(db, user.id)
    if not unlocked:
        return []
    exercises = list(
        db.scalars(
            select(Exercise)
            .where(Exercise.status == "approved", Exercise.skill_id.in_(unlocked))
            .order_by(Exercise.created_at)
        )
    )
    if not exercises:
        return []
    states = {
        state.exercise_id: state
        for state in db.scalars(select(UserCardState).where(UserCardState.user_id == user.id))
    }
    skill_nodes = {
        node.id: node for node in db.scalars(select(SkillNode).where(SkillNode.id.in_(unlocked)))
    }
    skill_titles = {node_id: node.title for node_id, node in skill_nodes.items()}
    sources = _source_maps(db, exercises)
    rotation = active_rotation(db, user.id)
    now = utcnow()

    due_pairs: list[tuple[UserCardState, Exercise]] = []
    new_exercises: list[Exercise] = []
    for exercise in exercises:
        state = states.get(exercise.id)
        if state is None or state.state == "new":
            new_exercises.append(exercise)
        elif state.due_at is None or state.due_at <= now:
            due_pairs.append((state, exercise))

    due_pairs.sort(key=lambda pair: pair[0].due_at or now)
    selected: list[tuple[Exercise, UserCardState | None]] = [
        (exercise, state) for state, exercise in due_pairs
    ]
    remaining = max(0, limit - len(selected))
    if remaining:
        for exercise in new_exercises[: min(remaining, settings.daily_new_card_limit)]:
            selected.append((exercise, states.get(exercise.id)))

    if rotation is not None:
        selected.sort(
            key=lambda pair: 0
            if _rotation_matches(
                rotation,
                skill_titles.get(pair[0].skill_id or "", ""),
                skill_nodes[pair[0].skill_id].category if pair[0].skill_id in skill_nodes else "",
            )
            else 1
        )

    items: list[dict] = []
    policy = get_policy(db, user.id)
    daily_limit = policy["daily_new_card_limit"]
    for exercise, state in selected[:limit]:
        node = skill_nodes.get(exercise.skill_id or "")
        items.append(
            {
                "exercise_id": exercise.id,
                "skill_id": exercise.skill_id,
                "skill_title": skill_titles.get(exercise.skill_id or ""),
                "type": exercise.type,
                "payload": sanitize_payload(exercise),
                "source": sources.get(exercise.id),
                "state": state.state if state else "new",
                "due_at": state.due_at if state else None,
                "retrievability": compute_retrievability(state, now) if state else None,
                "rotation_match": bool(
                    rotation
                    and _rotation_matches(
                        rotation,
                        skill_titles.get(exercise.skill_id or "", ""),
                        node.category if node else "",
                    )
                ),
            }
        )
    return items


def submit_review(
    db: Session,
    user: User,
    *,
    exercise_id: str,
    answer: dict,
    rating: str | None,
    response_time_ms: int | None,
) -> dict:
    exercise = db.get(Exercise, exercise_id)
    if exercise is None or exercise.status != "approved":
        raise StudyError("Egzersiz bulunamadı veya onaylanmamış")
    if exercise.skill_id:
        if exercise.skill_id not in unlocked_skill_ids(db, user.id):
            raise StudyError("Bu skill henüz kilitli")

    provider = None
    if settings.vignette_llm_eval and exercise.type == "vignette":
        try:
            provider = get_provider()
        except LLMError:
            provider = None
    is_correct, correct_answer, explanation = grade(exercise, answer, provider=provider)
    resolved_rating = rating or ("good" if is_correct else "again")

    state = get_or_create_state(db, user.id, exercise.id)
    before = state_snapshot(state)
    apply_review(db, state, resolved_rating)
    after = state_snapshot(state)
    ability = irt.update_from_review(
        db,
        user_id=user.id,
        exercise=exercise,
        is_correct=is_correct,
    )

    now = utcnow()
    db.add(
        ReviewLog(
            user_id=user.id,
            exercise_id=exercise.id,
            rating=resolved_rating,
            is_correct=is_correct,
            answer=answer,
            response_time_ms=response_time_ms,
            reviewed_at=now,
            state_before=before,
            state_after=after,
        )
    )
    mastery = update_mastery(db, user.id, exercise.skill_id, is_correct)
    xp_awarded = gamification.award_review_xp(db, user.id, resolved_rating, is_correct)
    streak = gamification.touch_streak(db, user.id)
    stats = gamification.get_stats(db, user.id)
    db.commit()

    return {
        "exercise_id": exercise.id,
        "is_correct": is_correct,
        "correct_answer": correct_answer,
        "explanation": explanation,
        "rating": resolved_rating,
        "next_due_at": state.due_at,
        "interval_days": state.interval_days,
        "xp_awarded": xp_awarded,
        "total_xp": stats["total_xp"],
        "current_streak": streak.current_streak,
        "mastery_score": mastery,
        "ability_theta": ability["theta"],
        "ability_se": ability["se"],
        "exercise_difficulty": ability["exercise_difficulty"],
    }


def grade(
    exercise: Exercise,
    answer: dict,
    *,
    provider=None,
) -> tuple[bool, dict | None, str | None]:
    payload = exercise.payload or {}
    if exercise.type == "mcq":
        options = payload.get("options", [])
        correct_indices = [
            index for index, option in enumerate(options) if option.get("is_correct")
        ]
        selected = answer.get("option_index", answer.get("selected_index"))
        if isinstance(selected, list):
            selected = selected[0] if selected else None
        try:
            selected = int(selected) if selected is not None else None
        except (TypeError, ValueError):
            selected = None
        is_correct = selected in correct_indices
        correct = None
        if correct_indices:
            index = correct_indices[0]
            correct = {"option_index": index, "text": options[index].get("text", "")}
        return is_correct, correct, payload.get("explanation")

    if exercise.type == "cloze":
        raw = answer.get("text") or answer.get("answer") or ""
        accepted = {_normalize_answer(payload.get("answer", ""))}
        accepted.update(
            _normalize_answer(alternative) for alternative in payload.get("alternatives", [])
        )
        accepted.discard("")
        is_correct = _normalize_answer(str(raw)) in accepted
        return is_correct, {"text": payload.get("answer", "")}, payload.get("explanation")

    if exercise.type == "matching":
        correct_map = {
            _normalize_answer(pair.get("left", "")): _normalize_answer(pair.get("right", ""))
            for pair in payload.get("pairs", [])
        }
        submitted = answer.get("pairs", {})
        submitted_map: dict[str, str] = {}
        if isinstance(submitted, dict):
            submitted_map = {
                _normalize_answer(str(key)): _normalize_answer(str(value))
                for key, value in submitted.items()
            }
        elif isinstance(submitted, list):
            for item in submitted:
                if isinstance(item, dict) and "left" in item and "right" in item:
                    submitted_map[_normalize_answer(str(item["left"]))] = _normalize_answer(
                        str(item["right"])
                    )
        is_correct = bool(correct_map) and submitted_map == correct_map
        correct_answer = {
            "pairs": [
                {"left": pair.get("left", ""), "right": pair.get("right", "")}
                for pair in payload.get("pairs", [])
            ]
        }
        return is_correct, correct_answer, payload.get("explanation")

    if exercise.type == "vignette":
        raw = answer.get("text") or answer.get("answer") or ""
        result = vignette.evaluate(
            str(raw),
            payload,
            provider=provider,
            pass_score=settings.vignette_pass_score,
        )
        correct_answer = {
            "score": result["score"],
            "criteria": result["criteria"],
            "model_answer": result["model_answer"],
        }
        return result["passed"], correct_answer, result["feedback"]

    raise StudyError(f"Desteklenmeyen egzersiz tipi: {exercise.type}")


def _normalize_answer(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "").casefold()
    value = value.replace("\u0307", "")
    value = re.sub(r"[^\wçğıöşü]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def study_stats(db: Session, user: User) -> dict:
    unlocked = unlocked_skill_ids(db, user.id)
    approved_count = 0
    due_count = 0
    new_count = 0
    if unlocked:
        approved_count = int(
            db.scalar(
                select(func.count(Exercise.id)).where(
                    Exercise.status == "approved", Exercise.skill_id.in_(unlocked)
                )
            )
            or 0
        )
        states = {
            state.exercise_id: state
            for state in db.scalars(select(UserCardState).where(UserCardState.user_id == user.id))
        }
        exercises = db.scalars(
            select(Exercise.id).where(
                Exercise.status == "approved", Exercise.skill_id.in_(unlocked)
            )
        ).all()
        now = utcnow()
        for exercise_id in exercises:
            state = states.get(exercise_id)
            if state is None or state.state == "new":
                new_count += 1
            elif state.due_at is None or state.due_at <= now:
                due_count += 1

    mastered = int(
        db.scalar(
            select(func.count(UserSkillProgress.id)).where(
                UserSkillProgress.user_id == user.id,
                UserSkillProgress.mastery_score >= settings.mastery_threshold,
            )
        )
        or 0
    )
    today_start = datetime.combine(utcnow().date(), time.min)
    reviews_today = int(
        db.scalar(
            select(func.count(ReviewLog.id)).where(
                ReviewLog.user_id == user.id, ReviewLog.reviewed_at >= today_start
            )
        )
        or 0
    )
    stats = gamification.get_stats(db, user.id)
    ability = db.scalar(select(UserAbility).where(UserAbility.user_id == user.id))
    rotation = active_rotation(db, user.id)
    policy = get_policy(db, user.id)
    return {
        "ability_theta": ability.theta if ability else 0.0,
        "ability_se": ability.se if ability else 1.0,
        "rotation": rotation.name if rotation else None,
        "due_count": due_count,
        "new_count": new_count,
        "approved_exercise_count": approved_count,
        "mastered_skill_count": mastered,
        "reviews_today": reviews_today,
        "mastery_threshold": policy["mastery_threshold"],
        "daily_new_card_limit": policy["daily_new_card_limit"],
        **stats,
    }
