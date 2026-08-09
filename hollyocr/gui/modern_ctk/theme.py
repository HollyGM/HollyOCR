"""Visual constants and appearance-mode color palettes for the CustomTkinter UI.

CustomTkinter ships light/dark color schemes, but we tweak them so the app
matches the surrounding system theme on macOS (translucent panels, dark-mode
borders). These constants are imported by the widgets and the main window.

`resolve_appearance_mode` is intentionally kept here rather than alongside
the window code: it's a pure function of (mode name, system theme) and has
no Tk dependency, so it's easy to unit-test independently.
"""

import os
import sys

# macOS trackpad fluid-scrolling tuning. macOS sends high-resolution scroll
# deltas that the default CTkScrollableFrame interprets too aggressively.
MAC_SCROLL_DELTA_SCALE = 1.35
MAC_SCROLL_MIN_FRACTION_STEP = 0.00018
MAC_SCROLL_MAX_FRACTION_STEP = 0.03

# PyMuPDF is fast and accurate but historically caused intermittent crashes
# when running inside a PyInstaller-frozen binary on macOS. The env var
# `HOLLYOCR_ENABLE_PYMUPDF=1` opts back in; default is "off in frozen mode".
ENABLE_PYMUPDF_ENV = "HOLLYOCR_ENABLE_PYMUPDF"
MUPDF_DISABLED_FOR_STABILITY = (
    sys.platform == "darwin"
    and getattr(sys, "frozen", False)
    and (os.environ.get(ENABLE_PYMUPDF_ENV, "").strip().lower() not in {"1", "true", "yes", "on"})
)


def resolve_appearance_mode(mode_name):
    """Map a user-facing appearance choice to a CustomTkinter theme name.

    Returns (theme, colors_dict). `colors_dict` holds the per-mode palette
    overrides for cards, fields, panels and text.
    """
    if mode_name == 'Escuro':
        theme = 'dark'
    elif mode_name == 'Claro':
        theme = 'light'
    else:  # 'Sistema' / unknown
        theme = 'system'

    if theme == 'light':
        colors = dict(
            APP_BG="#E9ECF1",
            CARD_BG="#FFFFFF",
            CARD_BORDER="#CCD3DE",
            FIELD_BG="#F6F8FB",
            TEXT_COLOR="#18202A",
            MUTED_COLOR="#55606E",
            SUCCESS_FG="#E9F8EE",
            WARNING_FG="#FBEAEA",
            SOFT_PANEL="#F4F7FB",
        )
    else:
        # CustomTkinter expects tuples for dark mode (light_value, dark_value)
        # but for our hardcoded custom palette we use plain dark values.
        colors = dict(
            APP_BG="#0B0C0E",
            CARD_BG="#17181C",
            CARD_BORDER="#2A2C31",
            FIELD_BG="#23252B",
            TEXT_COLOR="#F4F5F7",
            MUTED_COLOR="#A7ADB8",
            SUCCESS_FG="#10301F",
            WARNING_FG="#3A1F20",
            SOFT_PANEL="#121419",
        )
    # SUCCESS_TEXT / WARNING_TEXT: text colors used on top of SUCCESS_FG / WARNING_FG.
    colors["SUCCESS_TEXT"] = "#1D7A47" if theme == 'light' else "#8EE8B7"
    colors["WARNING_TEXT"] = "#A33B3F" if theme == 'light' else "#FF9FA2"

    # Action colors are shared across modes (macOS-flavored blue / red).
    colors["PRIMARY"] = "#0A84FF"
    colors["PRIMARY_HOVER"] = "#0072E5"
    colors["SECONDARY_HOVER"] = "#7A7A80"
    colors["DANGER_HOVER"] = "#E03B30"

    return theme, colors


def is_appearance_dark(theme):
    """True if the resolved theme should render dark UI."""
    return theme == 'dark'