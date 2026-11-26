"""Testes de segurança da allowlist de domínios HOSTS_PERMITIDOS (T03)."""

from __future__ import annotations

import unittest

from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.http import validar_e_normalizar_url


class TestHostsPermitidos(unittest.TestCase):
    def test_hosts_oficiais_permitidos(self) -> None:
        url, host = validar_e_normalizar_url("http://si3.ufc.br/sigaa/verTelaLogin.do")
        self.assertEqual(host, "si3.ufc.br")
        self.assertTrue(url.startswith("https://"))

    def test_bloqueio_dominios_externos(self) -> None:
        for url_maliciosa in (
            "https://evil.com/exfiltrate",
            "https://si3.ufc.br.attacker.com/sigaa",
            "ftp://si3.ufc.br/arquivo",
            "file:///etc/passwd",
        ):
            with self.assertRaises(ErroUfc) as ctx:
                validar_e_normalizar_url(url_maliciosa)
            self.assertEqual(ctx.exception.codigo, CodigoErro.ACAO_BLOQUEADA)
