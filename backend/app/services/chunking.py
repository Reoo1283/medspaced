from dataclasses import dataclass

from app.services.extraction import ExtractedSection


@dataclass
class ChunkDraft:
    chunk_index: int
    section_title: str
    heading_path: list[str]
    page_number: int | None
    raw_text: str
    token_count: int


def estimate_tokens(text: str) -> int:
    words = len(text.split())
    return max(1, int(words * 1.3))


def chunk_sections(
    sections: list[ExtractedSection],
    max_words: int = 600,
    overlap_words: int = 60,
) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    heading_stack: list[tuple[int, str]] = []

    for section in sections:
        title = section.title.strip()
        level = max(1, min(section.level, 6))
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        if title:
            heading_stack.append((level, title))
        heading_path = [item[1] for item in heading_stack]
        section_title = title or (heading_path[-1] if heading_path else "Bölüm")

        text = section.text.strip()
        if not text:
            continue
        for part in _split_text(text, max_words=max_words, overlap_words=overlap_words):
            chunks.append(
                ChunkDraft(
                    chunk_index=len(chunks),
                    section_title=section_title,
                    heading_path=heading_path,
                    page_number=section.page_number,
                    raw_text=part,
                    token_count=estimate_tokens(part),
                )
            )
    return chunks


def _split_text(text: str, max_words: int, overlap_words: int) -> list[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text.strip()]

    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    segments: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph.split()) <= max_words:
            segments.append(paragraph)
        else:
            segment_words = paragraph.split()
            start = 0
            while start < len(segment_words):
                end = min(start + max_words, len(segment_words))
                segments.append(" ".join(segment_words[start:end]))
                if end == len(segment_words):
                    break
                start = max(end - overlap_words, start + 1)

    chunks: list[str] = []
    buffer: list[str] = []
    buffer_words = 0
    for segment in segments:
        segment_words = len(segment.split())
        if buffer and buffer_words + segment_words > max_words:
            chunks.append("\n\n".join(buffer).strip())
            overlap = " ".join(" ".join(buffer).split()[-overlap_words:])
            buffer = [overlap] if overlap and overlap_words > 0 else []
            buffer_words = len(overlap.split())
        buffer.append(segment)
        buffer_words += segment_words
    if buffer:
        chunks.append("\n\n".join(buffer).strip())
    return [chunk for chunk in chunks if chunk]
