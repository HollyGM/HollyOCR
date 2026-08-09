# -*- mode: python ; coding: utf-8 -*-
"""Cross-platform PyInstaller recipe.

macOS builds produce a native arm64 .app bundle. Windows keeps the historical
single-file executable behavior used by build_exe.bat.
"""

import importlib.util
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


project_root = Path(SPECPATH).resolve() if 'SPECPATH' in globals() else Path.cwd().resolve()
is_macos = sys.platform == 'darwin'

version_source = (project_root / 'hollyocr' / 'version.py').read_text(encoding='utf-8')
_version_match = re.search(r'^VERSION\s*=\s*"([^"]+)"', version_source, re.MULTILINE)
_build_match = re.search(r'^BUILD\s*=\s*(\d+)', version_source, re.MULTILINE)
app_version = _version_match.group(1) if _version_match else '0.0.0'
app_build = _build_match.group(1) if _build_match else '1'
datas = []
binaries = []
hiddenimports = [
    'PIL._tkinter_finder',
    'tkinter',
    'docx',
    'packaging',
    'pymupdf',
    'fitz',
    'urllib.request',
]

for asset_name in ('logo.icns', 'logo.ico', 'logo_ui.png', 'logo.png'):
    asset_path = project_root / asset_name
    if asset_path.exists():
        datas.append((str(asset_path), '.'))


def add_data_tree(source, destination, excluded_names=None):
    excluded_names = {name.lower() for name in (excluded_names or set())}
    if not source.exists():
        return
    for file_path in source.rglob('*'):
        if not file_path.is_file() or file_path.name.lower() in excluded_names:
            continue
        relative_parent = file_path.relative_to(source).parent
        datas.append((str(file_path), str(Path(destination) / relative_parent)))


# Windows may optionally ship a local Poppler tree. macOS deliberately uses
# the system/Homebrew Poppler installation and does not embed it.
if not is_macos:
    bin_dir = project_root / 'bin'
    poppler_candidates = [bin_dir / 'poppler']
    if bin_dir.exists():
        poppler_candidates.extend(sorted(bin_dir.glob('*poppler*')))
    for candidate in poppler_candidates:
        if (
            (candidate / 'Library' / 'bin' / 'pdftoppm.exe').exists()
            or (candidate / 'bin' / 'pdftoppm.exe').exists()
            or (candidate / 'pdftoppm.exe').exists()
        ):
            poppler_bin = candidate / 'Library' / 'bin'
            if not poppler_bin.exists():
                poppler_bin = candidate / 'bin' if (candidate / 'bin').exists() else candidate
            add_data_tree(poppler_bin, Path('poppler') / 'Library' / 'bin', {'poppler-glib.dll'})
            add_data_tree(candidate / 'share' / 'poppler', Path('poppler') / 'share' / 'poppler')
            break


def collect_package(name):
    package_datas, package_binaries, package_hidden = collect_all(name)
    datas.extend(package_datas)
    binaries.extend(package_binaries)
    hiddenimports.extend(package_hidden)


collect_package('customtkinter')
if importlib.util.find_spec('tkinterdnd2') is not None:
    collect_package('tkinterdnd2')

if is_macos:
    # PyObjC frameworks expose Python modules plus metadata files. Collecting
    # both packages ensures Vision and its Quartz dependency survive analysis.
    collect_package('Vision')
    collect_package('Quartz')
    hiddenimports.extend(['Vision', 'Quartz', 'Cocoa', 'Foundation', 'CoreML', 'objc'])


a = Analysis(
    [str(project_root / 'hollyocr' / 'app.py')],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # pymupdf4llm is deliberately disabled in the frozen macOS app for
    # stability. Excluding its layout/ONNX chain avoids ~60 MB of dead weight;
    # plain PyMuPDF remains bundled and can still be enabled explicitly.
    excludes=(
        ['pymupdf4llm', 'pymupdf_layout', 'onnxruntime', 'pytest', '_pytest']
        if is_macos else []
    ),
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

if is_macos:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='HollyOCR',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch='arm64',
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name='HollyOCR',
    )
    app = BUNDLE(
        coll,
        name='HollyOCR.app',
        icon=str(project_root / 'logo.icns'),
        bundle_identifier='com.thiagoalbuquerque.hollyocr',
        info_plist={
            'CFBundleDisplayName': 'HollyOCR',
            'CFBundleShortVersionString': app_version,
            'CFBundleVersion': app_build,
            'LSMinimumSystemVersion': '12.0',
            'NSHighResolutionCapable': True,
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='HollyOCR',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=[str(project_root / 'logo.ico')],
    )
