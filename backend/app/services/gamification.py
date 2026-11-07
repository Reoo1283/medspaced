from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UserStreak, UserXP, utcnow

XP_BASE = 10
XP_CORRECT = 5
RATING_BONUS = {"again": 0, "hard": 1, "good": 2, "easy": 3}

LEAGUE_TIERS = (
    ("bronz", 0),
    ("gümüş", 100),
    ("altın", 300),
    ("platin", 700),
)


def league_for(weekly_xp: int) -> str:
    league = LEAGUE_TIERS[0][0]
    for name, threshold in LEAGUE_TIERS:
        if weekly_xp >= threshold:
            league = name
    return league


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def award_review_xp(db: Session, user_id: str, rating: str, is_correct: bool) -> int:
    amount = XP_BASE + (XP_CORRECT if is_correct else 0) + RATING_BONUS.get(rating, 0)
    xp = db.scalar(select(UserXP).where(UserXP.user_id == user_id))
    today = utcnow().date()
    if xp is None:
        xp = UserXP(
            user_id=user_id,
            total_xp=0,
            weekly_xp=0,
            week_start=_week_start(today),
            league="bronz",
        )
        db.add(xp)
    if xp.week_start != _week_start(today):
        xp.week_start = _week_start(today)
        xp.weekly_xp = 0
    xp.total_xp += amount
    xp.weekly_xp += amount
    xp.league = league_for(xp.weekly_xp)
    db.flush()
    return amount


def touch_streak(db: Session, user_id: str) -> UserStreak:
    streak = db.scalar(select(UserStreak).where(UserStreak.user_id == user_id))
    today = utcnow().date()
    if streak is None:
        streak = UserStreak(
            user_id=user_id,
            current_streak=1,
            longest_streak=1,
            last_active_date=today,
        )
        db.add(streak)
        db.flush()
        return streak

    if streak.last_active_date == today:
        return streak
    if streak.last_active_date is not None and (today - streak.last_active_date).days == 1:
        streak.current_streak += 1
    else:
        streak.current_streak = 1
    streak.last_active_date = today
    streak.longest_streak = max(streak.longest_streak, streak.current_streak)
    db.flush()
    return streak


def get_stats(db: Session, user_id: str) -> dict:
    xp = db.scalar(select(UserXP).where(UserXP.user_id == user_id))
    streak = db.scalar(select(UserStreak).where(UserStreak.user_id == user_id))
    return {
        "total_xp": xp.total_xp if xp else 0,
        "weekly_xp": xp.weekly_xp if xp else 0,
        "league": xp.league if xp else "bronz",
        "current_streak": streak.current_streak if streak else 0,
        "longest_streak": streak.longest_streak if streak else 0,
        "last_active_date": streak.last_active_date if streak else None,
    }
