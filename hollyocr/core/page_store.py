"""In-memory/disk-spilling storage for per-page extracted text."""

import shutil
import tempfile
from pathlib import Path

PAGE_STORE_SPILL_PAGES = 250
PAGE_STORE_SPILL_CHARS = 2_000_000


class PageTextStore:
    """Keep page text in memory for small documents and spill to disk for large ones."""

    def __init__(self, page_spill_threshold=PAGE_STORE_SPILL_PAGES, char_spill_threshold=PAGE_STORE_SPILL_CHARS):
        self.page_spill_threshold = max(1, int(page_spill_threshold or PAGE_STORE_SPILL_PAGES))
        self.char_spill_threshold = max(1000, int(char_spill_threshold or PAGE_STORE_SPILL_CHARS))
        self._texts = []
        self.details = []
        self._total_chars = 0
        self._spill_dir = None

    @property
    def page_count(self):
        return len(self._texts)

    def _make_page_filename(self, index):
        return f"page_{index + 1:06d}.txt"

    def _ensure_spill_dir(self):
        if self._spill_dir is None:
            self._spill_dir = Path(tempfile.mkdtemp(prefix="hollyocr_pages_"))

    def _should_spill(self):
        return self.page_count >= self.page_spill_threshold or self._total_chars >= self.char_spill_threshold

    def _ensure_disk_backing(self):
        if self._spill_dir is not None:
            return
        self._ensure_spill_dir()
        for idx, text in enumerate(self._texts):
            page_path = self._spill_dir / self._make_page_filename(idx)
            with open(page_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text or "")
            self._texts[idx] = page_path

    def append(self, text, detail):
        text = text or ""
        self._texts.append(text)
        self.details.append(detail or {})
        self._total_chars += len(text)
        if self._spill_dir is not None:
            self._write_page_file(self.page_count - 1, text)
        elif self._should_spill():
            self._ensure_disk_backing()

    def _write_page_file(self, index, text):
        self._ensure_spill_dir()
        page_path = self._spill_dir / self._make_page_filename(index)
        with open(page_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text or "")
        self._texts[index] = page_path

    def set(self, index, text, detail=None):
        old_text = self.get_text(index)
        new_text = text or ""
        self._total_chars += len(new_text) - len(old_text)
        if self._spill_dir is not None:
            self._write_page_file(index, new_text)
        else:
            self._texts[index] = new_text
            if self._should_spill():
                self._ensure_disk_backing()
        if detail is not None:
            self.details[index] = detail

    def get_text(self, index):
        ref = self._texts[index]
        if isinstance(ref, Path):
            with open(ref, "r", encoding="utf-8") as handle:
                return handle.read()
        return ref

    def get_detail(self, index):
        return self.details[index]

    def iter_pages(self):
        for idx in range(self.page_count):
            yield idx + 1, self.get_text(idx), self.get_detail(idx)

    def has_any_text(self):
        return any(bool((detail or {}).get("char_count", 0)) for detail in self.details)

    def cleanup(self):
        if self._spill_dir is not None:
            shutil.rmtree(self._spill_dir, ignore_errors=True)
            self._spill_dir = None
