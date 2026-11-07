from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class SkillNode(Base, IdMixin, TimestampMixin):
    __tablename__ = "skill_nodes"

    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), default="genel", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("skill_nodes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("content_chunks.id", ondelete="SET NULL"), nullable=True
    )


class SkillPrerequisite(Base, IdMixin):
    __tablename__ = "skill_prerequisites"
    __table_args__ = (
        UniqueConstraint("skill_id", "prerequisite_id", name="uq_skill_prerequisite"),
    )

    skill_id: Mapped[str] = mapped_column(
        ForeignKey("skill_nodes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    prerequisite_id: Mapped[str] = mapped_column(
        ForeignKey("skill_nodes.id", ondelete="CASCADE"), index=True, nullable=False
    )


class SkillConcept(Base, IdMixin):
    __tablename__ = "skill_concepts"
    __table_args__ = (UniqueConstraint("skill_id", "concept_id", name="uq_skill_concept"),)

    skill_id: Mapped[str] = mapped_column(
        ForeignKey("skill_nodes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    concept_id: Mapped[str] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), index=True, nullable=False
    )
