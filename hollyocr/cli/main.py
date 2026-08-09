"""Command-line entry point: argument parsing and the no-GUI conversion loop."""

import argparse
import sys
from pathlib import Path

from hollyocr.core.extraction import find_files
from hollyocr.core.ocr import check_ocr_environment
from hollyocr.core.output_writer import build_failure_meta
from hollyocr.core.pipeline import process_file
from hollyocr.core.vision_ocr import is_vision_ocr_available
from hollyocr.gui.modern_ctk.window import choose_input_output_gui
from hollyocr.utils.logging_setup import (
    LOGGER,
    NullWriter,
    is_interactive_terminal_stream,
)
from hollyocr.utils.paths import ensure_dir, get_dependencies_paths, get_log_path
from hollyocr.utils.platform import recommended_ocr_workers

try:
    from tqdm import tqdm
except Exception:
    def tqdm(iterable=None, **_kwargs):
        return iterable if iterable is not None else []


def bounded_int(label, minimum, maximum):
    """Create an argparse converter with a clear, bounded numeric range."""
    def parse(value):
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise argparse.ArgumentTypeError(f"{label} deve ser um número inteiro.") from exc
        if not minimum <= parsed <= maximum:
            raise argparse.ArgumentTypeError(
                f"{label} deve estar entre {minimum} e {maximum}."
            )
        return parsed

    return parse


def main():
    ap = argparse.ArgumentParser(
        prog="HollyOCR",
        description="Converta PDFs, imagens, DOCX e Markdown com OCR local.",
    )
    ap.add_argument('-i', '--input', required=False, help='Input file or directory')
    ap.add_argument('-o', '--output-dir', required=False, help='Directory to write output files')
    ap.add_argument('--poppler-path', default=None, help='Path to poppler bin (Windows)')
    ap.add_argument('--tesseract-path', default=None, help='Path to tesseract executable (optional)')
    ap.add_argument('--ocr-threshold', type=bounded_int('Limiar de OCR', 1, 5000), default=30,
                    help='Min chars to skip OCR (default 30; range 1-5000)')
    ap.add_argument('--ocr-dpi', type=bounded_int('DPI do OCR', 300, 450), default=300,
                    help='DPI used to render PDF pages before OCR (default 300; range 300-450)')
    ap.add_argument('--lang', default='por', help="OCR language for Tesseract (default 'por' for Portuguese)")
    ap.add_argument('--output-format', choices=['txt', 'md'], default='md', help='Output format: txt or md (default md)')
    ap.add_argument('--gui', action='store_true', help='Open GUI prompts to select input/output')
    ap.add_argument('--workers', type=bounded_int('Número de processos', 1, 32), default=None,
                    help='Number of parallel worker processes (default: auto; range 1-32)')
    ap.add_argument('--no-ocr', '--disable-ocr', dest='no_ocr', action='store_true', help='Disable OCR and only extract existing selectable text')
    ap.add_argument('--force-ocr', action='store_true', help='Force OCR on all pages regardless of text content')
    ap.add_argument('--ocr-backend', choices=['auto', 'tesseract', 'vision'], default='auto',
                    help='OCR backend: auto (Vision on macOS when available, else Tesseract), '
                         'tesseract (legacy), or vision (force Apple Vision; macOS only)')
    ap.add_argument('--page-audit', action='store_true', help='Generate a per-page JSONL audit sidecar file next to each output (off by default)')
    args = ap.parse_args()

    # If GUI requested or input/output not provided, open GUI dialogs
    input_arg = args.input
    output_arg = args.output_dir

    # Resolve dependencies
    poppler_path, tesseract_path = get_dependencies_paths(args.poppler_path, args.tesseract_path)

    # Validate --ocr-backend=vision on non-macOS or missing bindings.
    if args.ocr_backend == 'vision' and not is_vision_ocr_available():
        print('AVISO: --ocr-backend=vision selecionado, mas Apple Vision não está disponível.')
        print('       Caindo para Tesseract (defina --ocr-backend=tesseract para suprimir este aviso).')
        ocr_backend = 'tesseract'
    else:
        ocr_backend = args.ocr_backend

    if args.gui or (not input_arg or not output_arg):
        try:
            # Se abrir a GUI, o processo ocorre todo lá dentro.
            # Quando a janela fecha, o programa deve encerrar.
            choose_input_output_gui(poppler_path, tesseract_path)
            sys.exit(0)
        except Exception as e:
            print('Falha ao abrir GUI:', e)
            sys.exit(1)

    # O código abaixo será executado APENAS se for via linha de comando (sem GUI)
    use_ocr = not args.no_ocr
    ocr_issues = check_ocr_environment(poppler_path, tesseract_path, args.lang) if use_ocr else []
    if use_ocr and ocr_issues:
        print("AVISO: OCR pode falhar em PDFs escaneados ou imagens:")
        for issue in ocr_issues:
            print(f"- {issue}")

    # Handle input_arg: can be a list of files, a single file path string, or a directory path
    if isinstance(input_arg, list):
        # Multiple files selected - use parent of first file as input_root
        input_path = input_arg  # Keep as list for find_pdfs
        input_root = Path(input_arg[0]).parent
    else:
        input_path = Path(input_arg)
        input_root = input_path if input_path.is_dir() else input_path.parent

    out_base = Path(output_arg)
    ensure_dir(out_base)

    # poppler_path and tesseract_path are already resolved above

    metas = []
    file_list = list(find_files(input_path))
    if not file_list:
        print('Nenhum arquivo encontrado em', input_arg)
        sys.exit(1)

    # Process files sequentially but use per-page parallelism inside each file (controlled by --workers).
    show_terminal_progress = (
        not isinstance(sys.stderr, NullWriter)
        and is_interactive_terminal_stream(sys.stderr)
    )
    for fpath in tqdm(file_list, desc='Processando arquivos', disable=not show_terminal_progress):
        try:
            meta, _ = process_file(
                fpath,
                out_base,
                input_root,
                poppler_path=poppler_path,
                tesseract_path=tesseract_path,
                ocr_threshold=args.ocr_threshold,
                lang=args.lang,
                workers=args.workers if args.workers is not None else recommended_ocr_workers(backend=ocr_backend),
                output_format=args.output_format,
                use_ocr=use_ocr,
                force_ocr=(use_ocr and args.force_ocr),
                ocr_dpi=args.ocr_dpi,
                page_audit_enabled=args.page_audit,
                ocr_backend=ocr_backend,
            )
            if meta:
                metas.append(meta)
        except KeyboardInterrupt:
            print('\nInterrompido pelo usuário')
            break
        except Exception as e:
            LOGGER.exception("Unhandled error processing %s", fpath)
            metas.append(build_failure_meta(fpath, args.output_format, f"Erro inesperado: {e}"))
            print(f'Erro processando {fpath}: {e}')

    success_count = sum(1 for meta in metas if meta.get('status') == 'ok')
    failed_count = sum(1 for meta in metas if meta.get('status') == 'failed')
    print(f'Concluído. {success_count} convertido(s), {failed_count} falha(s). Arquivos gerados em {out_base}')
    if failed_count:
        print('Consulte o log técnico em', get_log_path())
        sys.exit(2)
