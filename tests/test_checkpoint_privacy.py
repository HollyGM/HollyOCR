"""O progresso salvo (texto integral das páginas) fica fora da pasta de saída, só para o usuário, e expira."""

import os
import stat
import tempfile
import time
import unittest
from pathlib import Path

from hollyocr.core import checkpoint


class CheckpointPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hollyocr_ckpt_")
        self.base = Path(self.tmp.name)
        self.pdf = self.base / "autos.pdf"
        self.pdf.write_bytes(b"%PDF-1.7\n%%EOF\n")
        self.out = self.base / "Dropbox" / "saida"
        self.out.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_checkpoint_lives_outside_the_output_folder(self):
        ckpt = checkpoint.ProcessingCheckpoint(self.pdf, self.out, {"dpi": 300})
        ckpt.save(0, "Texto sigiloso da página 1", {"source": "ocr"})
        self.assertTrue(ckpt.root.is_relative_to(checkpoint.checkpoints_root()))
        self.assertEqual(list(self.out.rglob("*")), [])
        self.assertEqual(ckpt.load(0)[0], "Texto sigiloso da página 1")

    @unittest.skipIf(os.name == "nt", "permissões POSIX")
    def test_checkpoint_folders_are_owner_only(self):
        ckpt = checkpoint.ProcessingCheckpoint(self.pdf, self.out, {"dpi": 300})
        for folder in (checkpoint.checkpoints_root(), ckpt.root):
            self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700, folder)

    def test_legacy_checkpoint_next_to_output_is_removed(self):
        probe = checkpoint.ProcessingCheckpoint(self.pdf, self.out, {"dpi": 300})
        legacy = self.out / checkpoint.LEGACY_DIRNAME / probe.root.name
        legacy.mkdir(parents=True)
        (legacy / "page_000001.txt").write_text("texto antigo", encoding="utf-8")
        checkpoint.ProcessingCheckpoint(self.pdf, self.out, {"dpi": 300})
        self.assertFalse((self.out / checkpoint.LEGACY_DIRNAME).exists())

    def test_stale_checkpoints_expire(self):
        root = checkpoint.checkpoints_root()
        old, recent = root / "antigo", root / "recente"
        for folder in (old, recent):
            folder.mkdir(parents=True)
            (folder / "page_000001.txt").write_text("x", encoding="utf-8")
        long_ago = time.time() - (checkpoint.CHECKPOINT_MAX_AGE_DAYS + 1) * 86400
        os.utime(old, (long_ago, long_ago))
        self.assertEqual(checkpoint.purge_stale_checkpoints(), 1)
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())

    def test_cleanup_removes_only_this_files_checkpoint(self):
        ckpt = checkpoint.ProcessingCheckpoint(self.pdf, self.out, {"dpi": 300})
        other = checkpoint.checkpoints_root() / "outro-documento"
        other.mkdir()
        ckpt.cleanup()
        self.assertFalse(ckpt.root.exists())
        self.assertTrue(other.exists())


if __name__ == "__main__":
    unittest.main()
