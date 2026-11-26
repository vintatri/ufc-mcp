"""Verifica que conexões reais de socket são bloqueadas nos testes (T00)."""

from __future__ import annotations

import socket
import unittest

from tests.conftest import bloquear_socket_connect


class TestTravaRede(unittest.TestCase):
    def test_bloqueio_conexao_externa(self) -> None:
        orig = socket.socket.connect
        socket.socket.connect = bloquear_socket_connect  # type: ignore[method-assign]
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                with self.assertRaises(RuntimeError) as ctx:
                    s.connect(("8.8.8.8", 53))
                self.assertIn("Conexao de rede real proibida", str(ctx.exception))
            finally:
                s.close()
        finally:
            socket.socket.connect = orig  # type: ignore[method-assign]
