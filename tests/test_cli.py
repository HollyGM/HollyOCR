"""Command-line entry point tests.

Focused on hollyocr.cli.main's own responsibilities (argument handling and the
batch loop), not on OCR correctness -- that is covered by
tests/test_pipeline_minimal.py, which exercises process_file() directly.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hollyocr.cli import main as cli_main_module


class CliExecutorReuseTests(unittest.TestCase):
    """Regression test: the CLI must share one process pool across the whole
    run instead of opening a new one per file/OCR batch (see process_file's
    docstring for why that matters on large documents)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cli_tests_")
        self.base = Path(self.tmp.name)
        self.input_dir = self.base / "input"
        self.output_dir = self.base / "output"
        self.input_dir.mkdir()
        self.files = [self.input_dir / f"doc{i}.md" for i in range(3)]
        for path in self.files:
            path.write_text("# Documento", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_single_shared_pool_for_the_whole_run(self):
        pool_instances = []
        real_pool_executor = cli_main_module.ProcessPoolExecutor

        class TrackingPool(real_pool_executor):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                pool_instances.append(self)

        fake_argv = [
            "hollyocr",
            "-i", str(self.input_dir),
            "-o", str(self.output_dir),
            "--no-ocr",
        ]
        with mock.patch.object(sys, "argv", fake_argv), \
             mock.patch.object(cli_main_module, "ProcessPoolExecutor", TrackingPool), \
             mock.patch.object(
                 cli_main_module, "process_file",
                 return_value=({"status": "ok", "input_path": "x"}, None),
             ) as mocked_process_file:
            cli_main_module.main()

        self.assertEqual(len(pool_instances), 1)
        self.assertEqual(mocked_process_file.call_count, 3)
        for _args, kwargs in mocked_process_file.call_args_list:
            self.assertIs(kwargs.get("executor"), pool_instances[0])


if __name__ == "__main__":
    unittest.main()
