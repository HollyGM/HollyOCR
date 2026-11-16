"""Programas auxiliares não vêm da pasta atual; a pasta de saída não é relida como entrada."""

import os
import tempfile
import unittest
from pathlib import Path

from hollyocr.core import extraction
from hollyocr.utils import paths


class RuntimeRootsTests(unittest.TestCase):
    def test_current_folder_is_not_searched_for_helper_programs(self):
        with tempfile.TemporaryDirectory(prefix="hollyocr_cwd_") as folder:
            planted = Path(folder) / "bin"
            planted.mkdir()
            (planted / "pdftoppm").write_text("#!/bin/sh\necho plantado\n")
            previous = os.getcwd()
            os.chdir(folder)
            try:
                roots = paths.get_runtime_roots()
                poppler, _tesseract = paths.get_dependencies_paths()
            finally:
                os.chdir(previous)
        resolved = Path(folder).resolve()
        self.assertNotIn(resolved, roots)
        self.assertNotEqual(Path(poppler).resolve() if poppler else None, (resolved / "bin"))


class OutputFolderDiscoveryTests(unittest.TestCase):
    def test_output_folder_inside_input_is_skipped(self):
        with tempfile.TemporaryDirectory(prefix="hollyocr_scan_") as folder:
            base = Path(folder)
            (base / "peticao.pdf").write_bytes(b"%PDF-1.7\n%%EOF\n")
            out = base / "convertidos"
            out.mkdir()
            (out / "peticao.md").write_text("# conversao anterior\n", encoding="utf-8")
            found = [p.name for p in extraction.find_files(str(base), exclude_dir=out)]
            everything = [p.name for p in extraction.find_files(str(base))]
        self.assertEqual(found, ["peticao.pdf"])
        self.assertIn("peticao.md", everything)


if __name__ == "__main__":
    unittest.main()
