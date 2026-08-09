"""Logo / icon discovery for the GUI windows.

The app bundles several logo formats (`logo.png`, `logo_ui.png`, `logo.ico`,
`logo.icns`) so it can look right on Windows, macOS, and the in-app header.
The build pipeline (PyInstaller .spec) drops them next to the executable, but
when running from source they're next to `hollyocr/`. `get_resource_path`
unifies those two cases plus a CWD fallback so unit tests and frozen builds
both work.
"""

import os
import sys


def get_resource_path(relative_path):
    """Locate a bundled asset (logo, etc.) regardless of run mode.

    Order:
    1. Next to the frozen binary (`sys._MEIPASS` for PyInstaller onefile).
    2. Next to this file (when running from source).
    3. The current working directory (when invoked from the project root).

    Returns the absolute path to the asset. Does NOT check existence -- caller
    decides what to do when the file is missing.
    """
    base_path = getattr(sys, "_MEIPASS", None)
    if not base_path or not os.path.exists(os.path.join(base_path, relative_path)):
        # Source-tree layout: assets live next to hollyocr/, which is the
        # parent of the gui/modern_ctk/ package directory.
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if not os.path.exists(os.path.join(base_path, relative_path)):
            base_path = os.getcwd()
    return os.path.join(base_path, relative_path)


def find_logo_paths():
    """Return (ui_logo_path, icon_path), each a str or None.

    Prefers PNG/JPG for the UI image (looks sharper on the header) and ICO
    for the window icon (Windows convention).
    """
    ui_logo_path = None
    icon_path = None
    for name in ["logo_ui.png", "logo.png", "logo.jpg", "logo.jpeg", "logo.ico"]:
        candidate = get_resource_path(name)
        if os.path.exists(candidate):
            ui_logo_path = candidate
            break
    for name in ["logo.ico", "logo.png", "logo.jpg", "logo.jpeg"]:
        candidate = get_resource_path(name)
        if os.path.exists(candidate):
            icon_path = candidate
            break
    return ui_logo_path, icon_path