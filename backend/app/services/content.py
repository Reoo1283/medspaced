from __future__ import annotations

import hashlib
from pathlib import Path
import uuid

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ContentChunk, ContentFile, Exercise, utcnow
from app.services.chunking import chunk_sections
from app.services.extraction import ExtractionError, extract_sections

ALLOWED_SUFFIXES = {".pdf", ".docx", ".pptx", ".md", ".markdown", ".txt", ".text"}
CHUNK_SIZE = 1024 * 1024


class ContentError(Exception):
    pass


def store_upload(upload: UploadFile, original_name: str) -> tuple[Path, int, str]:
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ContentError(f"Desteklenmeyen dosya türü: {suffix or 'bilinmiyor'}")
    if not upload.file:
        raise ContentError("Dosya akışı bulunamadı")

    target = settings.storage_path / f"{uuid.uuid4().hex}{suffix}"
    checksum = hashlib.sha256()
    size = 0
    with target.open("wb") as output:
        while True:
            block = upload.file.read(CHUNK_SIZE)
            if not block:
                break
            size += len(block)
            if size > settings.max_upload_mb * 1024 * 1024:
                output.close()
                target.unlink(missing_ok=True)
                raise ContentError(
                    f"Dosya boyutu {settings.max_upload_mb} MB sınırını aşıyor"
                )
            checksum.update(block)
            output.write(block)
    if size == 0:
        target.unlink(missing_ok=True)
        raise ContentError("Boş dosya yüklenemez")
    return target, size, checksum.hexdigest()


def process_file(db: Session, content_file: ContentFile) -> dict:
    if content_file.status == "processing":
        raise ContentError("Bu dosya zaten işleniyor")

    exercise_count = db.scalar(
        select(func.count(Exercise.id)).where(
            Exercise.source_chunk_id.in_(
                select(ContentChunk.id).where(ContentChunk.file_id == content_file.id)
            )
        )
    )
    if exercise_count:
        raise ContentError(
            "Bu dosyadan üretilmiş sorular var. Yeniden işlemek için önce ilgili soruları silin."
        )

    content_file.status = "processing"
    content_file.error_message = None
    db.commit()

    try:
        path = Path(content_file.storage_path)
        if not path.exists():
            raise ContentError("Dosya diskte bulunamadı")
        sections = extract_sections(path, content_file.filename)
        if not sections:
            raise ExtractionError("Dosyadan hiç bölüm çıkarılamadı")
        drafts = chunk_sections(sections)
        if not drafts:
            raise ExtractionError("Dosyadan hiç chunk üretilemedi")

        db.query(ContentChunk).filter(ContentChunk.file_id == content_file.id).delete(
            synchronize_session=False
        )
        for draft in drafts:
            db.add(
                ContentChunk(
                    file_id=content_file.id,
                    chunk_index=draft.chunk_index,
                    section_title=draft.section_title[:512],
                    heading_path=draft.heading_path,
                    page_number=draft.page_number,
                    raw_text=draft.raw_text,
                    token_count=draft.token_count,
                )
            )
        content_file.status = "extracted"
        content_file.processed_at = utcnow()
        db.commit()
        return {
            "chunks": len(drafts),
            "sections": len(sections),
            "pages": max((section.page_number or 0) for section in sections),
        }
    except Exception as exc:
        db.rollback()
        content_file.status = "failed"
        content_file.error_message = str(exc)[:2000]
        db.commit()
        raise
