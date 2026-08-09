"""The ProcessPoolExecutor batch loop shared by both GUI front-ends.

Both gui.classic_tk.window and gui.modern_ctk.window had their own
hand-written copy of "open one ProcessPoolExecutor, loop over file_list,
call core.pipeline.process_file for each, track progress/status, optionally
append to a compiled-output file handle." This module is that loop, factored
out behind small callbacks so each GUI can keep its own widgets, its own
UI-thread marshaling (root.after vs. the plain-Tk post_ui/queue drain), and
its own message wording for file discovery and the final result dialog --
none of which is touched here.
"""

from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

from hollyocr.core.output_writer import (
    build_compiled_header,
    build_compiled_separator,
    build_failure_meta,
    unique_output_path,
)
from hollyocr.core.pipeline import process_file
from hollyocr.utils.logging_setup import LOGGER


def open_compiled_handle(out_base: Path, total: int, output_format: str):
    """Create and header-stamp the compiled-mode output file. Raises on failure
    so callers can show their own error dialog."""
    comp_filename = f"COMPILADO_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{output_format}"
    comp_path = unique_output_path(out_base / comp_filename)
    handle = open(comp_path, "w", encoding="utf-8")
    handle.write(build_compiled_header(total, output_format))
    return handle


def run_conversion_loop(
    file_list,
    out_base: Path,
    input_root: Path,
    *,
    poppler_path,
    tesseract_path,
    lang,
    ocr_threshold,
    ocr_dpi,
    use_ocr,
    force_ocr,
    page_audit_enabled,
    output_format,
    output_mode,
    workers,
    should_stop,
    describe_file_progress,
    make_status_callback,
    on_file_status,
    on_progress,
    on_status,
    compiled_handle=None,
    ocr_backend='tesseract',
):
    """Run process_file() over file_list with one shared ProcessPoolExecutor.

    file_list must already be resolved and non-empty -- file discovery and
    the "no files found" message stay in each GUI, since their wording and
    follow-up actions (reset_buttons, dialog title, ...) differ.

    compiled_handle, if given, must already be open (see open_compiled_handle)
    and is always closed before returning, even on error.

    Returns the list of per-file meta dicts (see core.pipeline.process_file).
    """
    total = len(file_list)
    metas = []
    try:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            for index, fpath in enumerate(file_list, 1):
                if should_stop():
                    on_status("Cancelado pelo usuário.")
                    break

                on_file_status(fpath, "Processando")
                on_status(describe_file_progress(index, total, fpath))
                status_cb = make_status_callback(index, total, fpath)

                def on_page_progress(fraction, current_index=index):
                    # Blend intra-file progress (0..1) into the global percentage
                    # so single large files no longer sit at 0% until the end.
                    on_progress(int(((current_index - 1) + fraction) * 100 / total))

                try:
                    meta, text_content = process_file(
                        fpath,
                        out_base,
                        input_root,
                        poppler_path=poppler_path,
                        tesseract_path=tesseract_path,
                        ocr_threshold=ocr_threshold,
                        lang=lang,
                        workers=workers,
                        executor=executor,
                        status_callback=status_cb,
                        write_output=(output_mode == "individual"),
                        output_format=output_format,
                        use_ocr=use_ocr,
                        force_ocr=force_ocr,
                        ocr_dpi=ocr_dpi,
                        compiled_handle=compiled_handle if output_mode == "compiled" else None,
                        cancel_callback=should_stop,
                        page_audit_enabled=page_audit_enabled,
                        ocr_backend=ocr_backend,
                        progress_callback=on_page_progress,
                    )
                    if meta:
                        metas.append(meta)
                        if meta.get("status") == "ok":
                            on_file_status(fpath, "Convertido")
                            if output_mode == "compiled" and compiled_handle:
                                if text_content:
                                    compiled_handle.write(text_content)
                                compiled_handle.write(build_compiled_separator(output_format))
                        else:
                            on_file_status(fpath, "Erro")
                except Exception as exc:
                    LOGGER.exception("Unhandled error processing %s", fpath)
                    metas.append(build_failure_meta(fpath, output_format, f"Erro inesperado: {exc}"))
                    on_file_status(fpath, "Erro")
                finally:
                    on_progress(int(index * 100 / total))
    finally:
        if compiled_handle:
            try:
                compiled_handle.close()
            except Exception:
                pass

    return metas
