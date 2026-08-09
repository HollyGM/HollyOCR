"""OCR rendering and text reconstruction (Tesseract via pytesseract/pdf2image)."""

import os
import shutil
import subprocess  # nosec B404
import tempfile
from pathlib import Path

try:
    from pdf2image import convert_from_path
except Exception:
    convert_from_path = None

try:
    import pytesseract
except Exception:
    pytesseract = None

try:
    from PIL import Image, ImageOps
except Exception:
    Image = None
    ImageOps = None

from hollyocr.utils.logging_setup import LOGGER

from .quality import analyze_page_text_quality, choose_best_page_text


def _delete_temporary_image(image_path):
    """Remove only an image stored below the operating system temp folder."""
    candidate = Path(image_path).resolve(strict=False)
    temporary_root = Path(tempfile.gettempdir()).resolve(strict=False)
    if not candidate.is_relative_to(temporary_root):
        raise ValueError(f"Recusa de exclusão fora da área temporária: {candidate}")
    try:
        candidate.unlink(missing_ok=True)
    except OSError as exc:
        LOGGER.warning("Não foi possível remover imagem temporária %s: %s", candidate, exc)


def preprocess_image_for_ocr(image):
    """Apply conservative preprocessing that helps OCR without destroying layout."""
    if Image is None or ImageOps is None:
        raise RuntimeError('Pillow required for OCR preprocessing')
    img = image.convert("L")
    img = ImageOps.autocontrast(img)
    width, height = img.size
    longest_side = max(width, height)
    if longest_side and longest_side < 1400:
        scale = min(2.0, 1400 / longest_side)
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
    return img


def extract_structured_ocr_text(image, lang='por'):
    """Rebuild OCR text using line geometry to preserve tables and chat-like layouts better."""
    if pytesseract is None:
        raise RuntimeError('pytesseract required for OCR')
    output_helper = getattr(pytesseract, "Output", None)
    output_dict = getattr(output_helper, "DICT", "dict")
    data = pytesseract.image_to_data(image, lang=lang, output_type=output_dict)
    if not isinstance(data, dict):
        return ""

    lines = {}
    item_count = len(data.get("text", []))
    for idx in range(item_count):
        text = (data.get("text", [])[idx] or "").strip()
        if not text:
            continue
        try:
            conf = float(data.get("conf", [])[idx])
        except Exception:
            conf = -1.0
        if conf == 0:
            continue
        key = (
            int(data.get("block_num", [1])[idx] or 1),
            int(data.get("par_num", [1])[idx] or 1),
            int(data.get("line_num", [1])[idx] or 1),
        )
        lines.setdefault(key, []).append({
            "text": text,
            "left": int(data.get("left", [0])[idx] or 0),
            "top": int(data.get("top", [0])[idx] or 0),
            "width": int(data.get("width", [0])[idx] or 0),
        })

    ordered_lines = []
    for words in lines.values():
        words = sorted(words, key=lambda item: (item["left"], item["top"]))
        line_parts = []
        previous_right = None
        total_chars = max(1, sum(max(1, len(word["text"])) for word in words))
        avg_width = max(8.0, sum(word["width"] for word in words) / total_chars)
        for word in words:
            if previous_right is not None:
                gap = word["left"] - previous_right
                if gap >= max(24.0, avg_width * 7.0):
                    line_parts.append(" | ")
                elif gap >= max(10.0, avg_width * 3.0):
                    line_parts.append("  ")
                else:
                    line_parts.append(" ")
            line_parts.append(word["text"])
            previous_right = word["left"] + word["width"]
        line_text = "".join(line_parts).strip()
        if line_text:
            top = min(word["top"] for word in words)
            left = min(word["left"] for word in words)
            ordered_lines.append((top, left, line_text))

    ordered_lines.sort(key=lambda item: (item[0], item[1]))
    return "\n".join(line_text for _top, _left, line_text in ordered_lines).strip()


