"""Validate the selected OCR backend rather than unrelated available engines."""

from unittest import mock

from hollyocr.core import ocr, vision_ocr


def test_explicit_tesseract_checks_languages_even_when_vision_is_available():
    with mock.patch.object(vision_ocr, "is_vision_ocr_available", return_value=True), \
         mock.patch.object(ocr, "get_tesseract_languages", return_value={"eng"}):
        issues = ocr.check_ocr_environment("poppler", "tesseract", "por", backend="tesseract")
    assert "Idioma 'por' não está instalado no Tesseract." in issues


def test_combined_tesseract_languages_accepts_installed_components():
    with mock.patch.object(ocr, "get_tesseract_languages", return_value={"por", "eng"}):
        issues = ocr.check_ocr_environment("poppler", "tesseract", "por+eng", backend="tesseract")
    assert issues == []


def test_combined_tesseract_languages_reports_only_missing_components():
    with mock.patch.object(ocr, "get_tesseract_languages", return_value={"por"}):
        issues = ocr.check_ocr_environment("poppler", "tesseract", "por+eng", backend="tesseract")
    assert issues == ["Idioma 'eng' não está instalado no Tesseract."]


def test_auto_vision_does_not_require_tesseract_language_data():
    with mock.patch.object(vision_ocr, "is_vision_ocr_available", return_value=True), \
         mock.patch.object(ocr, "get_tesseract_languages") as languages:
        issues = ocr.check_ocr_environment("poppler", None, "por", backend="auto")
    assert issues == []
    languages.assert_not_called()
