"""Persistent per-page OCR checkpoints for safe resumption of huge documents.

The checkpoint holds the full text of every page, so it lives in the per-user
app-data folder (owner-only access) instead of next to the output, where it
could end up in a synced or shared folder. Unfinished checkpoints expire after
``CHECKPOINT_MAX_AGE_DAYS``.
"""

import hashlib
import json
import os
import shutil
import time
from pathlib import Path

from hollyocr.utils.paths import get_app_data_dir

CHECKPOINT_MAX_AGE_DAYS = 30
# Versions up to 5.0.1 kept checkpoints in "<output>/.hollyocr_checkpoints".
LEGACY_DIRNAME = ".hollyocr_checkpoints"


def checkpoints_root():
    """Folder that holds every unfinished conversion's checkpoint."""
    return get_app_data_dir() / "checkpoints"


def _make_private_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        os.chmod(path, 0o700)


def purge_stale_checkpoints(root=None, max_age_days=CHECKPOINT_MAX_AGE_DAYS, now=None):
    """Delete checkpoints untouched for more than ``max_age_days``. Returns how many."""
    root = Path(root) if root else checkpoints_root()
    if not root.is_dir():
        return 0
    limit = (now if now is not None else time.time()) - max_age_days * 86400
    removed = 0
    for child in root.iterdir():
        try:
            if child.is_dir() and child.stat().st_mtime < limit:
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed


class ProcessingCheckpoint:
    def __init__(self, file_path, out_base, settings, root=None):
        file_path = Path(file_path)
        stat = file_path.stat()
        identity = hashlib.sha256(str(file_path.resolve()).encode("utf-8")).hexdigest()[:20]
        base = Path(root) if root else checkpoints_root()
        purge_stale_checkpoints(base)
        self.root = base / identity
        self.fingerprint = {
            "path": str(file_path.resolve()),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "settings": settings,
            "version": 4,
        }
        self.manifest = self.root / "manifest.json"
        self._remove_legacy(Path(out_base) / LEGACY_DIRNAME / identity)
        _make_private_dir(base)
        self._prepare()

    @staticmethod
    def _remove_legacy(legacy):
        """Old versions left the text next to the output; remove it for this file."""
        if legacy.is_dir():
            shutil.rmtree(legacy, ignore_errors=True)
            try:
                legacy.parent.rmdir()
            except OSError:
                pass

    def _prepare(self):
        valid = False
        try:
            valid = json.loads(self.manifest.read_text(encoding="utf-8")) == self.fingerprint
        except Exception:
            valid = False
        if self.root.exists() and not valid:
            shutil.rmtree(self.root, ignore_errors=True)
        _make_private_dir(self.root)
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
