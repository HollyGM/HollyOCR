"""End-to-end extraction pipeline focused on maximum faithful PDF content."""

import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
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
    import docx
except Exception:
    docx = None

from hollyocr.utils.logging_setup import LOGGER

from .checkpoint import ProcessingCheckpoint
from .extraction import (
    extract_docx_text,
    extract_text_pages,
    inspect_pdf,
    normalize_output_format,
)
from .ocr import get_contiguous_batches, ocr_image_file
from .output_writer import (
    _write_output_stream,
    build_failure_meta,
    build_output_text,
    create_page_audit_output_path,
    should_cancel,
    unique_output_path,
    write_output_document_atomic,
    write_page_audit_atomic,
)
from .page_store import PageTextStore
from .quality import analyze_page_text_quality, build_page_detail, choose_best_page_text
from .strategy import choose_processing_profile
from .vision_ocr import is_vision_ocr_available

MIN_IMAGE_COVERAGE_FOR_OCR = 0.025
FULL_PAGE_IMAGE_COVERAGE = 0.65
COMPLETE_TEXT_LAYER_MIN_CHARS = 900
IMAGE_OCR_POLICY_VERSION = 3

# Fraction of a file's progress bar reserved for native extraction; the rest
# belongs to OCR, which dominates wall-clock time on scanned documents.
EXTRACTION_PROGRESS_WEIGHT = 0.35


def _report_progress(progress_callback, fraction):
    """Best-effort intra-file progress in [0, 1]; UI failures never abort the pipeline."""
    if progress_callback is None:
        return
    try:
        progress_callback(max(0.0, min(1.0, float(fraction))))
    except Exception:
        pass


def _image_page_requires_ocr(native_detail, coverages, has_image=True):
    """Decide whether an embedded image can contain text worth OCR.

    Tiny court-system logos and signature ornaments are ignored. A large scan
    with a healthy, substantial text layer is also not OCRed a second time.
    Missing placement data remains conservative and triggers OCR.
    """
    if not has_image:
        return False
    coverages = tuple(float(value or 0.0) for value in (coverages or ()))
    if not coverages:
        return True
    largest = max(coverages)
    if largest < MIN_IMAGE_COVERAGE_FOR_OCR:
        return False

    native_detail = native_detail or {}
    if largest >= FULL_PAGE_IMAGE_COVERAGE:
        native_chars = int(native_detail.get("char_count", 0) or 0)
        native_score = int(native_detail.get("quality_score", 0) or 0)
        if (
            native_chars >= COMPLETE_TEXT_LAYER_MIN_CHARS
            and native_score >= 70
            and not native_detail.get("needs_ocr")
        ):
            return False
    return True


def _relative_output_path(file_path, out_base, input_root, output_format):
    try:
        rel = file_path.relative_to(input_root)
        if str(rel) == ".":
            rel = file_path.name
    except Exception:
        rel = file_path.name
    return unique_output_path(out_base / Path(str(rel)).with_suffix(f".{output_format}"))


def _ocr_reason(detail, page_index, ocr_image_pages, force_ocr, image_coverages):
    reasons = []
    if force_ocr:
        reasons.append("OCR integral solicitado")
    if page_index in ocr_image_pages:
        coverage = max(image_coverages.get(page_index, ()) or (0.0,))
        if coverage:
            reasons.append(f"imagem relevante detectada ({coverage * 100:.1f}% da página)")
        else:
            reasons.append("imagem relevante detectada")
    if detail.get("extraction_issue"):
        reasons.append("camada nativa incompleta")
    if detail.get("needs_ocr") and not detail.get("extraction_issue"):
        reasons.append("texto nativo ausente ou de baixa qualidade")
    return "; ".join(reasons) or "verificação OCR"


def _apply_ocr_result(
    page_store,
    page_index,
    ocr_text,
    threshold,
    force_ocr,
    ocr_image_pages,
    image_counts,
    image_coverages,
):
    native_text = page_store.get_text(page_index)
    native_detail = page_store.get_detail(page_index)
    ocr_analysis = analyze_page_text_quality(ocr_text, min_chars=threshold)
    chosen_text, source, chosen_analysis = choose_best_page_text(
        native_text,
        native_detail,
        ocr_text,
        ocr_analysis,
        force_ocr=force_ocr,
        preserve_both=page_index in ocr_image_pages or bool(native_detail.get("extraction_issue")),
    )
    detail = build_page_detail(
        page_index + 1,
        chosen_text or "",
        source,
        analysis=chosen_analysis,
        image_count=image_counts.get(page_index, 0),
        image_coverage=max(image_coverages.get(page_index, ()) or (0.0,)),
        ocr_image_candidate=page_index in ocr_image_pages,
        extraction_issue=native_detail.get("extraction_issue"),
        ocr_reason=_ocr_reason(native_detail, page_index, ocr_image_pages, force_ocr, image_coverages),
    )
    page_store.set(page_index, chosen_text or "", detail)
    return detail


