"""Configuração global de testes e bloqueio estrito de conexões reais de rede (T00)."""

from __future__ import annotations

import socket
from typing import Any

try:
    import pytest
except ImportError:
    pytest = None  # type: ignore[assignment]


def bloquear_socket_connect(*_args: Any, **_kwargs: Any) -> Any:
    raise RuntimeError("Conexao de rede real proibida nos testes automatizados.")


if pytest is not None:
    @pytest.fixture(autouse=True)
    def _trava_rede_global(monkeypatch: Any) -> None:
        monkeypatch.setattr(socket.socket, "connect", bloquear_socket_connect)
