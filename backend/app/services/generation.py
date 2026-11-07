from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Callable
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Concept,
    ContentChunk,
    Exercise,
    ExerciseReviewEvent,
    SkillConcept,
    SkillNode,
    utcnow,
)
from app.services.llm import PROMPT_VERSION, LLMProvider, get_provider
from app.services.llm_schemas import ExerciseDraft


class GenerationError(Exception):
    pass


def normalize_term(text: str) -> str:
    value = re.sub(r"\s+", " ", text).strip().casefold()
    value = re.sub(r"[^\wçğıöşü\s\-]", "", value, flags=re.UNICODE)
    return value[:255]


def _dedupe_hash(draft: ExerciseDraft) -> str:
    if draft.type == "mcq":
        key = f"mcq|{normalize_term(draft.stem)}"
    elif draft.type == "cloze":
        key = f"cloze|{normalize_term(draft.text)}"
    elif draft.type == "matching":
        lefts = "|".join(sorted(normalize_term(pair.left) for pair in draft.pairs))
        key = f"matching|{lefts}"
    elif draft.type == "vignette":
        key = f"vignette|{normalize_term(draft.vignette)}|{normalize_term(draft.prompt)}"
    else:  # pragma: no cover - schema guard
        key = f"{draft.type}|{normalize_term(str(draft))}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def generate_for_file(
    db: Session,
    *,
    file_id: str,
    skill_id: str,
    exercise_types: list[str],
    max_chunks: int | None = None,
    progress: Callable[[int, str], None] | None = None,
    provider: LLMProvider | None = None,
) -> dict:
    skill = db.get(SkillNode, skill_id)
    if skill is None:
        raise GenerationError("Skill bulunamadı")

    limit = min(max_chunks or settings.max_chunks_per_generation, settings.max_chunks_per_generation)
    chunks = list(
        db.scalars(
            select(ContentChunk)
            .where(ContentChunk.file_id == file_id)
            .order_by(ContentChunk.chunk_index)
            .limit(limit)
        )
    )
    if not chunks:
        raise GenerationError("Bu dosya için işlenmiş chunk bulunamadı")

    llm = provider or get_provider()
    concepts_created = 0
    exercises_created = 0
    skipped = 0
    errors: list[str] = []

    for index, chunk in enumerate(chunks, start=1):
        try:
            extraction = llm.extract_concepts(chunk)
        except Exception as exc:
            errors.append(f"chunk {chunk.chunk_index + 1}: kavram çıkarımı başarısız: {exc}")
            skipped += 1
            _report(progress, int(index / len(chunks) * 100), f"{index}/{len(chunks)} chunk")
            continue

        for candidate in extraction.concepts:
            normalized = normalize_term(candidate.term)
            if not normalized:
                skipped += 1
                continue
            concept = db.scalar(
                select(Concept).where(
                    Concept.chunk_id == chunk.id,
                    Concept.normalized_term == normalized,
                )
            )
            if concept is None:
                concept = Concept(
                    chunk_id=chunk.id,
                    term=candidate.term.strip()[:255],
                    normalized_term=normalized,
                    category=(candidate.category or "genel").strip()[:100],
                    key_facts=[fact.strip() for fact in candidate.key_facts if fact.strip()][:10],
                )
                db.add(concept)
                db.flush()
                concepts_created += 1
            else:
                concept.key_facts = [fact.strip() for fact in candidate.key_facts if fact.strip()][:10]

            link = db.scalar(
                select(SkillConcept).where(
                    SkillConcept.skill_id == skill_id,
                    SkillConcept.concept_id == concept.id,
                )
            )
            if link is None:
                db.add(SkillConcept(skill_id=skill_id, concept_id=concept.id))

            try:
                generated = llm.generate_exercises(chunk, candidate, exercise_types)
            except Exception as exc:
                errors.append(
                    f"chunk {chunk.chunk_index + 1}, '{candidate.term}': soru üretimi başarısız: {exc}"
                )
                skipped += 1
                continue

            for draft in generated.exercises:
                draft.source_chunk_id = chunk.id
                dedupe = _dedupe_hash(draft)
                if db.scalar(select(Exercise.id).where(Exercise.dedupe_hash == dedupe)) is not None:
                    skipped += 1
                    continue
                exercise = Exercise(
                    skill_id=skill_id,
                    concept_id=concept.id,
                    type=draft.type,
                    payload=draft.model_dump(mode="json"),
                    difficulty=draft.difficulty,
                    status="under_review",
                    source_chunk_id=chunk.id,
                    created_by_ai=True,
                    generation_meta={
                        "provider": llm.name,
                        "model": llm.model,
                        "prompt_version": PROMPT_VERSION,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "chunk_id": chunk.id,
                    },
                    dedupe_hash=dedupe,
                )
                db.add(exercise)
                db.flush()
                db.add(
                    ExerciseReviewEvent(
                        exercise_id=exercise.id,
                        reviewer_id=None,
                        action="submitted",
                        note="Otomatik doğrulama geçti; uzman incelemesine gönderildi.",
                        created_at=utcnow(),
                    )
                )
                exercises_created += 1
        db.flush()
        _report(progress, int(index / len(chunks) * 100), f"{index}/{len(chunks)} chunk")

    db.commit()
    return {
        "chunks_processed": len(chunks),
        "concepts_created": concepts_created,
        "exercises_created": exercises_created,
        "skipped": skipped,
        "errors": errors[:20],
        "provider": llm.name,
        "model": llm.model,
    }


def _report(progress: Callable[[int, str], None] | None, percent: int, message: str) -> None:
    if progress is not None:
        progress(min(100, max(0, percent)), message)
