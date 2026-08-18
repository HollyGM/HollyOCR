"""Headless smoke checks for both GUI front-ends.

These deliberately avoid creating a Tk root, which would make CI depend on
an active display server. The conversion orchestration itself is exercised
by GuiSharedProcessingTests in test_pipeline_minimal.py.
"""

import unittest

from hollyocr.gui.classic_tk.window import choose_input_output_gui_plain_tk
from hollyocr.gui.modern_ctk.window import choose_input_output_gui


class GuiImportSmokeTests(unittest.TestCase):
    def test_both_gui_entrypoints_are_importable(self):
        self.assertTrue(callable(choose_input_output_gui))
        self.assertTrue(callable(choose_input_output_gui_plain_tk))


if __name__ == "__main__":
    unittest.main()
