"""Atomic file writing and assembly of the .txt/.md output document."""

import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from hollyocr.utils.logging_setup import LOGGER
from hollyocr.utils.paths import ensure_dir

from .extraction import get_page_text_at, get_pages_count, normalize_output_format
from .quality import (
    describe_page_detail,
    humanize_page_flags,
    humanize_page_source,
    humanize_structure_hints,
)


def write_text_atomic(path: Path, content: str):
    """Write text via a temporary file and replace the target only after success."""
    ensure_dir(path.parent)
    temp_path = path.parent / f".{path.name}.{os.getpid()}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        os.replace(temp_path, path)
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            LOGGER.warning("Failed to remove temporary output file: %s", temp_path)


def should_cancel(cancel_callback):
    if not cancel_callback:
        return False
    try:
        return bool(cancel_callback())
    except Exception:
        return False


def unique_output_path(path: Path):
    """Avoid overwriting previous conversions with the same output name."""
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def build_failure_meta(file_path: Path, output_format: str, error: str, warnings=None):
    return {
        "input_path": str(file_path),
        "output_path": "",
        "output_format": normalize_output_format(output_format),
        "pages": 0,
        "index": [],
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "status": "failed",
        "error": error,
        "warnings": warnings or [],
    }


def create_page_audit_output_path(file_path: Path, out_base: Path, input_root: Path):
    try:
        rel = file_path.relative_to(input_root)
        if str(rel) == '.':
            rel = file_path.name
    except Exception:
        rel = file_path.name
    return unique_output_path(out_base / Path(str(rel)).with_name(f"{Path(str(rel)).stem}_paginas.jsonl"))


