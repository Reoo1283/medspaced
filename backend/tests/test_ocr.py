from pathlib import Path

import pytest

from app.services.extraction import ExtractionError, _ocr_image, extract_sections


def _image():
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1000, 260), "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 90), "MEDSPACED OCR TEST 2026", fill="black")
    return image


def test_ocr_image_returns_text():
    pytest.importorskip("rapidocr_onnxruntime")
    text = _ocr_image(_image())
    assert "MEDSPACED" in text.upper()


def test_scanned_pdf_uses_ocr(tmp_path: Path):
    pytest.importorskip("rapidocr_onnxruntime")
    import fitz

    image_path = tmp_path / "scan.png"
    _image().save(image_path)
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_image(fitz.Rect(40, 40, 572, 240), filename=str(image_path))
    pdf_path = tmp_path / "scan.pdf"
    document.save(pdf_path)
    document.close()

    sections = extract_sections(pdf_path, "scan.pdf")
    assert sections
    assert "MEDSPACED" in sections[0].text.upper()


def test_ocr_image_reports_missing_engines(monkeypatch):
    from app.services import extraction

    def broken(image):
        raise RuntimeError("motor yok")

    monkeypatch.setattr(extraction, "_rapidocr_text", broken)
    monkeypatch.setattr(extraction, "_pytesseract_text", broken)
    with pytest.raises(ExtractionError, match="OCR başarısız"):
        _ocr_image(_image())
