from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
import re


class ExtractionError(Exception):
    pass


@dataclass
class ExtractedSection:
    title: str
    level: int
    text: str
    page_number: int | None = None


@dataclass
class _SectionBuilder:
    title: str = ""
    level: int = 1
    page_number: int | None = None
    parts: list[str] = field(default_factory=list)

    def add(self, text: str, page: int | None = None) -> None:
        if self.page_number is None and page is not None:
            self.page_number = page
        if text:
            self.parts.append(text)

    def build(self) -> ExtractedSection | None:
        text = "\n\n".join(part.strip() for part in self.parts if part.strip()).strip()
        if not text:
            return None
        return ExtractedSection(
            title=self.title.strip(),
            level=max(1, min(self.level, 6)),
            text=text,
            page_number=self.page_number,
        )


def extract_sections(path: Path, filename: str) -> list[ExtractedSection]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix == ".pptx":
        return _extract_pptx(path)
    if suffix in {".md", ".markdown"}:
        return _extract_markdown(path)
    if suffix in {".txt", ".text", ""}:
        return _extract_text(path)
    raise ExtractionError(f"Desteklenmeyen dosya türü: {suffix or 'bilinmiyor'}")


def _extract_pdf(path: Path) -> list[ExtractedSection]:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ExtractionError("PDF çıkarımı için PyMuPDF gerekli") from exc

    document = fitz.open(path)
    try:
        sizes: Counter[float] = Counter()
        pages_text: list[str] = []
        for page in document:
            page_dict = page.get_text("dict")
            page_parts: list[str] = []
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "")
                        if text.strip():
                            sizes[round(float(span.get("size", 10)), 1)] += len(text)
                            page_parts.append(text)
            pages_text.append(" ".join(page_parts))

        full_text = " ".join(pages_text).strip()
        if len(full_text) < 40:
            return _extract_scanned_pdf(document, path)

        body_size = sizes.most_common(1)[0][0] if sizes else 10.0
        sections: list[ExtractedSection] = []
        builder = _SectionBuilder(title=_pdf_title(document, path), level=1)
        page_started = False

        for page_index, page in enumerate(document):
            page_number = page_index + 1
            page_dict = page.get_text("dict")
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                block_text = _pdf_block_text(block)
                if not block_text:
                    continue
                max_size = _pdf_block_max_size(block)
                is_heading = (
                    max_size >= body_size * 1.15
                    and len(block_text) <= 160
                    and len(block_text.split()) <= 18
                    and not block_text.rstrip().endswith((",", ";"))
                )
                if is_heading:
                    built = builder.build()
                    if built and built.text:
                        sections.append(built)
                    level = 1 if max_size >= body_size * 1.55 else 2
                    builder = _SectionBuilder(
                        title=block_text, level=level, page_number=page_number
                    )
                    page_started = True
                else:
                    if not builder.title and not page_started:
                        builder.title = _pdf_title(document, path) or f"Sayfa {page_number}"
                    builder.add(block_text, page_number)
        built = builder.build()
        if built:
            sections.append(built)
        if not sections:
            return _extract_scanned_pdf(document, path)
        return sections
    finally:
        document.close()


def _pdf_title(document, path: Path) -> str:
    metadata = document.metadata or {}
    title = (metadata.get("title") or "").strip()
    return title or path.stem.replace("_", " ").replace("-", " ").strip()


def _pdf_block_text(block: dict) -> str:
    lines: list[str] = []
    for line in block.get("lines", []):
        line_text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
        if line_text:
            lines.append(line_text)
    return " ".join(lines).strip()


def _pdf_block_max_size(block: dict) -> float:
    sizes = [
        float(span.get("size", 0))
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if span.get("text", "").strip()
    ]
    return max(sizes) if sizes else 0.0


_rapidocr_engine = None


def _rapidocr_text(image) -> str:
    global _rapidocr_engine
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR

    if _rapidocr_engine is None:
        _rapidocr_engine = RapidOCR()
    result, _ = _rapidocr_engine(np.asarray(image.convert("RGB")))
    return "\n".join(str(line[1]).strip() for line in result or [] if str(line[1]).strip())


def _pytesseract_text(image) -> str:
    import pytesseract

    try:
        return pytesseract.image_to_string(image, lang="tur+eng").strip()
    except Exception:
        return pytesseract.image_to_string(image, lang="eng").strip()


