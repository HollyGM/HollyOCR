"""Rotating file logger and safe stdout/stderr handling for windowed builds."""

import logging
from logging.handlers import RotatingFileHandler

from .paths import APP_NAME, get_log_path


def setup_logging():
    """Configure a small rotating log file for GUI and CLI diagnostics."""
    logger = logging.getLogger(APP_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        handler = RotatingFileHandler(
            get_log_path(),
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    except Exception:
        logger.addHandler(logging.NullHandler())
    return logger


LOGGER = setup_logging()


class NullWriter:
    """Dummy writer for when sys.stdout/stderr is None (no console)."""
    def write(self, text): return len(str(text))
    def flush(self): pass
    def isatty(self): return False


def is_stream_usable(stream):
    """Return False for invalid stdout/stderr handles in windowed executables."""
    if stream is None:
        return False
    try:
        stream.write("")
        stream.flush()
        return True
    except Exception:
        return False


def is_interactive_terminal_stream(stream):
    """Return True only for a usable interactive console stream."""
    try:
        return is_stream_usable(stream) and bool(stream.isatty())
    except Exception:
        return False
