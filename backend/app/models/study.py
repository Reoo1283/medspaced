from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class UserSkillProgress(Base, IdMixin, TimestampMixin):
    __tablename__ = "user_skill_progress"
    __table_args__ = (UniqueConstraint("user_id", "skill_id", name="uq_user_skill_progress"),)

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("skill_nodes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    mastery_score: Mapped[float] = mapped_column(Float, default=0.0)
    last_practiced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserCardState(Base, IdMixin, TimestampMixin):
    __tablename__ = "user_card_state"
    __table_args__ = (UniqueConstraint("user_id", "exercise_id", name="uq_user_card_state"),)

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    exercise_id: Mapped[str] = mapped_column(
        ForeignKey("exercises.id", ondelete="CASCADE"), index=True, nullable=False
    )
    scheduler: Mapped[str] = mapped_column(String(20), default="sm2", nullable=False)
    difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    stability: Mapped[float | None] = mapped_column(Float, nullable=True)
    retrievability: Mapped[float | None] = mapped_column(Float, nullable=True)
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    lapse_count: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String(20), default="new")
    last_review_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fsrs_card: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class UserLearningSettings(Base, IdMixin, TimestampMixin):
    __tablename__ = "user_learning_settings"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    desired_retention: Mapped[float] = mapped_column(Float, default=0.9)
    fsrs_parameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reviews_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    lapse_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    optimized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    mastery_threshold: Mapped[float] = mapped_column(Float, default=70.0)
    daily_new_card_limit: Mapped[int] = mapped_column(Integer, default=20)


class ReviewLog(Base, IdMixin):
    __tablename__ = "review_logs"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    exercise_id: Mapped[str] = mapped_column(
        ForeignKey("exercises.id", ondelete="CASCADE"), index=True, nullable=False
    )
    rating: Mapped[str] = mapped_column(String(10), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    answer: Mapped[dict | None] = mapped_column(JSON, default=dict)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    state_before: Mapped[dict | None] = mapped_column(JSON, default=dict)
    state_after: Mapped[dict | None] = mapped_column(JSON, default=dict)


class UserAbility(Base, IdMixin, TimestampMixin):
    __tablename__ = "user_ability"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    theta: Mapped[float] = mapped_column(Float, default=0.0)
    se: Mapped[float] = mapped_column(Float, default=1.0)


class UserAbilityDimension(Base, IdMixin, TimestampMixin):
    __tablename__ = "user_ability_dimensions"
    __table_args__ = (
        UniqueConstraint("user_id", "dimension", name="uq_user_ability_dimension"),
    )

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    theta: Mapped[float] = mapped_column(Float, default=0.0)
    se: Mapped[float] = mapped_column(Float, default=1.0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class SrsMigrationAudit(Base, IdMixin):
    __tablename__ = "srs_migration_audits"

    batch_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    card_id: Mapped[str] = mapped_column(
        ForeignKey("user_card_state.id", ondelete="CASCADE"), index=True, nullable=False
    )
    before_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    after_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="applied", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserRotation(Base, IdMixin, TimestampMixin):
    __tablename__ = "user_rotations"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
