"""Filesystem paths: app-data dir, config/log/crash file locations, and
resolution of bundled Poppler/Tesseract binaries."""

import os
import shutil
import sys
from pathlib import Path

from hollyocr.version import APP_NAME

CONFIG_FILENAME = "user_settings.json"
LEGACY_APP_NAMES = ("PDF_OCR_Converter",)


def get_app_data_dir(app_name=APP_NAME):
    """Return the per-user directory for settings and crash logs."""
    if os.name == 'nt':
        base = os.environ.get('APPDATA') or os.environ.get('LOCALAPPDATA')
        if base:
            return Path(base) / app_name
    elif sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / app_name
    else:
        base = os.environ.get('XDG_CONFIG_HOME')
        return (Path(base) if base else Path.home() / '.config') / app_name


def get_config_path():
    return get_app_data_dir() / CONFIG_FILENAME


def get_legacy_config_paths():
    """Retorna preferências de versões anteriores para migração única."""
    return [get_app_data_dir(app_name) / CONFIG_FILENAME for app_name in LEGACY_APP_NAMES]


def get_crash_log_path():
    try:
        app_dir = get_app_data_dir()
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir / "CRASH_LOG.txt"
    except OSError:
        return Path.cwd() / "CRASH_LOG.txt"


def get_log_path():
    """Return the per-user technical log path."""
    try:
        app_dir = get_app_data_dir()
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir / f"{APP_NAME}.log"
    except OSError:
        return Path.cwd() / f"{APP_NAME}.log"


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def unique_paths(paths):
    """Return normalized paths without duplicates while preserving order."""
    seen = set()
    result = []
    for path in paths:
        if not path:
            continue
        try:
            resolved = Path(path).resolve()
        except (OSError, RuntimeError):
            continue
        key = str(resolved).lower() if os.name == 'nt' else str(resolved)
        if key not in seen:
            seen.add(key)
            result.append(resolved)
    return result


def get_runtime_roots():
    """Locations that may contain bundled assets in source or PyInstaller mode."""
    roots = []
    if getattr(sys, 'frozen', False):
        roots.append(Path(sys.executable).resolve().parent)
        if hasattr(sys, '_MEIPASS'):
            roots.append(Path(sys._MEIPASS))

    script_dir = Path(__file__).resolve().parent
    roots.extend([script_dir, script_dir.parent, Path.cwd()])
    return unique_paths(roots)


def normalize_tesseract_path(path, exe_ext):
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / f'tesseract{exe_ext}'
    return str(candidate)


def get_dependencies_paths(args_poppler=None, args_tesseract=None):
    """Resolve paths for Poppler and Tesseract from args, bundled folders, and PATH."""
    is_windows = os.name == 'nt'
    exe_ext = ".exe" if is_windows else ""
    runtime_roots = get_runtime_roots()

    # 1. Poppler
    poppler = args_poppler
    if not poppler:
        base_dirs = []
        for root in runtime_roots:
            base_dirs.extend([
                root / 'bin' / 'poppler',
                root / 'poppler',
                root / 'bin',
            ])

            bin_dir = root / 'bin'
            if bin_dir.exists():
                for child in bin_dir.iterdir():
                    if child.is_dir() and 'poppler' in child.name.lower():
                        base_dirs.insert(0, child)

        if not is_windows:
            base_dirs.extend([
                Path('/opt/homebrew/bin'),  # Mac Apple Silicon
                Path('/usr/local/bin'),     # Mac Intel / Linux
                Path('/usr/bin')
            ])

        possible_subdirs = [
            Path('Library') / 'bin',
            Path('bin'),
            Path('.')
        ]

        pdftoppm = shutil.which(f'pdftoppm{exe_ext}') or shutil.which('pdftoppm')
        poppler_from_path = str(Path(pdftoppm).parent) if pdftoppm else None

        for base in unique_paths(base_dirs):
            if poppler:
                break
            if not base.exists():
                continue

            if (base / f'pdftoppm{exe_ext}').exists():
                poppler = str(base)
                break

            for sub in possible_subdirs:
                p = base / sub
                if (p / f'pdftoppm{exe_ext}').exists():
                    poppler = str(p)
                    break

        if not poppler and poppler_from_path:
            poppler = poppler_from_path

    # 2. Tesseract
    tesseract = args_tesseract
    if tesseract:
        tesseract = normalize_tesseract_path(tesseract, exe_ext)
    else:
        possible_tesseracts = []
        for root in runtime_roots:
            possible_tesseracts.extend([
                root / 'bin' / 'Tesseract-OCR' / f'tesseract{exe_ext}',
                root / 'Tesseract-OCR' / f'tesseract{exe_ext}',
            ])

        if is_windows:
            local_appdata = os.environ.get('LOCALAPPDATA')
            possible_tesseracts.extend([
                Path(r'C:\Program Files\Tesseract-OCR\tesseract.exe'),
                Path(r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'),
            ])
            if local_appdata:
                possible_tesseracts.append(Path(local_appdata) / 'Tesseract-OCR' / 'tesseract.exe')
        else:
            possible_tesseracts.extend([
                Path('/opt/homebrew/bin/tesseract'),  # Mac Apple Silicon
                Path('/usr/local/bin/tesseract'),     # Mac Intel
                Path('/usr/bin/tesseract')
            ])

        if 'TESSDATA_PREFIX' in os.environ:
            p = Path(os.environ['TESSDATA_PREFIX']).parent / f'tesseract{exe_ext}'
            if p.exists():
                possible_tesseracts.insert(0, p)

        which_tesseract = shutil.which(f'tesseract{exe_ext}') or shutil.which('tesseract')
        if which_tesseract:
            possible_tesseracts.append(Path(which_tesseract))

        for candidate in unique_paths(possible_tesseracts):
            if candidate.exists():
                tesseract = str(candidate)
                break

    return poppler, tesseract
