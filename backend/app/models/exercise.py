from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class Concept(Base, IdMixin, TimestampMixin):
    __tablename__ = "concepts"
    __table_args__ = (
        UniqueConstraint("chunk_id", "normalized_term", name="uq_concept_chunk_term"),
    )

    chunk_id: Mapped[str] = mapped_column(
        ForeignKey("content_chunks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    term: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_term: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), default="genel")
    key_facts: Mapped[list | None] = mapped_column(JSON, default=list)


class Exercise(Base, IdMixin, TimestampMixin):
    __tablename__ = "exercises"

    skill_id: Mapped[str | None] = mapped_column(
        ForeignKey("skill_nodes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    concept_id: Mapped[str | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    difficulty: Mapped[float] = mapped_column(Float, default=0.5)
    difficulty_at_approval: Mapped[float | None] = mapped_column(Float, nullable=True)
    discrimination: Mapped[float] = mapped_column(Float, default=1.0)
    guessing: Mapped[float] = mapped_column(Float, default=0.25)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    source_chunk_id: Mapped[str] = mapped_column(
        ForeignKey("content_chunks.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    created_by_ai: Mapped[bool] = mapped_column(Boolean, default=True)
    generation_meta: Mapped[dict | None] = mapped_column(JSON, default=dict)
    dedupe_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    reviewed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExerciseReviewEvent(Base, IdMixin):
    __tablename__ = "exercise_review_events"

    exercise_id: Mapped[str] = mapped_column(
        ForeignKey("exercises.id", ondelete="CASCADE"), index=True, nullable=False
    )
    reviewer_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
