"""Headless regressions for safe closing and constrained output selectors."""

import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest import mock

from hollyocr.gui.shared import processing
from hollyocr.gui.shared.processing import (
    GuiTaskLifecycle,
    configure_processing_widgets,
    run_conversion_loop,
)


class GuiLifecycleTests(unittest.TestCase):
    def test_close_cancels_and_waits_for_worker_cleanup(self):
        scheduled = []
        closed = []
        started = Event()
        release = Event()
        cleaned_up = Event()
        lifecycle = GuiTaskLifecycle(
            lambda delay, callback: scheduled.append(callback),
            lambda: closed.append(cleaned_up.is_set()),
        )

        def convert():
            started.set()
            try:
                release.wait(5)
            finally:
                cleaned_up.set()

        lifecycle.start(convert)
        try:
            self.assertTrue(started.wait(2))
            self.assertFalse(lifecycle.worker.daemon)
            lifecycle.request_close()
            self.assertTrue(lifecycle.should_stop())
            self.assertEqual(closed, [])
            self.assertEqual(len(scheduled), 1)
            scheduled.pop(0)()
            self.assertEqual(closed, [])
            lifecycle.request_close()
            self.assertEqual(len(scheduled), 1)
            with self.assertRaises(RuntimeError):
                lifecycle.start(lambda: None)
        finally:
            release.set()
            lifecycle.worker.join(2)
        self.assertFalse(lifecycle.running)
        scheduled.pop(0)()
        self.assertEqual(closed, [True])

    def test_close_without_active_conversion_is_immediate(self):
        closed = []
        lifecycle = GuiTaskLifecycle(
            lambda delay, callback: self.fail("Idle closing should not be delayed"),
            lambda: closed.append(True),
        )
        lifecycle.request_close()
        lifecycle.request_close()
        self.assertEqual(closed, [True])

    def test_new_conversion_clears_previous_cancellation(self):
        lifecycle = GuiTaskLifecycle(lambda *_: None, lambda: None)
        lifecycle.cancel()
        observed = []
        lifecycle.start(lambda: observed.append(lifecycle.should_stop()))
        lifecycle.worker.join(2)
        self.assertEqual(observed, [False])

    def test_selectors_remain_readonly_after_each_conversion(self):
        class Widget:
            def __init__(self):
                self.state = None

            def configure(self, **kwargs):
                self.state = kwargs["state"]

        selector, entry = Widget(), Widget()
        for _ in range(2):
            configure_processing_widgets([selector, entry], True, (selector,))
            self.assertEqual((selector.state, entry.state), ("disabled", "disabled"))
            configure_processing_widgets([selector, entry], False, (selector,))
            self.assertEqual((selector.state, entry.state), ("readonly", "normal"))


class GuiOutputValidationTests(unittest.TestCase):
    def test_cancellation_during_file_marks_it_cancelled_and_preserves_progress(self):
        stopped = False
        statuses = []
        progress = []

        def cancel_during_file(*args, **kwargs):
            nonlocal stopped
            kwargs["progress_callback"](0.4)
            stopped = True
            return None, None

        files = [Path("first.pdf"), Path("second.pdf")]
        with mock.patch.object(processing, "process_file", side_effect=cancel_during_file) as convert:
            metas = run_conversion_loop(
                files, Path("output"), Path("."),
                poppler_path=None, tesseract_path=None, lang="por",
                ocr_threshold=30, ocr_dpi=300, use_ocr=False, force_ocr=False,
                page_audit_enabled=False, output_format="md",
                output_mode="individual", workers=1, should_stop=lambda: stopped,
                describe_file_progress=lambda *_: "Processando",
                make_status_callback=lambda *_: None,
                on_file_status=lambda path, status: statuses.append((path, status)),
                on_progress=progress.append, on_status=lambda *_: None,
            )
        self.assertEqual(metas, [])
        self.assertEqual(convert.call_count, 1)
        self.assertEqual(statuses[-1], (files[0], "Cancelado"))
        self.assertEqual(progress, [20])

    def test_invalid_output_choices_fail_before_reporting_conversion(self):
        with tempfile.TemporaryDirectory(prefix="gui_output_validation_") as temp:
            root = Path(temp)
            source = root / "document.md"
            source.write_text("# Documento\n\nTexto de reprodução.", encoding="utf-8")
            output = root / "output"
            output.mkdir()
            for output_format, output_mode in (
                ("md", "individua"),
                ("pdf", "individual"),
                ("md", "compiled"),
            ):
                with self.subTest(output_format=output_format, output_mode=output_mode):
                    statuses = []
                    with self.assertRaises(ValueError):
                        run_conversion_loop(
                            [source], output, root,
                            poppler_path=None, tesseract_path=None, lang="por",
                            ocr_threshold=30, ocr_dpi=300, use_ocr=False, force_ocr=False,
                            page_audit_enabled=False, output_format=output_format,
                            output_mode=output_mode, workers=1, should_stop=lambda: False,
                            describe_file_progress=lambda *_: "Processando",
                            make_status_callback=lambda *_: None,
                            on_file_status=lambda path, status: statuses.append(status),
                            on_progress=lambda *_: None, on_status=lambda *_: None,
                        )
                    self.assertEqual(statuses, [])
                    self.assertEqual(list(output.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