def write_page_audit_atomic(path: Path, file_path: Path, index, page_details):
    """Write one JSONL record per page for evidentiary traceability."""
    ensure_dir(path.parent)
    temp_path = path.parent / f".{path.name}.{os.getpid()}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8", newline="\n") as handle:
            for idx, item in enumerate(index):
                detail = page_details[idx] if idx < len(page_details) else {}
                record = {
                    "input_file": str(file_path),
                    "page": int(item.get("page", idx + 1)),
                    "summary": item.get("summary", ""),
                    "char_count": int(item.get("chars", 0) or 0),
                    "source": detail.get("source"),
                    "source_label": humanize_page_source(detail.get("source")),
                    "quality_score": int(detail.get("quality_score", 0) or 0),
                    "quality_flags": list(detail.get("quality_flags", [])),
                    "structure_hints": list(detail.get("structure_hints", [])),
                    "needs_ocr": bool(detail.get("needs_ocr", False)),
                    "image_count": int(detail.get("image_count", 0) or 0),
                    "image_coverage": float(detail.get("image_coverage", 0.0) or 0.0),
                    "ocr_image_candidate": bool(detail.get("ocr_image_candidate", False)),
                    "extraction_issue": detail.get("extraction_issue"),
                    "ocr_reason": detail.get("ocr_reason"),
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        os.replace(temp_path, path)
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            LOGGER.warning("Failed to remove temporary page audit file: %s", temp_path)


def build_compiled_header(total, output_format='txt'):
    output_format = normalize_output_format(output_format)
    now = datetime.now()
    if output_format == 'md':
        return f"# Relatório compilado\n\n- Gerado em: {now}\n- Total de arquivos: {total}\n\n"
    return f"RELATÓRIO COMPILADO - {now}\nTotal de arquivos: {total}\n" + "="*60 + "\n\n"


def build_compiled_separator(output_format='txt'):
    output_format = normalize_output_format(output_format)
    if output_format == 'md':
        return "\n---\n\n"
    return "\n" + "="*60 + "\n\n"


def _write_output_stream(handle, file_path: Path, pages_text, index, write_output=True, output_format='txt', page_details=None):
    page_details = page_details or []
    output_format = normalize_output_format(output_format)
    if output_format == 'md':
        if write_output:
            handle.write(f"# {file_path.name}\n")
        else:
            handle.write(f"# Arquivo: {file_path.name}\n")

        source_counts = {}
        image_pages = 0
        ocr_image_pages = 0
        extraction_issue_pages = 0
        for detail in page_details:
            source = humanize_page_source(detail.get("source"))
            source_counts[source] = source_counts.get(source, 0) + 1
            image_pages += int(bool(detail.get("image_count")))
            ocr_image_pages += int(bool(detail.get("ocr_image_candidate")))
            extraction_issue_pages += int(bool(detail.get("extraction_issue")))
        handle.write("\n## Resumo da extração\n\n")
        handle.write(f"- Páginas processadas: {get_pages_count(pages_text)}\n")
        handle.write(f"- Páginas com elementos gráficos detectados: {image_pages}\n")
        handle.write(f"- Páginas com imagens relevantes para OCR: {ocr_image_pages}\n")
        if extraction_issue_pages:
            handle.write(
                f"- Páginas com camada nativa incompleta recuperadas por OCR: {extraction_issue_pages}\n"
            )
        for source, count in sorted(source_counts.items()):
            handle.write(f"- {source}: {count}\n")

        handle.write("\n## Índice\n\n")
        for idx, it in enumerate(index):
            detail = page_details[idx] if idx < len(page_details) else None
            meta_suffix = ""
            if detail:
                meta_suffix = (
                    f" [{humanize_page_source(detail.get('source'))}, "
                    f"qualidade {detail.get('quality_score', 0)}/100"
                )
                detail_flags = humanize_page_flags(detail.get("quality_flags"))
                if detail_flags:
                    meta_suffix += f", alertas: {', '.join(detail_flags)}"
                structure_hints = humanize_structure_hints(detail.get("structure_hints"))
                if structure_hints:
                    meta_suffix += f", estrutura: {', '.join(structure_hints)}"
                meta_suffix += "]"
            handle.write(f"- Página {it['page']}{meta_suffix}: {it['summary']}\n")
        handle.write("\n")

        for i in range(get_pages_count(pages_text)):
            txt = get_page_text_at(pages_text, i)
            handle.write(f"## Página {i+1}\n\n")
            detail = page_details[i] if i < len(page_details) else None
            detail_line = describe_page_detail(detail)
            if detail_line:
                handle.write(f"> {detail_line}\n\n")
            handle.write((txt or '') + "\n\n")
        return

    if not write_output:
        handle.write(f"=== ARQUIVO: {file_path.name} ===\n")

    handle.write('ÍNDICE (resumo por página)\n')
    handle.write('------------------------------\n')
    for idx, it in enumerate(index):
        detail = page_details[idx] if idx < len(page_details) else None
        meta_suffix = ""
        if detail:
            meta_suffix = f" [{humanize_page_source(detail.get('source'))} | qualidade {detail.get('quality_score', 0)}/100"
            detail_flags = humanize_page_flags(detail.get("quality_flags"))
            if detail_flags:
                meta_suffix += f" | alertas: {', '.join(detail_flags)}"
            structure_hints = humanize_structure_hints(detail.get("structure_hints"))
            if structure_hints:
                meta_suffix += f" | estrutura: {', '.join(structure_hints)}"
            meta_suffix += "]"
        handle.write(f"Página {it['page']}{meta_suffix}: {it['summary']}\n")
    handle.write('\n')
    for i in range(get_pages_count(pages_text)):
        txt = get_page_text_at(pages_text, i)
        handle.write(f"=== Página {i+1} ===\n")
        detail = page_details[i] if i < len(page_details) else None
        detail_line = describe_page_detail(detail)
        if detail_line:
            handle.write(f"[Meta] {detail_line}\n")
        handle.write((txt or '') + "\n\n")


def build_output_text(file_path: Path, pages_text, index, write_output=True, output_format='txt', page_details=None):
    buffer = io.StringIO()
    _write_output_stream(
        buffer,
        file_path,
        pages_text,
        index,
        write_output=write_output,
        output_format=output_format,
        page_details=page_details,
    )
    return buffer.getvalue()


def write_output_document_atomic(path: Path, file_path: Path, pages_text, index, output_format='txt', page_details=None):
    """Write converted output without building the whole document in memory."""
    output_format = normalize_output_format(output_format)
    ensure_dir(path.parent)
    temp_path = path.parent / f".{path.name}.{os.getpid()}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8", newline="\n") as f:
            _write_output_stream(
                f,
                file_path,
                pages_text,
                index,
                write_output=True,
                output_format=output_format,
                page_details=page_details,
            )
        os.replace(temp_path, path)
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            LOGGER.warning("Failed to remove temporary output file: %s", temp_path)