def _ocr_image(image) -> str:
    errors: list[str] = []
    for engine in (_rapidocr_text, _pytesseract_text):
        try:
            text = engine(image).strip()
        except Exception as exc:
            errors.append(f"{engine.__name__}: {exc}")
            continue
        if text:
            return text
    detail = "; ".join(errors) if errors else "OCR motoru metin bulamadı"
    raise ExtractionError(f"OCR başarısız: {detail}")


def _extract_scanned_pdf(document, path: Path) -> list[ExtractedSection]:
    try:
        import io
        from PIL import Image
    except ImportError as exc:
        raise ExtractionError("Taranmış PDF OCR için Pillow gerekli") from exc

    sections: list[ExtractedSection] = []
    for page_index, page in enumerate(document):
        pixmap = page.get_pixmap(dpi=200)
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        try:
            text = _ocr_image(image)
        except ExtractionError as exc:
            raise ExtractionError(
                f"Sayfa {page_index + 1} OCR başarısız; RapidOCR veya Tesseract kurulmalı: {exc}"
            ) from exc
        if text:
            sections.append(
                ExtractedSection(
                    title=f"{path.stem} — Sayfa {page_index + 1}",
                    level=1,
                    text=text,
                    page_number=page_index + 1,
                )
            )
    if not sections:
        raise ExtractionError("PDF içinden metin çıkarılamadı")
    return sections


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _extract_markdown(path: Path) -> list[ExtractedSection]:
    text = path.read_text(encoding="utf-8", errors="replace")
    sections: list[ExtractedSection] = []
    current: _SectionBuilder | None = None
    for line in text.splitlines():
        match = _HEADING_RE.match(line.strip())
        if match:
            if current is not None:
                built = current.build()
                if built:
                    sections.append(built)
            current = _SectionBuilder(title=match.group(2).strip(), level=len(match.group(1)))
        else:
            if current is None:
                current = _SectionBuilder(title=path.stem, level=1)
            current.add(line)
    if current is not None:
        built = current.build()
        if built:
            sections.append(built)
    if not sections:
        raise ExtractionError("Markdown içeriği boş")
    return sections


def _extract_text(path: Path) -> list[ExtractedSection]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        raise ExtractionError("Metin dosyası boş")
    return [ExtractedSection(title=path.stem, level=1, text=text)]


def _style_heading_level(style_name: str) -> int | None:
    name = (style_name or "").strip().lower()
    if name == "title":
        return 1
    match = re.match(r"heading\s*(\d+)", name)
    if match:
        return int(match.group(1))
    return None


def _extract_docx(path: Path) -> list[ExtractedSection]:
    try:
        from docx import Document
    except ImportError as exc:
        raise ExtractionError("DOCX çıkarımı için python-docx gerekli") from exc

    document = Document(path)
    sections: list[ExtractedSection] = []
    current = _SectionBuilder(title=path.stem, level=1)

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        level = _style_heading_level(paragraph.style.name if paragraph.style else "")
        if level is not None:
            built = current.build()
            if built:
                sections.append(built)
            current = _SectionBuilder(title=text, level=level)
        else:
            current.add(text)

    for table in document.tables:
        rows: list[str] = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            current.add("\n".join(rows))

    built = current.build()
    if built:
        sections.append(built)
    if not sections:
        raise ExtractionError("DOCX içeriği boş")
    return sections


def _extract_pptx(path: Path) -> list[ExtractedSection]:
    try:
        from pptx import Presentation
    except ImportError as exc:
        raise ExtractionError("PPTX çıkarımı için python-pptx gerekli") from exc

    presentation = Presentation(path)
    sections: list[ExtractedSection] = []
    for index, slide in enumerate(presentation.slides):
        title_shape = slide.shapes.title
        title = title_shape.text.strip() if title_shape is not None and title_shape.has_text_frame else ""
        parts: list[str] = []
        for shape in slide.shapes:
            if shape is title_shape or not getattr(shape, "has_text_frame", False):
                continue
            text = shape.text_frame.text.strip()
            if text:
                parts.append(text)
        try:
            notes_frame = slide.notes_slide.notes_text_frame
            notes = notes_frame.text.strip() if notes_frame is not None else ""
        except Exception:
            notes = ""
        if notes:
            parts.append(f"Notlar: {notes}")
        body = "\n\n".join(parts).strip()
        if title or body:
            sections.append(
                ExtractedSection(
                    title=title or f"Slayt {index + 1}",
                    level=1,
                    text=body or title,
                    page_number=index + 1,
                )
            )
    if not sections:
        raise ExtractionError("PPTX içeriği boş")
    return sections