def extract_ocr_text(image, lang='por', tesseract_path=None):
    """Run OCR with both plain and structured reconstruction, keeping the most usable result."""
    if pytesseract is None:
        raise RuntimeError('pytesseract required for OCR')
    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = str(tesseract_path)

    prepared = preprocess_image_for_ocr(image)
    plain_text = pytesseract.image_to_string(prepared, lang=lang) if lang else pytesseract.image_to_string(prepared)
    structured_text = ""
    try:
        structured_text = extract_structured_ocr_text(prepared, lang=lang)
    except Exception:
        structured_text = ""

    plain_analysis = analyze_page_text_quality(plain_text)
    structured_analysis = analyze_page_text_quality(structured_text)
    best_text, _source, _analysis = choose_best_page_text(
        plain_text,
        plain_analysis,
        structured_text,
        structured_analysis,
        force_ocr=False,
    )
    return best_text or plain_text or structured_text


def get_contiguous_batches(pages_to_ocr, max_batch_size=50):
    """Group 0-based page indices into contiguous lists of at most max_batch_size."""
    if not pages_to_ocr:
        return []
    pages = sorted(pages_to_ocr)
    batches = []
    current_batch = [pages[0]]
    for p in pages[1:]:
        if p == current_batch[-1] + 1 and len(current_batch) < max_batch_size:
            current_batch.append(p)
        else:
            batches.append(current_batch)
            current_batch = [p]
    if current_batch:
        batches.append(current_batch)
    return batches


def ocr_image_file(image_path: str, lang='por', tesseract_path=None,
                   backend='auto', delete_after=False):
    """Run OCR on a single pre-rendered image file.

    backend: 'auto' (default; picks Vision on macOS when available, else Tesseract),
             'tesseract' (force the legacy pipeline), or
             'vision' (force Apple Vision; raises if unavailable).
    delete_after: remove the image after OCR. The safe default is ``False``;
        only internal PDF renders stored in a temp folder should enable it.
    """
    from . import vision_ocr

    use_vision = False
    if backend == 'vision':
        use_vision = True
    elif backend == 'auto':
        use_vision = vision_ocr.is_vision_ocr_available()

    if use_vision:
        try:
            text = vision_ocr.ocr_image_vision(image_path, lang=lang)
        except Exception:
            # Vision should always be available when is_vision_ocr_available said so,
            # but a single corrupt frame should not abort the whole batch -- fall back.
            if backend == 'vision':
                raise
            text = None
        if text is not None:
            if delete_after:
                _delete_temporary_image(image_path)
            return text

    if pytesseract is None:
        raise RuntimeError('pytesseract required for OCR')
    if Image is None:
        raise RuntimeError('Pillow required for OCR image handling')
    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = str(tesseract_path)

    try:
        with Image.open(image_path) as img:
            return extract_ocr_text(img, lang=lang, tesseract_path=tesseract_path)
    finally:
        if delete_after:
            _delete_temporary_image(image_path)


def tesseract_startupinfo():
    if os.name != 'nt':
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return startupinfo


def get_tesseract_languages(tesseract_path=None):
    """Return installed Tesseract language codes, or None if they cannot be read."""
    executable = str(Path(tesseract_path).resolve()) if tesseract_path else shutil.which("tesseract")
    if not executable:
        return None
    command = [executable, '--list-langs']
    try:
        proc = subprocess.run(  # nosec B603
            command,
            capture_output=True,
            text=True,
            shell=False,
            timeout=10,
            startupinfo=tesseract_startupinfo()
        )
    except (OSError, subprocess.SubprocessError):
        return None

    output = (proc.stdout or '') + '\n' + (proc.stderr or '')
    if proc.returncode != 0:
        return None

    languages = []
    for line in output.splitlines():
        value = line.strip()
        if not value or value.lower().startswith('list of available languages'):
            continue
        languages.append(value)
    return set(languages)


def check_ocr_environment(poppler_path=None, tesseract_path=None, lang='por'):
    """Collect OCR dependency issues that deserve a user-visible warning."""
    from .vision_ocr import is_vision_ocr_available

    issues = []
    vision_available = is_vision_ocr_available()
    if convert_from_path is None:
        issues.append("Biblioteca pdf2image não encontrada.")
    if not poppler_path:
        issues.append("Poppler não encontrado; OCR em PDFs escaneados pode falhar.")
    if not vision_available:
        if pytesseract is None:
            issues.append("Biblioteca pytesseract não encontrada.")
        if not tesseract_path:
            issues.append("Tesseract não encontrado; OCR em imagens e PDFs escaneados pode falhar.")
        elif lang:
            langs = get_tesseract_languages(tesseract_path)
            if langs is not None and lang not in langs:
                issues.append(f"Idioma '{lang}' não está instalado no Tesseract.")
    return issues
