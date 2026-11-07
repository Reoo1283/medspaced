from __future__ import annotations

import base64
import calendar
import hashlib
import hmac
import json
import random
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Exercise, SkillNode, User, utcnow
from app.services import gamification, irt
from app.services.llm import LLMError, get_provider
from app.services.study import grade, sanitize_payload


class ExamError(Exception):
    pass


def _encode(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    signature = hmac.new(settings.secret_key.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{token}.{signature}"


def _decode(token: str) -> dict:
    try:
        encoded, signature = token.split(".", 1)
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        expected = hmac.new(
            settings.secret_key.encode("utf-8"), raw, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("imza")
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ExamError("Geçersiz sınav oturumu") from exc
    if not isinstance(payload, dict) or not payload.get("ids"):
        raise ExamError("Geçersiz sınav oturumu")
    return payload


def _question(exercise: Exercise, skills: dict[str, SkillNode]) -> dict:
    skill = skills.get(exercise.skill_id or "")
    return {
        "exercise_id": exercise.id,
        "skill_id": exercise.skill_id,
        "skill_title": skill.title if skill else None,
        "type": exercise.type,
        "payload": sanitize_payload(exercise),
    }


def start_exam(
    db: Session,
    user: User,
    *,
    skill_ids: list[str],
    count: int,
    duration_minutes: int,
) -> dict:
    statement = select(Exercise).where(Exercise.status == "approved")
    if skill_ids:
        statement = statement.where(Exercise.skill_id.in_(skill_ids))
    exercises = list(db.scalars(statement).all())
    if not exercises:
        raise ExamError("Sınav için onaylı soru bulunamadı")
    selected = random.SystemRandom().sample(exercises, min(count, len(exercises)))
    skills = {
        skill.id: skill
        for skill in db.scalars(
            select(SkillNode).where(
                SkillNode.id.in_({item.skill_id for item in selected if item.skill_id})
            )
        ).all()
    }
    started = utcnow()
    expires = started + timedelta(minutes=duration_minutes)
    ids = [exercise.id for exercise in selected]
    token = _encode(
        {
            "uid": user.id,
            "ids": ids,
            "exp": calendar.timegm(expires.utctimetuple()),
            "start": calendar.timegm(started.utctimetuple()),
        }
    )
    return {
        "session_id": token,
        "started_at": started,
        "expires_at": expires,
        "duration_minutes": duration_minutes,
        "questions": [_question(exercise, skills) for exercise in selected],
    }


def submit_exam(db: Session, user: User, *, session_id: str, answers: list[dict]) -> dict:
    payload = _decode(session_id)
    if payload.get("uid") != user.id:
        raise ExamError("Sınav oturumu bu kullanıcıya ait değil")
    now = utcnow()
    if calendar.timegm(now.utctimetuple()) > int(payload.get("exp", 0)):
        raise ExamError("Sınav süresi doldu")

    ids = [str(item) for item in payload["ids"]]
    exercises = {
        exercise.id: exercise
        for exercise in db.scalars(select(Exercise).where(Exercise.id.in_(ids))).all()
    }
    submitted = {str(item.get("exercise_id")): item for item in answers}
    provider = None
    if settings.vignette_llm_eval:
        try:
            provider = get_provider()
        except LLMError:
            provider = None

    details = []
    correct_count = 0
    xp_awarded = 0
    for exercise_id in ids:
        exercise = exercises.get(exercise_id)
        if exercise is None:
            continue
        entry = submitted.get(exercise_id)
        is_correct = False
        correct_answer = None
        explanation = None
        score = None
        if entry is not None:
            is_correct, correct_answer, explanation = grade(
                exercise, entry.get("answer", {}) or {}, provider=provider
            )
            if correct_answer and "score" in correct_answer:
                score = correct_answer["score"]
            irt.update_from_review(db, user_id=user.id, exercise=exercise, is_correct=is_correct)
            xp_awarded += gamification.award_review_xp(
                db, user.id, "good" if is_correct else "again", is_correct
            )
        if is_correct:
            correct_count += 1
        details.append(
            {
                "exercise_id": exercise_id,
                "is_correct": is_correct,
                "correct_answer": correct_answer,
                "explanation": explanation,
                "score": score,
            }
        )
    if not details:
        raise ExamError("Sınav soruları bulunamadı")
    gamification.touch_streak(db, user.id)
    stats = gamification.get_stats(db, user.id)
    db.commit()
    total = len(details)
    return {
        "score": round(correct_count / total * 100, 2),
        "correct_count": correct_count,
        "total": total,
        "xp_awarded": xp_awarded,
        "total_xp": stats["total_xp"],
        "league": stats["league"],
        "current_streak": stats["current_streak"],
        "duration_seconds": max(0, calendar.timegm(now.utctimetuple()) - int(payload["start"])),
        "details": details,
    }
