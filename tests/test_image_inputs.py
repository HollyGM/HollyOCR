"""Imagens de entrada: Pillow restrito a JPEG/PNG no OCR; TIFF multipágina e HEIC aceitos."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw, UnidentifiedImageError

from hollyocr.core import extraction, ocr, pipeline


def _page_with_text(text, mode="L"):
    image = Image.new(mode, (600, 200), 255 if mode in ("L", "1") else (255, 255, 255))
    ImageDraw.Draw(image).text((20, 80), text, fill=0 if mode in ("L", "1") else (0, 0, 0))
    return image


class ImageInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hollyocr_images_")
        self.base = Path(self.tmp.name)
        self.work = self.base / "trabalho"
        self.work.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_disguised_file_never_reaches_other_decoders(self):
        disguised = self.base / "foto.jpg"
        _page_with_text("BMP disfarcado").save(disguised, "BMP")
        with mock.patch.object(ocr.pytesseract, "image_to_string") as tesseract:
            with self.assertRaises(UnidentifiedImageError):
                ocr.ocr_image_file(str(disguised), backend="tesseract")
        tesseract.assert_not_called()

    def test_real_jpeg_and_png_still_open(self):
        for name, fmt in (("a.jpg", "JPEG"), ("b.png", "PNG")):
            path = self.base / name
            _page_with_text("ok").save(path, fmt)
            with mock.patch.object(ocr, "extract_ocr_text", return_value="texto") as extract:
                self.assertEqual(ocr.ocr_image_file(str(path), backend="tesseract"), "texto")
            extract.assert_called_once()

    def test_multipage_tiff_becomes_one_png_per_page(self):
        tiff = self.base / "digitalizacao.tif"
        pages = [_page_with_text(f"Pagina {n}") for n in (1, 2, 3)]
        pages[0].save(tiff, "TIFF", save_all=True, append_images=pages[1:])
        images = ocr.expand_image_input(tiff, self.work)
        self.assertEqual(len(images), 3)
        for image in images:
            with Image.open(image, formats=ocr.OCR_IMAGE_FORMATS) as opened:
                self.assertEqual(opened.format, "PNG")

    def test_16_bit_tiff_is_rescaled_not_whitened(self):
        tiff = self.base / "cinza16.tif"
        image = Image.new("I;16", (200, 100), 60000)
        ImageDraw.Draw(image).rectangle((50, 30, 150, 70), fill=2000)
        image.save(tiff, "TIFF")
        [png] = ocr.expand_image_input(tiff, self.work)
        with Image.open(png) as converted:
            darkest, lightest = converted.convert("L").getextrema()
        self.assertLess(darkest, 40)
        self.assertGreater(lightest, 200)

    @unittest.skipUnless(sys.platform == "darwin" and Path(ocr.SIPS_PATH).exists(), "HEIC só no macOS")
    def test_heic_is_converted_by_macos(self):
        png = self.base / "origem.png"
        _page_with_text("Foto do iPhone", mode="RGB").save(png, "PNG")
        heic = self.base / "foto.heic"
        result = subprocess.run([ocr.SIPS_PATH, "-s", "format", "heic", str(png), "--out", str(heic)],
                                capture_output=True, check=False)
        if result.returncode != 0 or not heic.exists():
            self.skipTest("este macOS não grava HEIC")
        [converted] = ocr.expand_image_input(heic, self.work)
        with Image.open(converted, formats=ocr.OCR_IMAGE_FORMATS) as opened:
            self.assertEqual(opened.format, "PNG")

    def test_find_files_accepts_tiff_and_heic(self):
        for name in ("a.tif", "b.tiff", "c.heic", "d.HEIF", "e.gif"):
            (self.base / name).write_bytes(b"x")
        found = {p.name for p in extraction.find_files(str(self.base))}
        self.assertTrue({"a.tif", "b.tiff", "c.heic", "d.HEIF"} <= found)
        self.assertNotIn("e.gif", found)

    def test_pipeline_converts_every_tiff_page_and_keeps_original(self):
        tiff = self.base / "autos.tiff"
        pages = [_page_with_text(f"Pagina {n}") for n in (1, 2)]
        pages[0].save(tiff, "TIFF", save_all=True, append_images=pages[1:])
        out = self.base / "saida"
        out.mkdir()
        texts = iter(["Texto reconhecido da primeira pagina do TIFF.", "Texto reconhecido da segunda pagina do TIFF."])
        with mock.patch.object(pipeline, "ocr_image_file", side_effect=lambda *a, **k: next(texts)):
            meta, _ = pipeline.process_file(tiff, out, self.base, output_format="md", workers=1, ocr_backend="vision")
        self.assertEqual(meta["status"], "ok", meta.get("error"))
        self.assertEqual(meta["pages"], 2)
        content = Path(meta["output_path"]).read_text(encoding="utf-8")
        self.assertIn("primeira pagina", content)
        self.assertIn("segunda pagina", content)
        self.assertTrue(tiff.exists())


if __name__ == "__main__":
    unittest.main()
