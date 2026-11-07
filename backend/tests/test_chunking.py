from app.services.chunking import chunk_sections, estimate_tokens
from app.services.extraction import ExtractedSection


def test_short_section_single_chunk():
    sections = [ExtractedSection(title="Giriş", level=1, text="Kısa bir metin.", page_number=1)]
    chunks = chunk_sections(sections)
    assert len(chunks) == 1
    assert chunks[0].section_title == "Giriş"
    assert chunks[0].page_number == 1
    assert chunks[0].chunk_index == 0


def test_long_section_is_split_with_overlap():
    text = " ".join(f"kelime{i}" for i in range(700))
    sections = [ExtractedSection(title="Uzun", level=1, text=text)]
    chunks = chunk_sections(sections, max_words=300, overlap_words=30)
    assert len(chunks) >= 2
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(len(chunk.raw_text.split()) <= 330 for chunk in chunks)


def test_heading_path_nested():
    sections = [
        ExtractedSection(title="Anestezi", level=1, text="Ana bölüm metni."),
        ExtractedSection(title="İndüksiyon", level=2, text="Alt bölüm metni."),
    ]
    chunks = chunk_sections(sections)
    assert chunks[0].heading_path == ["Anestezi"]
    assert chunks[1].heading_path == ["Anestezi", "İndüksiyon"]
    assert chunks[1].section_title == "İndüksiyon"


def test_estimate_tokens_positive():
    assert estimate_tokens("bir iki üç") >= 1
    assert estimate_tokens("") >= 1
