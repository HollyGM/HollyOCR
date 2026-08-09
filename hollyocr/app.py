#!/usr/bin/env python3
"""Ponto de entrada compatível para a interface e a linha de comando.

Uso: python hollyocr/app.py -i <entrada> -o <destino>

O processamento vive nos subpacotes ``cli``, ``gui`` e ``core``. Este módulo
também reexporta os auxiliares estáveis usados por integrações e testes.
"""

import multiprocessing
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Allow `from hollyocr.xxx import yyy` to resolve when this file is run
# directly as a script (python hollyocr/app.py), which is how the
# .bat/.sh launchers and the PyInstaller .spec files invoke it.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from hollyocr import __author__, __build__, __version__
from hollyocr.core.extraction import normalize_output_format
from hollyocr.core.output_writer import (
    build_compiled_header,
    build_compiled_separator,
    unique_output_path,
    write_output_document_atomic,
)
from hollyocr.core.pipeline import process_file
from hollyocr.utils.logging_setup import (
    NullWriter,
    is_interactive_terminal_stream,
    is_stream_usable,
)
from hollyocr.utils.paths import get_crash_log_path
from hollyocr.utils.platform import hide_ocr_console_windows

__all__ = [
    "__author__",
    "__build__",
    "__version__",
    "build_compiled_header",
    "build_compiled_separator",
    "normalize_output_format",
    "process_file",
    "unique_output_path",
    "write_output_document_atomic",
]

hide_ocr_console_windows()


if __name__ == '__main__':
    multiprocessing.freeze_support()

    # Setup robust error logging for silent crashes in windowed mode
    try:
        # Fix for pyinstaller --noconsole mode where stdout/stderr can be None or invalid.
        frozen_without_interactive_console = (
            getattr(sys, 'frozen', False)
            and os.name == 'nt'
            and not is_interactive_terminal_stream(sys.stdout)
        )
        if frozen_without_interactive_console or not is_stream_usable(sys.stdout):
            sys.stdout = NullWriter()
        if frozen_without_interactive_console or not is_stream_usable(sys.stderr):
            sys.stderr = NullWriter()

        from hollyocr.cli.main import main
        main()
    except Exception:
        # Critical error handler: writes to CRASH_LOG.txt in the user app-data folder
        try:
            with open(get_crash_log_path(), "w", encoding="utf-8") as f:
                f.write(f"FATAL ERROR - {datetime.now(timezone.utc).isoformat()}\n")
                traceback.print_exc(file=f)
        except OSError as log_error:
            if is_stream_usable(sys.__stderr__):
                sys.__stderr__.write(f"HollyOCR não conseguiu gravar o relatório de falha: {log_error}\n")
        sys.exit(1)