def process_file(
    file_path: Path,
    out_base: Path,
    input_root: Path,
    poppler_path=None,
    tesseract_path=None,
    ocr_threshold=30,
    lang="por",
    workers=1,
    executor=None,
    status_callback=None,
    write_output=True,
    output_format="md",
    use_ocr=True,
    force_ocr=False,
    cancel_callback=None,
    ocr_dpi=300,
    compiled_handle=None,
    page_audit_enabled=False,
    ocr_backend="auto",
    progress_callback=None,
):
    """Extract native text and OCR pages with meaningful raster content.

    This pipeline performs extraction and OCR only; it does not call models,
    external APIs, or content summarizers.

    ``executor``: when ``workers`` > 1, callers processing more than one file
    or more than one OCR batch should pass a shared ``ProcessPoolExecutor``
    here (see ``gui.shared.processing.run_conversion_loop`` and ``cli.main``).
    Without it, this function falls back to opening and closing its own pool
    for every render batch, which pays process-startup cost repeatedly instead
    of once -- costly on large documents, and especially so with the Apple
    Vision backend, whose CoreML models re-pay their warm-up cost per process.
    """
    file_path, out_base, input_root = Path(file_path), Path(out_base), Path(input_root)
    output_format = normalize_output_format(output_format)
    warnings = []
    inspection = None
    profile = choose_processing_profile(1, ocr_dpi)
    checkpoint = None
    page_store = None
    extraction_issues = {}

    try:
        if should_cancel(cancel_callback):
            return None, None
        ext = file_path.suffix.lower()

        if ext == ".pdf":
            inspection = inspect_pdf(file_path)
            profile = choose_processing_profile(inspection.page_count, ocr_dpi)
            page_store = PageTextStore(profile.page_spill_threshold, profile.char_spill_threshold)
            if status_callback:
                status_callback(
                    f"Perfil {profile.name}: {inspection.page_count or '?'} páginas, "
                    f"lotes de {profile.render_batch_size}, OCR a {profile.ocr_dpi} DPI."
                )

            def record_extraction_issue(page_index, message):
                extraction_issues.setdefault(page_index, []).append(str(message))

            for page_number, text in enumerate(
                extract_text_pages(
                    file_path,
                    output_format=output_format,
                    use_ocr=use_ocr,
                    lang=lang,
                    allow_markdown_layout=inspection.page_count <= 250,
                    diagnostic_callback=record_extraction_issue,
                ),
                1,
            ):
                analysis = analyze_page_text_quality(text, min_chars=ocr_threshold)
                page_index = page_number - 1
                image_count = inspection.image_counts.get(page_index, 0)
                coverages = inspection.image_coverages.get(page_index, ())
                extraction_issue = "; ".join(extraction_issues.get(page_index, ())) or None
                detail = build_page_detail(
                    page_number,
                    text,
                    "nativo",
                    analysis=analysis,
                    image_count=image_count,
                    image_coverage=max(coverages or (0.0,)),
                    extraction_issue=extraction_issue,
                )
                if extraction_issue:
                    detail["needs_ocr"] = True
                    detail["quality_flags"] = list(detail.get("quality_flags", [])) + ["camada-nativa-incompleta"]
                detail["ocr_image_candidate"] = _image_page_requires_ocr(
                    detail, coverages, has_image=bool(image_count)
                )
                page_store.append(text, detail)
                if inspection.page_count:
                    _report_progress(
                        progress_callback,
                        EXTRACTION_PROGRESS_WEIGHT * page_number / inspection.page_count,
                    )
            if page_store.page_count == 0:
                return build_failure_meta(
                    file_path, output_format, "PDF sem páginas legíveis, vazio, protegido ou corrompido."
                ), None
        else:
            page_store = PageTextStore()
            if ext in {".md", ".markdown"}:
                text = file_path.read_text(encoding="utf-8")
                page_store.append(text, build_page_detail(1, text, "markdown"))
            elif ext == ".docx":
                if docx is None:
                    return build_failure_meta(file_path, output_format, "python-docx não está instalado."), None
                text = extract_docx_text(file_path)
                page_store.append(text, build_page_detail(1, text, "docx"))
            elif ext in {".png", ".jpg", ".jpeg"}:
                if not use_ocr:
                    return build_failure_meta(file_path, output_format, "OCR desativado; imagens exigem OCR."), None
                text = ocr_image_file(
                    str(file_path), lang=lang, tesseract_path=tesseract_path, backend=ocr_backend, delete_after=False
                )
                page_store.append(text, build_page_detail(1, text, "imagem-ocr", image_count=1, ocr_reason="imagem de entrada"))
            else:
                return build_failure_meta(file_path, output_format, f"Formato não suportado: {ext}"), None

        image_pages = set(inspection.image_pages) if inspection else set()
        image_counts = dict(inspection.image_counts) if inspection else {}
        image_coverages = dict(inspection.image_coverages) if inspection else {}
        ocr_image_pages = {
            idx for idx, detail in enumerate(page_store.details)
            if detail.get("ocr_image_candidate")
        }
        if inspection and inspection.warning:
            warnings.append(inspection.warning)
        if inspection and not inspection.reliable:
            if use_ocr:
                force_ocr = True
                warnings.append("Inspeção inconclusiva: OCR integral ativado para não perder prints ou imagens.")

        pages_to_ocr = []
        if use_ocr and ext == ".pdf":
            if tesseract_path and pytesseract is not None:
                pytesseract.pytesseract.tesseract_cmd = str(tesseract_path)
            pages_to_ocr = [
                idx for idx, detail in enumerate(page_store.details)
                if force_ocr or detail.get("needs_ocr") or idx in ocr_image_pages
            ]

            checkpoint = ProcessingCheckpoint(
                file_path,
                out_base,
                {
                    "backend": ocr_backend,
                    "dpi": profile.ocr_dpi,
                    "lang": lang,
                    "threshold": int(ocr_threshold),
                    "force_ocr": bool(force_ocr),
                    "image_ocr_policy": IMAGE_OCR_POLICY_VERSION,
                    "image_pages": sorted(ocr_image_pages),
                    "native_extraction_issue_pages": sorted(extraction_issues),
                },
            )
            pending = []
            for page_index in range(page_store.page_count):
                cached = checkpoint.load(page_index)
                if cached:
                    page_store.set(page_index, cached[0], cached[1])
                elif page_index in pages_to_ocr:
                    pending.append(page_index)
                else:
                    checkpoint.save(page_index, page_store.get_text(page_index), page_store.get_detail(page_index))
            pages_to_ocr = pending

        if pages_to_ocr:
            vision_selected = ocr_backend == "vision" or (ocr_backend == "auto" and is_vision_ocr_available())
            if convert_from_path is None or (not vision_selected and pytesseract is None):
                return build_failure_meta(
                    file_path,
                    output_format,
                    "Dependências de OCR ausentes: pdf2image/Poppler e Vision ou Tesseract são obrigatórios.",
                    warnings,
                ), None
            if status_callback:
                status_callback(
                    f"OCR necessário em {len(pages_to_ocr)} página(s), incluindo imagens com texto em potencial."
                )

            import tempfile
            batches = get_contiguous_batches(pages_to_ocr, profile.render_batch_size)
            completed = 0
            with tempfile.TemporaryDirectory(prefix="hollyocr_") as temp_dir:
                for batch in batches:
                    if should_cancel(cancel_callback):
                        if status_callback:
                            status_callback("Processamento interrompido; progresso salvo para retomada.")
                        return None, None
                    first_page, last_page = batch[0] + 1, batch[-1] + 1
                    try:
                        paths = convert_from_path(
                            str(file_path),
                            dpi=profile.ocr_dpi,
                            first_page=first_page,
                            last_page=last_page,
                            poppler_path=poppler_path,
                            output_folder=temp_dir,
                            paths_only=True,
                            fmt="jpeg",
                            jpegopt={"quality": 95, "optimize": True},
                        )
                    except Exception as exc:
                        warnings.append(f"Falha ao renderizar páginas {first_page}-{last_page}: {exc}")
                        LOGGER.exception("Failed to render PDF pages %s-%s", first_page, last_page)
                        continue

                    pairs = list(zip(batch, paths))
                    if len(pairs) != len(batch):
                        warnings.append(
                            f"Renderização incompleta nas páginas {first_page}-{last_page}: "
                            f"{len(paths)} imagem(ns) para {len(batch)} página(s)."
                        )

                    def consume(page_index, text):
                        nonlocal completed
                        detail = _apply_ocr_result(
                            page_store,
                            page_index,
                            text,
                            ocr_threshold,
                            force_ocr,
                            ocr_image_pages,
                            image_counts,
                            image_coverages,
                        )
                        checkpoint.save(page_index, page_store.get_text(page_index), detail)
                        completed += 1
                        if status_callback:
                            status_callback(f"OCR: {completed}/{len(pages_to_ocr)} páginas")
                        _report_progress(
                            progress_callback,
                            EXTRACTION_PROGRESS_WEIGHT
                            + (0.99 - EXTRACTION_PROGRESS_WEIGHT) * completed / len(pages_to_ocr),
                        )

                    max_workers = min(max(1, int(workers or 1)), max(1, multiprocessing.cpu_count()), len(pairs))
                    if max_workers > 1:
                        def run_parallel(active_executor):
                            futures = {
                                active_executor.submit(
                                    ocr_image_file,
                                    path,
                                    lang,
                                    tesseract_path,
                                    ocr_backend,
                                    True,
                                ): page_index
                                for page_index, path in pairs
                            }
                            for future in as_completed(futures):
                                page_index = futures[future]
                                try:
                                    consume(page_index, future.result())
                                except Exception as exc:
                                    warnings.append(f"OCR falhou na página {page_index + 1}: {exc}")
                                    LOGGER.exception("OCR failed for page %s", page_index + 1)
                        if executor:
                            run_parallel(executor)
                        else:
                            with ProcessPoolExecutor(max_workers=max_workers) as pool:
                                run_parallel(pool)
                    else:
                        for page_index, path in pairs:
                            try:
                                consume(
                                    page_index,
                                    ocr_image_file(
                                        path,
                                        lang=lang,
                                        tesseract_path=tesseract_path,
                                        backend=ocr_backend,
                                        delete_after=True,
                                    ),
                                )
                            except Exception as exc:
                                warnings.append(f"OCR falhou na página {page_index + 1}: {exc}")
                                LOGGER.exception("OCR failed for page %s", page_index + 1)

        if not page_store.has_any_text():
            return build_failure_meta(
                file_path,
                output_format,
                "Não foi possível extrair texto por camada nativa nem OCR.",
                warnings,
            ), None

        index = []
        for idx in range(page_store.page_count):
            text = page_store.get_text(idx)
            detail = page_store.get_detail(idx)
            summary = " ".join(text.strip().splitlines())[:240].strip() or "<sem texto>"
            index.append(
                {
                    "page": idx + 1,
                    "summary": summary,
                    "chars": len(text),
                    "source": detail.get("source"),
                    "quality_score": detail.get("quality_score"),
                    "quality_flags": detail.get("quality_flags", []),
                    "structure_hints": detail.get("structure_hints", []),
                }
            )

        full_text = None
        if write_output:
            out_path = _relative_output_path(file_path, out_base, input_root, output_format)
            write_output_document_atomic(
                out_path, file_path, page_store, index, output_format, page_details=page_store.details
            )
            out_path_str = str(out_path)
        elif compiled_handle is not None:
            _write_output_stream(
                compiled_handle, file_path, page_store, index, False, output_format, page_details=page_store.details
            )
            out_path_str = "Compilado (não salvo individualmente)"
        else:
            full_text = build_output_text(
                file_path, page_store, index, False, output_format, page_details=page_store.details
            )
            out_path_str = "Compilado (não salvo individualmente)"

        audit_path = None
        if page_audit_enabled:
            audit = create_page_audit_output_path(file_path, out_base, input_root)
            write_page_audit_atomic(audit, file_path, index, page_store.details)
            audit_path = str(audit)

        if checkpoint:
            checkpoint.cleanup()
        _report_progress(progress_callback, 1.0)
        return {
            "input_path": str(file_path),
            "output_path": out_path_str,
            "output_format": output_format,
            "pages": page_store.page_count,
            "index": index,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "status": "ok",
            "warnings": warnings,
            "page_audit_path": audit_path,
            "page_details": list(page_store.details),
            "processing_profile": profile.name,
            "image_pages": sorted(page + 1 for page in image_pages),
            "ocr_image_pages": sorted(page + 1 for page in ocr_image_pages),
        }, full_text
    except Exception as exc:
        LOGGER.exception("Unhandled processing error for %s", file_path)
        return build_failure_meta(file_path, output_format, f"Erro durante processamento: {exc}", warnings), None
    finally:
        if page_store is not None:
            page_store.cleanup()
