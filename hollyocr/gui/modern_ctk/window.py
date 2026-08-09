"""Primary GUI entry point.

The product now has one focused interface for faithful OCR extraction.  The
former AI/model/API panel was removed, along with its background services and
credentials.  Reusing the robust Tk window also keeps the packaged macOS app
stable across system Tk versions.
"""

from hollyocr.gui.classic_tk.window import choose_input_output_gui_plain_tk


def choose_input_output_gui(default_poppler=None, default_tesseract=None):
    return choose_input_output_gui_plain_tk(default_poppler, default_tesseract)
