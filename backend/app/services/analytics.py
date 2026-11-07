from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import mean

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Exercise, ReviewLog, User, UserSkillProgress
from app.services.learning_policy import get_policy


def _window_start(days: int) -> datetime:
    return datetime.combine(datetime.utcnow().date(), datetime.min.time()) - timedelta(days=days)


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
    return round(covariance / (variance_x * variance_y) ** 0.5, 4)


def learning_metrics(db: Session, user: User) -> dict:
    """Return learning output metrics for a user."""
    window_start = _window_start(30)
    window_start_14 = _window_start(14)

    # All-time logs
    all_logs = list(
        db.scalars(
            select(ReviewLog)
            .where(ReviewLog.user_id == user.id)
            .order_by(ReviewLog.reviewed_at)
        ).all()
    )
    # 30-day window logs
    window_logs = [log for log in all_logs if log.reviewed_at >= window_start]
    total_reviews = len(all_logs)
    window_reviews = len(window_logs)

    correct_reviews = sum(1 for log in window_logs if log.is_correct)
    lapse_reviews = sum(1 for log in window_logs if log.rating == "again")
    retention = round(correct_reviews / window_reviews, 4) if window_reviews > 0 else 0.0
    lapse_rate = round(lapse_reviews / window_reviews, 4) if window_reviews > 0 else 0.0

    # Daily counts for last 14 days
    daily_counts: dict[date, int] = {}
    for log in window_logs:
        if log.reviewed_at >= window_start_14:
            day = log.reviewed_at.date()
            daily_counts[day] = daily_counts.get(day, 0) + 1
    daily_reviews = [
        {"date": str(window_start_14.date() + timedelta(days=i)), "count": daily_counts.get(window_start_14.date() + timedelta(days=i), 0)}
        for i in range(14)
    ]

    # Calibration curve: bin by predicted retrievability (state_before.retrievability)
    bins = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]
    calibration = []
    for low, high in bins:
        bin_logs = [
            log
            for log in window_logs
            if log.state_before
            and isinstance(log.state_before.get("retrievability"), (int, float))
            and low <= log.state_before["retrievability"] < high
        ]
        if not bin_logs:
            calibration.append({"predicted_range": f"{low:.1f}-{high:.1f}", "avg_predicted": None, "actual_accuracy": None, "count": 0})
            continue
        avg_predicted = round(mean(log.state_before["retrievability"] for log in bin_logs), 4)
        actual_correct = sum(1 for log in bin_logs if log.is_correct)
        actual_accuracy = round(actual_correct / len(bin_logs), 4)
        calibration.append(
            {
                "predicted_range": f"{low:.1f}-{high:.1f}",
                "avg_predicted": avg_predicted,
                "actual_accuracy": actual_accuracy,
                "count": len(bin_logs),
            }
        )

    # Exam readiness
    policy = get_policy(db, user.id)
    unlocked = list(
        db.scalars(
            select(UserSkillProgress.skill_id).where(
                UserSkillProgress.user_id == user.id,
                UserSkillProgress.mastery_score >= policy["mastery_threshold"],
            )
        ).all()
    )
    unlocked_ids = set(unlocked)
    approved_total = int(
        db.scalar(
            select(func.count(Exercise.id)).where(Exercise.status == "approved")
        )
        or 0
    )
    reviewed_distinct = set()
    for log in window_logs:
        reviewed_distinct.add(log.exercise_id)
    coverage = round(len(reviewed_distinct) / approved_total, 4) if approved_total > 0 else 0.0
    mastery_avg = round(
        mean(
            float(progress.mastery_score)
            for progress in db.scalars(
                select(UserSkillProgress).where(UserSkillProgress.user_id == user.id)
            ).all()
        )
        if unlocked else 0.0,
        4,
    )
    readiness = round(100 * (0.45 * (mastery_avg / 100) + 0.35 * retention + 0.2 * coverage), 1)

    return {
        "reviews_total": total_reviews,
        "reviews_last_30d": window_reviews,
        "retention": retention,
        "lapse_rate": lapse_rate,
        "exam_readiness": readiness,
        "readiness_components": {
            "mastery_avg": mastery_avg,
            "retention": retention,
            "coverage": coverage,
        },
        "calibration": calibration,
        "daily_reviews": daily_reviews,
    }


def difficulty_calibration_report(db: Session) -> dict:
    """Compare reviewer approval difficulty with current IRT difficulty."""
    approved_exercises = list(
        db.scalars(
            select(Exercise).where(Exercise.status == "approved")
        ).all()
    )

    items = []
    for ex in approved_exercises:
        attempts = int(
            db.scalar(
                select(func.count(ReviewLog.id)).where(ReviewLog.exercise_id == ex.id)
            )
            or 0
        )
        approval_diff = ex.difficulty_at_approval
        current_diff = ex.difficulty
        deviation = None
        abs_deviation = None
        if approval_diff is not None and attempts > 0:
            deviation = round(current_diff - approval_diff, 4)
            abs_deviation = round(abs(deviation), 4)
        items.append(
            {
                "exercise_id": ex.id,
                "skill_id": ex.skill_id,
                "type": ex.type,
                "attempts": attempts,
                "approval_difficulty": approval_diff,
                "current_difficulty": current_diff,
                "deviation": deviation,
                "abs_deviation": abs_deviation,
            }
        )

    with_baseline = [item for item in items if item["deviation"] is not None]
    if with_baseline:
        mean_deviation = round(mean(item["deviation"] for item in with_baseline), 4)
        mean_abs = round(mean(item["abs_deviation"] for item in with_baseline), 4)
        max_abs = round(max(item["abs_deviation"] for item in with_baseline), 4)
    else:
        mean_deviation = mean_abs = max_abs = None

    high_dev = [item for item in with_baseline if item["abs_deviation"] >= 0.15]
    high_dev.sort(key=lambda x: x["abs_deviation"], reverse=True)

    return {
        "reviewed_items": len(items),
        "items_with_baseline": len(with_baseline),
        "mean_deviation": mean_deviation,
        "mean_absolute_deviation": mean_abs,
        "max_absolute_deviation": max_abs,
        "high_deviation_count": len(high_dev),
        "high_deviation_threshold": 0.15,
        "high_deviation_items": high_dev[:20],
    }