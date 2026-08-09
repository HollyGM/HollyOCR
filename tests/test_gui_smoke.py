"""Headless smoke checks for both GUI front-ends.

These deliberately avoid creating a Tk root, which would make CI depend on
an active display server. The conversion orchestration itself is exercised
by GuiSharedProcessingTests in test_pipeline_minimal.py.
"""

import unittest

from hollyocr.gui.classic_tk.window import choose_input_output_gui_plain_tk
from hollyocr.gui.modern_ctk.theme import resolve_appearance_mode
from hollyocr.gui.modern_ctk.widgets import validate_path
from hollyocr.gui.modern_ctk.window import choose_input_output_gui


class GuiImportSmokeTests(unittest.TestCase):
    def test_both_gui_entrypoints_are_importable(self):
        self.assertTrue(callable(choose_input_output_gui))
        self.assertTrue(callable(choose_input_output_gui_plain_tk))

    def test_theme_resolution_has_required_palette(self):
        theme, palette = resolve_appearance_mode("Claro")
        self.assertEqual(theme, "light")
        self.assertTrue({"APP_BG", "CARD_BG", "TEXT_COLOR", "PRIMARY"} <= set(palette))

    def test_validate_path_rejects_missing_path(self):
        self.assertIsNone(validate_path("/path/that/does/not/exist"))


if __name__ == "__main__":
    unittest.main()
