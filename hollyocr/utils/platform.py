"""OS/hardware detection, console-window hiding, and native file opening."""

import multiprocessing
import os
import platform
import shutil
import subprocess
import sys


def is_apple_silicon():
    """Return True when running on Apple Silicon (arm64/aarch64)."""
    if sys.platform != "darwin":
        return False
    machine = (platform.machine() or "").lower()
    return machine in {"arm64", "aarch64"}


def recommended_ocr_workers(backend="tesseract", max_cap_non_macos=4,
                            max_cap_apple_silicon_tesseract=6,
                            max_cap_apple_silicon_vision=4):
    """Pick a conservative parallel worker count for OCR tasks.

    backend: 'tesseract' scales nicely up to ~6 workers on M-class chips; 'vision'
    (Apple Vision) tops out at ~4 because the Neural Engine already parallelizes
    internally and extra processes only add fork/IPC overhead.
    """
    try:
        cpu_total = max(1, multiprocessing.cpu_count())
    except Exception:
        return 1

    if is_apple_silicon():
        cap = max_cap_apple_silicon_vision if backend == "vision" else max_cap_apple_silicon_tesseract
        return max(2, min(cap, cpu_total - 1 if cpu_total > 2 else cpu_total))

    return max(1, min(max_cap_non_macos, cpu_total - 1 if cpu_total > 1 else cpu_total))


def is_macos_legacy_tk(tk_module):
    """Detect the macOS system Tk build that renders CustomTkinter unreliably."""
    if sys.platform != "darwin":
        return False
    try:
        patchlevel = str(tk_module.Tcl().eval("info patchlevel"))
    except Exception:
        patchlevel = ""
    return patchlevel.startswith("8.5")


def open_path_natively(path):
    """Open a file or folder in the default system viewer/explorer."""
    candidate = os.path.abspath(os.fspath(path))
    if not os.path.exists(candidate):
        raise FileNotFoundError(candidate)
    if os.name == 'nt':
        os.startfile(candidate)
    elif sys.platform == 'darwin':
        subprocess.Popen(  # nosec B603
            ['/usr/bin/open', candidate],
            shell=False,
            start_new_session=True,
        )
    else:
        opener = shutil.which('xdg-open')
        if not opener:
            raise RuntimeError("xdg-open não foi encontrado neste sistema.")
        subprocess.Popen(  # nosec B603
            [opener, candidate],
            shell=False,
            start_new_session=True,
        )


def hide_ocr_console_windows():
    """Hide Poppler/Tesseract helper consoles on Windows."""
    if os.name != 'nt':
        return

    create_no_window = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)

    try:
        import pdf2image.pdf2image as pdf2image_module
        if not getattr(pdf2image_module, '_hollyocr_hidden_popen', False):
            original_popen = pdf2image_module.Popen

            def hidden_popen(*args, **kwargs):
                kwargs['creationflags'] = kwargs.get('creationflags', 0) | create_no_window
                startupinfo = kwargs.get('startupinfo')
                if startupinfo is None and hasattr(subprocess, 'STARTUPINFO'):
                    startupinfo = subprocess.STARTUPINFO()
                if startupinfo is not None:
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    try:
                        startupinfo.wShowWindow = subprocess.SW_HIDE
                    except Exception:
                        pass
                    kwargs['startupinfo'] = startupinfo
                return original_popen(*args, **kwargs)

            pdf2image_module.Popen = hidden_popen
            pdf2image_module._hollyocr_hidden_popen = True
    except Exception:
        pass

    try:
        import pytesseract.pytesseract as pytesseract_module
        if not getattr(pytesseract_module, '_hollyocr_hidden_subprocess', False):
            original_subprocess_args = pytesseract_module.subprocess_args

            def hidden_subprocess_args(include_stdout=True):
                kwargs = original_subprocess_args(include_stdout)
                kwargs['creationflags'] = kwargs.get('creationflags', 0) | create_no_window
                startupinfo = kwargs.get('startupinfo')
                if startupinfo is None and hasattr(subprocess, 'STARTUPINFO'):
                    startupinfo = subprocess.STARTUPINFO()
                if startupinfo is not None:
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    try:
                        startupinfo.wShowWindow = subprocess.SW_HIDE
                    except Exception:
                        pass
                    kwargs['startupinfo'] = startupinfo
                return kwargs

            pytesseract_module.subprocess_args = hidden_subprocess_args
            pytesseract_module._hollyocr_hidden_subprocess = True
    except Exception:
        pass
