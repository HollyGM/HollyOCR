"""Automatic processing profiles for small, large, and very large PDFs."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessingProfile:
    name: str
    page_count: int
    render_batch_size: int
    page_spill_threshold: int
    char_spill_threshold: int
    ocr_dpi: int


def choose_processing_profile(page_count, requested_dpi=300):
    """Bound memory/disk pressure without lowering OCR quality below 300 DPI."""
    page_count = max(0, int(page_count or 0))
    dpi = max(300, min(450, int(requested_dpi or 300)))
    if page_count <= 250:
        return ProcessingProfile("pequeno", page_count, 50, 250, 2_000_000, dpi)
    if page_count <= 2_000:
        return ProcessingProfile("grande", page_count, 32, 120, 1_000_000, dpi)
    if page_count <= 5_000:
        return ProcessingProfile("muito-grande", page_count, 24, 80, 750_000, dpi)
    return ProcessingProfile("gigante", page_count, 16, 50, 500_000, dpi)
