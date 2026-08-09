"""Apple Vision OCR backend tests.

These run only on macOS (`is_vision_ocr_available()` returns True); on other
platforms they are skipped. The pure-Python helpers (lang mapping, backend
dispatch in ocr_image_file) are tested on every platform.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw, ImageFont

from hollyocr.core import ocr as core_ocr
from hollyocr.core import vision_ocr


def _make_test_image(path: Path, text: str) -> None:
    """Write a simple high-contrast text image we can OCR."""
    img = Image.new("RGB", (1200, 400), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial.ttf", 48
        )
    except Exception:
        font = ImageFont.load_default()
    draw.text((40, 160), text, fill="black", font=font)
    img.save(path)


class VisionOcrLangMapTests(unittest.TestCase):
    """Pure-Python mapping from Tesseract codes to Vision BCP-47 codes."""

    def test_tesseract_code_maps_to_bcp47(self):
        self.assertEqual(vision_ocr._map_lang_to_vision("por"), ["pt-BR"])
        self.assertEqual(vision_ocr._map_lang_to_vision("eng"), ["en-US"])
        self.assertEqual(vision_ocr._map_lang_to_vision("spa"), ["es-ES"])

    def test_empty_lang_falls_back_to_english(self):
        self.assertEqual(vision_ocr._map_lang_to_vision(""), ["en-US"])
        self.assertEqual(vision_ocr._map_lang_to_vision(None), ["en-US"])

    def test_already_bcp47_passes_through(self):
        self.assertEqual(vision_ocr._map_lang_to_vision("pt-BR"), ["pt-BR"])
        self.assertEqual(vision_ocr._map_lang_to_vision("en_US"), ["en-US"])

    def test_unknown_lang_falls_back_to_english(self):
        # Tesseract uses codes like "vie" or "chi_sim"; we don't have mappings
        # for those, so fall back gracefully.
        self.assertEqual(vision_ocr._map_lang_to_vision("vie"), ["en-US"])

    def test_composite_lang_uses_first(self):
        self.assertEqual(vision_ocr._map_lang_to_vision("por+eng"), ["pt-BR"])


class VisionOcrAvailabilityTests(unittest.TestCase):
    def test_availability_is_consistent(self):
        """Repeated calls return the same answer (no flaky cold-start cost)."""
        first = vision_ocr.is_vision_ocr_available()
        for _ in range(5):
            self.assertEqual(vision_ocr.is_vision_ocr_available(), first)

    def test_availability_on_current_platform(self):
        """On macOS with bindings installed, must be True; elsewhere False."""
        if sys.platform == "darwin":
            self.assertTrue(vision_ocr.is_vision_ocr_available(),
                            "Vision bindings should be installed on this macOS")
        else:
            self.assertFalse(vision_ocr.is_vision_ocr_available())

    def test_error_string_matches_availability(self):
        if vision_ocr.is_vision_ocr_available():
            self.assertEqual(vision_ocr.vision_ocr_error(), "")
        else:
            self.assertNotEqual(vision_ocr.vision_ocr_error(), "")


@unittest.skipUnless(
    sys.platform == "darwin" and vision_ocr.is_vision_ocr_available(),
    "Apple Vision only available on macOS with pyobjc-framework-Vision",
)
class VisionOcrLiveTests(unittest.TestCase):
    """Real Vision OCR on a generated test image."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="vision_ocr_tests_")
        cls.base = Path(cls.tmp.name)
        cls.image_path = cls.base / "hello.png"
        _make_test_image(cls.image_path, "Hello Vision")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_ocr_returns_nonempty_text(self):
        text = vision_ocr.ocr_image_vision(str(self.image_path), lang="eng")
        self.assertTrue(text, "Vision OCR returned empty text")
        # Either 'Hello' or 'Vision' should appear (case-insensitive).
        lowered = text.lower()
        self.assertTrue(
            "hello" in lowered or "vision" in lowered,
            f"Expected text to contain 'Hello' or 'Vision', got: {text!r}",
        )

    def test_ocr_fast_level_works(self):
        text = vision_ocr.ocr_image_vision(
            str(self.image_path), lang="eng", recognition_level="fast"
        )
        self.assertTrue(text)

    def test_ocr_invalid_path_raises(self):
        with self.assertRaises(Exception):
            vision_ocr.ocr_image_vision(
                str(self.base / "does_not_exist.png"), lang="eng"
            )


