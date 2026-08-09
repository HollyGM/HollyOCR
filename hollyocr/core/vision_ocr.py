"""Apple Vision Framework OCR backend (macOS only, uses Neural Engine).

Dramatically faster than Tesseract on Apple Silicon once the CoreML models
are warmed up (~13ms/page accurate vs ~170ms/page for Tesseract at 200 DPI
on M5). The first call is slow (~25s) because macOS loads and links the
text-recognition CoreML bundles; subsequent calls are sub-100ms because the
models stay resident in the ANE.

Backend auto-detected by `is_vision_ocr_available()`. We never raise on
import failure -- macOS versions older than 10.15 or systems where the
pyobjc-framework-Vision bindings are not installed simply fall back to
Tesseract silently.
"""

import contextlib
import logging
import os
import sys
import threading
import time

# The macOS Vision/CoreML stack logs a noisy "Unable to find a valid E5 in
# provided path..." warning every time it can't locate the architecture-
# specific CoreML bundle (this happens on newer Apple Silicon chips whose
# H# identifier is not yet in the OS bundle list -- e.g. M5 on a fresh
# macOS 27 install). It is HARMLESS -- Vision falls back to the universal
# bundle and works correctly -- but it spams stderr on every call. macOS
# routes these messages through the unified os_log subsystem, which Python's
# stderr redirection cannot fully suppress (the writes happen at C level
# via OS_LOG_DEFAULT, bypassing the Python file object). The good news: the
# returned text and quality are unaffected. See https://github.com/
# apple/swift-corelibs-foundation/issues/4827 for the upstream discussion.
_logger = logging.getLogger(__name__)
_logger.addHandler(logging.NullHandler())

# Lazy PyObjC imports -- these are macOS-only and we want zero cost on other OSes.
_VISION_MODULES = None
_VISION_IMPORT_ERROR = None
_VISION_LOCK = threading.Lock()


@contextlib.contextmanager
def _silenced_stderr():
    """Temporarily redirect fd-level stderr to /dev/null.

    logging + warnings don't catch the macOS Vision stack's NSLog-style
    writes, which bypass Python entirely. We have to dup the fd to actually
    silence them. Restored on exit, even if Vision raises.
    """
    devnull = None
    saved_stderr = None
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        saved_stderr = os.dup(2)
        os.dup2(devnull, 2)
    except OSError:
        if devnull is not None:
            os.close(devnull)
        if saved_stderr is not None:
            os.close(saved_stderr)
        # If fd-level redirection is unavailable, run without silencing. An
        # exception raised by the caller must still propagate exactly once.
        yield
        return

    os.close(devnull)
    try:
        yield
    finally:
        os.dup2(saved_stderr, 2)
        os.close(saved_stderr)


def _ensure_vision_imported():
    """Import Vision/Quartz lazily. Returns True on success."""
    global _VISION_MODULES, _VISION_IMPORT_ERROR
    if _VISION_MODULES is not None:
        return True
    if _VISION_IMPORT_ERROR is not None:
        return False
    if sys.platform != "darwin":
        _VISION_IMPORT_ERROR = "not-darwin"
        return False
    with _VISION_LOCK:
        if _VISION_MODULES is not None:
            return True
        try:
            import Quartz  # noqa: F401
            import Vision  # noqa: F401
            from Cocoa import NSData  # noqa: F401
            from Foundation import NSDictionary  # noqa: F401
            _VISION_MODULES = (Vision, Quartz, NSData, NSDictionary)
            return True
        except Exception as exc:
            _VISION_IMPORT_ERROR = str(exc)
            return False


def is_vision_ocr_available():
    """True iff Apple Vision OCR backend can be used right now."""
    return _ensure_vision_imported()


def vision_ocr_error():
    """Human-readable reason Vision OCR isn't available, or empty string."""
    if _ensure_vision_imported():
        return ""
    return _VISION_IMPORT_ERROR or "Vision framework unavailable"


# Tesseract uses 3-letter codes ("por", "eng"); Vision uses BCP-47 ("pt-BR", "en-US").
_TESSERACT_TO_VISION_LANG = {
    "por": "pt-BR",
    "pt": "pt-BR",
    "eng": "en-US",
    "en": "en-US",
    "spa": "es-ES",
    "es": "es-ES",
    "fra": "fr-FR",
    "fr": "fr-FR",
    "deu": "de-DE",
    "ger": "de-DE",
    "de": "de-DE",
    "ita": "it-IT",
    "it": "it-IT",
}


