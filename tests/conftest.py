"""Configuração comum dos testes."""

import tempfile
from pathlib import Path

import pytest

from hollyocr.core import checkpoint


@pytest.fixture(autouse=True)
def checkpoints_isolados(monkeypatch):
    """O progresso salvo dos testes vai para uma pasta temporária, nunca para o
    Application Support do usuário."""
    with tempfile.TemporaryDirectory(prefix="hollyocr_checkpoints_") as pasta:
        raiz = Path(pasta) / "checkpoints"
        monkeypatch.setattr(checkpoint, "checkpoints_root", lambda: raiz)
        yield raiz
