"""Persistent per-page OCR checkpoints for safe resumption of huge documents."""

import hashlib
import json
import os
import shutil
from pathlib import Path

from hollyocr.utils.paths import ensure_dir


class ProcessingCheckpoint:
    def __init__(self, file_path, out_base, settings):
        file_path = Path(file_path)
        stat = file_path.stat()
        identity = hashlib.sha256(str(file_path.resolve()).encode("utf-8")).hexdigest()[:20]
        self.root = Path(out_base) / ".hollyocr_checkpoints" / identity
        self.fingerprint = {
            "path": str(file_path.resolve()),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "settings": settings,
            "version": 3,
        }
        self.manifest = self.root / "manifest.json"
        self._prepare()

    def _prepare(self):
        valid = False
        try:
            valid = json.loads(self.manifest.read_text(encoding="utf-8")) == self.fingerprint
        except Exception:
            valid = False
        if self.root.exists() and not valid:
            shutil.rmtree(self.root, ignore_errors=True)
        ensure_dir(self.root)
        if not valid:
            self._write_atomic(self.manifest, json.dumps(self.fingerprint, ensure_ascii=False, sort_keys=True))

    def _page_path(self, page_index, suffix):
        return self.root / f"page_{page_index + 1:06d}.{suffix}"

    @staticmethod
    def _write_atomic(path, content):
        temp = path.parent / f".{path.name}.{os.getpid()}.tmp"
        with open(temp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temp, path)

    def load(self, page_index):
        text_path = self._page_path(page_index, "txt")
        detail_path = self._page_path(page_index, "json")
        try:
            return text_path.read_text(encoding="utf-8"), json.loads(detail_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save(self, page_index, text, detail):
        self._write_atomic(self._page_path(page_index, "txt"), text or "")
        self._write_atomic(
            self._page_path(page_index, "json"),
            json.dumps(detail or {}, ensure_ascii=False, sort_keys=True),
        )

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)
        try:
            self.root.parent.rmdir()
        except OSError:
            pass