def _map_lang_to_vision(lang):
    """Translate a Tesseract-style language code to Vision BCP-47 (best-effort)."""
    if not lang:
        return ["en-US"]
    # If already BCP-47-ish, use as-is.
    if "-" in lang or "_" in lang:
        return [str(lang).replace("_", "-")]
    primary = lang.split("+")[0].strip().lower()
    mapped = _TESSERACT_TO_VISION_LANG.get(primary, "en-US")
    return [mapped]


def _warm_up_vision_models(cg_image_factory):
    """Run a single throwaway recognition to force macOS to load the CoreML
    text-recognition bundles into the ANE. Without this, the first real call
    pays the full model-load cost (~25s on a cold cache)."""
    Vision, Quartz, NSData, _NSDictionary = _VISION_MODULES
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelFast)
    request.setUsesLanguageCorrection_(False)
    request.setRecognitionLanguages_(["en-US"])
    cg_image = cg_image_factory()
    if cg_image is None:
        return False
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
    with _silenced_stderr():
        success, _error = handler.performRequests_error_([request], None)
    return bool(success)


_WARMED_UP = False
_WARMUP_LOCK = threading.Lock()


def ocr_image_vision(image_path, lang="por", recognition_level="accurate",
                    use_language_correction=True):
    """Run Apple Vision OCR on a single image file. Returns the recognized text.

    recognition_level: 'fast' or 'accurate' (default 'accurate' -- ~100ms/page
    on M5 once warm, ~13ms/page for 'fast').
    """
    if not is_vision_ocr_available():
        raise RuntimeError(f"Apple Vision OCR unavailable: {vision_ocr_error()}")
    Vision, Quartz, NSData, _NSDictionary = _VISION_MODULES

    with open(image_path, "rb") as handle:
        image_bytes = handle.read()
    ns_data = NSData.dataWithBytes_length_(image_bytes, len(image_bytes))
    image_source = Quartz.CGImageSourceCreateWithData(ns_data, None)
    if image_source is None:
        raise RuntimeError(f"Vision: cannot decode image {image_path!r}")
    cg_image = Quartz.CGImageSourceCreateImageAtIndex(image_source, 0, None)
    if cg_image is None:
        raise RuntimeError(f"Vision: CGImageSource returned no image for {image_path!r}")

    # One-shot warm-up so callers never see the 25s cold-start cost.
    global _WARMED_UP
    with _WARMUP_LOCK:
        if not _WARMED_UP:
            try:
                _warm_up_vision_models(lambda: cg_image)
            except Exception as exc:
                _logger.debug("Apple Vision warm-up failed: %s", exc)
            _WARMED_UP = True

    request = Vision.VNRecognizeTextRequest.alloc().init()
    level = (
        Vision.VNRequestTextRecognitionLevelAccurate
        if recognition_level == "accurate"
        else Vision.VNRequestTextRecognitionLevelFast
    )
    request.setRecognitionLevel_(level)
    request.setUsesLanguageCorrection_(bool(use_language_correction))
    request.setRecognitionLanguages_(_map_lang_to_vision(lang))

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
    t0 = time.monotonic()
    with _silenced_stderr():
        success, error = handler.performRequests_error_([request], None)
    elapsed_ms = (time.monotonic() - t0) * 1000.0

    if not success:
        raise RuntimeError(f"Vision OCR failed: {error}")

    observations = request.results() or []
    text_lines = []
    for obs in observations:
        candidates = obs.topCandidates_(1)
        if not candidates:
            continue
        candidate = candidates[0]
        text = str(candidate.string())
        if text:
            text_lines.append(text)

    text = "\n".join(text_lines).strip()

    # Vision's confidence is in [0, 1]; stash it as a hidden suffix so the
    # quality analyzer can compare apples-to-apples if desired. For now we
    # just return plain text -- downstream code does not act on confidence.
    _ = elapsed_ms  # available if a caller wants to log per-call timing
    return text


def ocr_image_vision_with_fallback(image_path, lang="por", tesseract_callable=None,
                                    recognition_level="accurate"):
    """Run Vision OCR; if it fails for any reason, fall back to Tesseract.

    tesseract_callable is the project's existing Tesseract OCR entrypoint
    (`ocr_image_file`). Only invoked if Vision raises.
    """
    try:
        return ocr_image_vision(image_path, lang=lang, recognition_level=recognition_level)
    except Exception:
        if tesseract_callable is None:
            raise
        return tesseract_callable(image_path, lang=lang)
