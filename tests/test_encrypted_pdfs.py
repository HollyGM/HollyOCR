"""PDFs criptografados: proteção só de permissões converte; senha de abertura falha com aviso claro.

Reproduz o app empacotado para macOS, que desliga o PyMuPDF e depende só do pypdf
(que, por sua vez, precisa da biblioteca cryptography para decifrar AES).
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pymupdf
from pypdf import PdfWriter

from hollyocr.core import extraction, pipeline


def _encrypt(source: Path, target: Path, user_password: str):
    writer = PdfWriter()
    writer.append(str(source))
    writer.encrypt(user_password=user_password, owner_password="senha-do-proprietario", algorithm="AES-256")
    with target.open("wb") as handle:
        writer.write(handle)


class EncryptedPdfTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hollyocr_encrypted_")
        self.base = Path(self.tmp.name)
        self.out = self.base / "saida"
        self.out.mkdir()
        plain = self.base / "aberto.pdf"
        with pymupdf.open() as document:
            for number in (1, 2):
                page = document.new_page()
                page.insert_text((72, 96), f"Decisao judicial pagina {number} com texto nativo suficiente.")
            document.save(plain)
        self.permissions_only = self.base / "protegido_permissoes.pdf"
        self.with_password = self.base / "com_senha.pdf"
        _encrypt(plain, self.permissions_only, user_password="")
        _encrypt(plain, self.with_password, user_password="senha-de-abertura")

    def tearDown(self):
        self.tmp.cleanup()

    def convert(self, pdf):
        return pipeline.process_file(
            pdf, self.out, self.base, output_format="md", use_ocr=False, workers=1, ocr_backend="vision"
        )

    def test_inspection_reads_permission_protected_pdf(self):
        inspection = extraction.inspect_pdf(self.permissions_only)
        self.assertTrue(inspection.reliable, inspection.warning)
        self.assertEqual(inspection.page_count, 2)
        self.assertFalse(inspection.password_required)

    def test_permission_protected_pdf_converts_like_packaged_app(self):
        # App empacotado: PyMuPDF desligado, só o pypdf extrai o texto.
        with mock.patch.object(extraction, "fitz", None), mock.patch.object(extraction, "pymupdf4llm", None):
            meta, _ = self.convert(self.permissions_only)
        self.assertEqual(meta["status"], "ok", meta.get("error"))
        self.assertEqual(meta["pages"], 2)
        text = Path(meta["output_path"]).read_text(encoding="utf-8")
        self.assertIn("Decisao judicial pagina 1", text)
        self.assertIn("Decisao judicial pagina 2", text)

    def test_permission_protected_pdf_converts_with_pymupdf(self):
        meta, _ = self.convert(self.permissions_only)
        self.assertEqual(meta["status"], "ok", meta.get("error"))
        self.assertEqual(meta["pages"], 2)

    def test_password_protected_pdf_fails_with_clear_message(self):
        meta, _ = self.convert(self.with_password)
        self.assertEqual(meta["status"], "failed")
        self.assertIn("senha de abertura", meta["error"])
        self.assertEqual(list(self.out.glob("*.md")), [])


if __name__ == "__main__":
    unittest.main()
