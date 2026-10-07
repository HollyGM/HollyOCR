"""A successful conversion must account for every PDF page and OCR request."""

import tempfile
import unittest
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest import mock

import pymupdf

from hollyocr.core import extraction, pipeline


class PipelineIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hollyocr_integrity_")
        self.base = Path(self.tmp.name)
        self.pdf = self.base / "documento.pdf"
        self.out = self.base / "output"
        self.out.mkdir()
        with pymupdf.open() as document:
            for number in (1, 2):
                page = document.new_page()
                page.insert_text((72, 96), f"Documento original completo da pagina {number}.")
            document.save(self.pdf)

    def tearDown(self):
        self.tmp.cleanup()

    def convert(self, **kwargs):
        options = {"output_format": "md", "workers": 1, "ocr_backend": "vision"}
        options.update(kwargs)
        return pipeline.process_file(self.pdf, self.out, self.base, **options)

    def assert_no_output(self):
        self.assertEqual(list(self.out.glob("*.md")), [])

    def test_missing_native_page_is_a_failure(self):
        with mock.patch.object(pipeline, "extract_text_pages", return_value=iter(["Somente primeira pagina"])):
            meta, _ = self.convert(use_ocr=False)
        self.assertEqual(meta["status"], "failed")
        self.assertIn("1 página(s)", meta["error"])
        self.assertIn("2 página(s)", meta["error"])
        self.assert_no_output()

    def test_extractor_failure_after_yield_does_not_restart_page_numbering(self):
        def broken_chunks():
            yield {"text": "Primeira pagina"}
            raise RuntimeError("Falha na segunda pagina")

        layout = SimpleNamespace(to_markdown=mock.Mock(return_value=broken_chunks()))
        with mock.patch.object(extraction, "pymupdf4llm", layout):
            meta, _ = self.convert(use_ocr=False)
        self.assertEqual(meta["status"], "failed")
        self.assertIn("Extração incompleta", meta["error"])
        self.assert_no_output()

    def test_damaged_native_layer_without_ocr_is_not_complete(self):
        def damaged_pages(*_args, **kwargs):
            kwargs["diagnostic_callback"](0, "Camada nativa incompleta: falha no formulário")
            yield "Rodapé técnico, sem o conteúdo principal."
            yield "Segunda página completa."

        with mock.patch.object(pipeline, "extract_text_pages", side_effect=damaged_pages):
            meta, _ = self.convert(use_ocr=False)
        self.assertEqual(meta["status"], "failed")
        self.assertIn("Ative OCR", meta["error"])
        self.assertIn("Camada nativa incompleta", meta["warnings"][0])
        self.assert_no_output()

    def test_render_failure_preserves_checkpoint_and_can_resume(self):
        with mock.patch.object(pipeline, "convert_from_path", side_effect=RuntimeError("Poppler falhou")):
            meta, _ = self.convert(force_ocr=True)
        self.assertEqual(meta["status"], "failed")
        self.assertIn("OCR incompleto", meta["error"])
        self.assertIn("Poppler falhou", meta["warnings"][0])
        self.assertTrue(list(self.out.rglob("manifest.json")))
        self.assert_no_output()

        with mock.patch.object(pipeline, "convert_from_path", return_value=["one.jpg", "two.jpg"]), \
             mock.patch.object(pipeline, "ocr_image_file", side_effect=["Texto OCR primeira", "Texto OCR segunda"]):
            resumed, _ = self.convert(force_ocr=True)
        self.assertEqual(resumed["status"], "ok")
        self.assertEqual(resumed["pages"], 2)
        self.assertFalse((self.out / ".hollyocr_checkpoints").exists())

    def test_short_render_does_not_assign_images_to_unverified_pages(self):
        with mock.patch.object(pipeline, "convert_from_path", return_value=["unknown-page.jpg"]), \
             mock.patch.object(pipeline, "ocr_image_file") as ocr:
            meta, _ = self.convert(force_ocr=True)
        self.assertEqual(meta["status"], "failed")
        self.assertIn("Renderização incompleta", meta["warnings"][0])
        ocr.assert_not_called()
        self.assert_no_output()

    def test_page_ocr_failure_resumes_only_missing_page(self):
        with mock.patch.object(pipeline, "convert_from_path", return_value=["one.jpg", "two.jpg"]), \
             mock.patch.object(pipeline, "ocr_image_file", side_effect=[RuntimeError("OCR falhou"), "Texto segunda"]):
            meta, _ = self.convert(force_ocr=True)
        self.assertEqual(meta["status"], "failed")
        self.assertTrue(list(self.out.rglob("page_000002.txt")))
        self.assertEqual(list(self.out.rglob("page_000001.txt")), [])
        self.assert_no_output()

        with mock.patch.object(pipeline, "convert_from_path", return_value=["one.jpg"]) as render, \
             mock.patch.object(pipeline, "ocr_image_file", return_value="Texto primeira") as ocr:
            resumed, _ = self.convert(force_ocr=True)
        self.assertEqual(resumed["status"], "ok")
        self.assertEqual(render.call_args.kwargs["first_page"], 1)
        self.assertEqual(render.call_args.kwargs["last_page"], 1)
        self.assertEqual(ocr.call_count, 1)
        self.assertFalse((self.out / ".hollyocr_checkpoints").exists())

    def test_cancel_between_ocr_pages_preserves_completed_page(self):
        cancelled = Event()

        def first_ocr(*_args, **_kwargs):
            cancelled.set()
            return "Texto primeira"

        with mock.patch.object(pipeline, "convert_from_path", return_value=["one.jpg", "two.jpg"]), \
             mock.patch.object(pipeline, "ocr_image_file", side_effect=first_ocr) as ocr:
            meta, _ = self.convert(force_ocr=True, cancel_callback=cancelled.is_set)
        self.assertIsNone(meta)
        self.assertEqual(ocr.call_count, 1)
        self.assertTrue(list(self.out.rglob("page_000001.txt")))
        self.assert_no_output()

    def test_cancel_during_native_extraction_stops_without_output(self):
        cancelled = Event()

        def native_pages(*_args, **_kwargs):
            yield "Primeira pagina"
            cancelled.set()
            yield "Segunda pagina"

        with mock.patch.object(pipeline, "extract_text_pages", side_effect=native_pages):
            meta, _ = self.convert(use_ocr=False, cancel_callback=cancelled.is_set)
        self.assertIsNone(meta)
        self.assert_no_output()