class OcrImageFileBackendDispatchTests(unittest.TestCase):
    """`ocr_image_file` honors the backend parameter on every platform."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ocr_backend_tests_")
        self.base = Path(self.tmp.name)
        self.image_path = self.base / "page.png"
        _make_test_image(self.image_path, "OCR backend dispatch")

    def tearDown(self):
        self.tmp.cleanup()

    def test_backend_tesseract_calls_tesseract_path(self):
        """backend='tesseract' must invoke the Tesseract pipeline, not Vision."""
        with mock.patch.object(core_ocr, "extract_ocr_text", return_value="TESS_OK") as mocked:
            result = core_ocr.ocr_image_file(
                str(self.image_path), lang="eng", backend="tesseract"
            )
        self.assertEqual(result, "TESS_OK")
        self.assertTrue(mocked.called)

    def test_backend_auto_falls_back_when_vision_unavailable(self):
        """If Vision says 'not available', backend='auto' must use Tesseract."""
        with mock.patch.object(vision_ocr, "is_vision_ocr_available", return_value=False), \
             mock.patch.object(core_ocr, "extract_ocr_text", return_value="AUTO_OK") as mocked:
            result = core_ocr.ocr_image_file(
                str(self.image_path), lang="eng", backend="auto"
            )
        self.assertEqual(result, "AUTO_OK")
        self.assertTrue(mocked.called)

    def test_backend_vision_unavailable_raises(self):
        """If user explicitly forces 'vision' but bindings missing, raise."""
        with mock.patch.object(vision_ocr, "is_vision_ocr_available", return_value=False):
            with self.assertRaises(Exception):
                core_ocr.ocr_image_file(
                    str(self.image_path), lang="eng", backend="vision"
                )

    def test_backend_vision_failure_falls_back_silently(self):
        """A single Vision failure (corrupt frame) must not abort the batch."""
        with mock.patch.object(vision_ocr, "is_vision_ocr_available", return_value=True), \
             mock.patch.object(vision_ocr, "ocr_image_vision",
                               side_effect=RuntimeError("bad frame")), \
             mock.patch.object(core_ocr, "extract_ocr_text", return_value="FALLBACK_OK") as mocked:
            result = core_ocr.ocr_image_file(
                str(self.image_path), lang="eng", backend="auto"
            )
        self.assertEqual(result, "FALLBACK_OK")
        self.assertTrue(mocked.called)

    def test_backend_vision_success_skips_tesseract(self):
        """If Vision returns text, Tesseract must NOT be called."""
        with mock.patch.object(vision_ocr, "is_vision_ocr_available", return_value=True), \
             mock.patch.object(vision_ocr, "ocr_image_vision", return_value="VISION_OK"), \
             mock.patch.object(core_ocr, "extract_ocr_text") as mocked_tesseract:
            result = core_ocr.ocr_image_file(
                str(self.image_path), lang="eng", backend="auto"
            )
        self.assertEqual(result, "VISION_OK")
        mocked_tesseract.assert_not_called()

    def test_original_image_is_preserved_by_default(self):
        original = self.image_path.read_bytes()
        with mock.patch.object(core_ocr, "extract_ocr_text", return_value="OK"):
            result = core_ocr.ocr_image_file(
                str(self.image_path), lang="eng", backend="tesseract"
            )
        self.assertEqual(result, "OK")
        self.assertEqual(self.image_path.read_bytes(), original)

    def test_delete_after_rejects_paths_outside_system_temp(self):
        outside_temp = Path.cwd() / ".hollyocr-safety-test.png"
        try:
            outside_temp.write_bytes(self.image_path.read_bytes())
            with mock.patch.object(core_ocr, "extract_ocr_text", return_value="OK"):
                with self.assertRaises(ValueError):
                    core_ocr.ocr_image_file(
                        str(outside_temp),
                        lang="eng",
                        backend="tesseract",
                        delete_after=True,
                    )
            self.assertTrue(outside_temp.exists())
        finally:
            outside_temp.unlink(missing_ok=True)


class VisionStderrContextTests(unittest.TestCase):
    def test_body_exception_propagates_once(self):
        with self.assertRaisesRegex(RuntimeError, "sentinela"):
            with vision_ocr._silenced_stderr():
                raise RuntimeError("sentinela")


if __name__ == "__main__":
    unittest.main()
