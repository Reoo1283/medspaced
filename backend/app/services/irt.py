from __future__ import annotations

import math
from itertools import combinations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Exercise, ReviewLog, SkillNode, UserAbility, UserAbilityDimension

MIN_DIFFICULTY = 0.05
MAX_DIFFICULTY = 0.95
MIN_THETA = -4.0
MAX_THETA = 4.0
MAX_GUESSING = 0.6
DIMENSION_FALLBACK = "genel"


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _sigmoid(value: float) -> float:
    if value >= 0:
        exponent = math.exp(-value)
        return 1.0 / (1.0 + exponent)
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)


def difficulty_to_b(difficulty: float) -> float:
    probability = _clamp(difficulty, MIN_DIFFICULTY, MAX_DIFFICULTY)
    return math.log(probability / (1.0 - probability))


def b_to_difficulty(b: float) -> float:
    return _clamp(_sigmoid(b), MIN_DIFFICULTY, MAX_DIFFICULTY)


def _model() -> str:
    return settings.irt_model


def item_probability(theta: float, exercise: Exercise, model: str | None = None) -> float:
    """Probability of a correct response under 2PL, 3PL or MIRT item loading."""
    model = model or _model()
    discrimination = max(0.3, float(exercise.discrimination or 1.0))
    difficulty_b = difficulty_to_b(exercise.difficulty)
    core = _sigmoid(discrimination * (theta - difficulty_b))
    if model == "2pl":
        return core
    guessing = _clamp(float(exercise.guessing or 0.0), 0.0, MAX_GUESSING)
    return guessing + (1.0 - guessing) * core


def get_or_create_ability(db: Session, user_id: str) -> UserAbility:
    ability = db.scalar(select(UserAbility).where(UserAbility.user_id == user_id))
    if ability is None:
        ability = UserAbility(user_id=user_id, theta=0.0, se=1.0)
        db.add(ability)
        db.flush()
    return ability


def get_or_create_dimension(
    db: Session, user_id: str, dimension: str
) -> UserAbilityDimension:
    row = db.scalar(
        select(UserAbilityDimension).where(
            UserAbilityDimension.user_id == user_id,
            UserAbilityDimension.dimension == dimension,
        )
    )
    if row is None:
        row = UserAbilityDimension(
            user_id=user_id,
            dimension=dimension,
            theta=0.0,
            se=1.0,
            attempts=0,
        )
        db.add(row)
        db.flush()
    return row


def exercise_dimension(db: Session, exercise: Exercise) -> str:
    if not exercise.skill_id:
        return DIMENSION_FALLBACK
    skill = db.get(SkillNode, exercise.skill_id)
    if skill is None or not (skill.category or "").strip():
        return DIMENSION_FALLBACK
    return skill.category.strip().lower()


def update_from_review(
    db: Session,
    *,
    user_id: str,
    exercise: Exercise,
    is_correct: bool,
) -> dict:
    ability = get_or_create_ability(db, user_id)
    user_attempts = int(
        db.scalar(select(func.count(ReviewLog.id)).where(ReviewLog.user_id == user_id)) or 0
    )
    item_attempts = int(
        db.scalar(
            select(func.count(ReviewLog.id)).where(ReviewLog.exercise_id == exercise.id)
        )
        or 0
    )

    model = _model()
    theta = _clamp(ability.theta, MIN_THETA, MAX_THETA)
    difficulty_b = difficulty_to_b(exercise.difficulty)
    expected = item_probability(theta, exercise, model)
    score = 1.0 if is_correct else 0.0
    residual = score - expected

    user_step = max(0.05, 0.45 / (1.0 + 0.15 * user_attempts))
    ability.theta = round(_clamp(theta + user_step * residual, MIN_THETA, MAX_THETA), 4)
    ability.se = round(max(0.15, ability.se * 0.9), 4)

    item_step = max(0.02, 0.25 / (1.0 + 0.2 * item_attempts))
    calibrated_b = difficulty_b - item_step * residual
    exercise.difficulty = round(b_to_difficulty(calibrated_b), 4)

    dimension: str | None = None
    dimension_theta: float | None = None
    if model == "mirt":
        dimension = exercise_dimension(db, exercise)
        row = get_or_create_dimension(db, user_id, dimension)
        dim_theta = _clamp(row.theta, MIN_THETA, MAX_THETA)
        dim_expected = item_probability(dim_theta, exercise, "3pl")
        dim_residual = score - dim_expected
        dim_step = max(0.04, 0.35 / (1.0 + 0.15 * row.attempts))
        row.theta = round(
            _clamp(dim_theta + dim_step * dim_residual, MIN_THETA, MAX_THETA), 4
        )
        row.se = round(max(0.15, row.se * 0.92), 4)
        row.attempts += 1
        dimension_theta = row.theta

    db.flush()

    return {
        "theta": ability.theta,
        "se": ability.se,
        "exercise_difficulty": exercise.difficulty,
        "expected_correct": round(expected, 4),
        "model": model,
        "dimension": dimension,
        "dimension_theta": dimension_theta,
    }


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    count = len(xs)
    if count < 2:
        return None
    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    variance_x = sum((x - mean_x) ** 2 for x in xs)
    variance_y = sum((y - mean_y) ** 2 for y in ys)
    if variance_x <= 0 or variance_y <= 0:
        return None
    return round(covariance / math.sqrt(variance_x * variance_y), 4)


def dimension_correlations(db: Session) -> list[dict]:
    rows = db.execute(
        select(
            UserAbilityDimension.dimension,
            UserAbilityDimension.user_id,
            UserAbilityDimension.theta,
        )
    ).all()
    by_dimension: dict[str, dict[str, float]] = {}
    for dimension, user_id, theta in rows:
        by_dimension.setdefault(dimension, {})[user_id] = float(theta)
    results: list[dict] = []
    for left, right in combinations(sorted(by_dimension), 2):
        shared = sorted(set(by_dimension[left]) & set(by_dimension[right]))
        xs = [by_dimension[left][user_id] for user_id in shared]
        ys = [by_dimension[right][user_id] for user_id in shared]
        results.append(
            {
                "dimension_a": left,
                "dimension_b": right,
                "r": _pearson(xs, ys),
                "n": len(shared),
            }
        )
    return results


def ability_profile(db: Session, user_id: str) -> dict:
    ability = db.scalar(select(UserAbility).where(UserAbility.user_id == user_id))
    dimensions = list(
        db.scalars(
            select(UserAbilityDimension)
            .where(UserAbilityDimension.user_id == user_id)
            .order_by(UserAbilityDimension.dimension)
        )
    )
    return {
        "model": _model(),
        "theta": ability.theta if ability else 0.0,
        "se": ability.se if ability else 1.0,
        "dimensions": [
            {
                "dimension": row.dimension,
                "theta": row.theta,
                "se": row.se,
                "attempts": row.attempts,
            }
            for row in dimensions
        ],
        "correlations": dimension_correlations(db),
    }
