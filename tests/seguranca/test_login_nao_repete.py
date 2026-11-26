"""Testa que falha de login cria `login_suspenso` e impede novas tentativas (Mitigação A9 / T07)."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from tests.apoio.sigaa_simulado import TransporteUfcSimulado
from tests.seguranca.test_cofre import KeyringSeguroMemoria
from ufc_mcp.nucleo.config import Limites
from ufc_mcp.nucleo.credenciais import CofreSistema, Credencial
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.http import ClienteEducado
from ufc_mcp.nucleo.sessao_sigaa import SessaoSigaa


class TestLoginSuspenso(unittest.TestCase):
    def test_suspensao_imediata_apos_credencial_invalida(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kr = KeyringSeguroMemoria()
            cofre = CofreSistema(backend_keyring=kr)
            cofre.salvar_credencial(Credencial(usuario="aluno", senha="SENHA_ERRADA"))

            transporte = TransporteUfcSimulado(senha_esperada="senha_correta_123")
            http = ClienteEducado(
                Limites(pausa_minima_s=0.5),
                relogio=lambda: 10.0,
                dormir=lambda _s: asyncio.sleep(0),
                transporte=transporte,
            )
            sessao = SessaoSigaa(http, cofre, Path(tmp))

            async def rodar() -> None:
                with self.assertRaises(ErroUfc) as ctx1:
                    await sessao.abrir_portal()
                self.assertEqual(ctx1.exception.codigo, CodigoErro.CREDENCIAL_INVALIDA)
                self.assertEqual(transporte.contagem_logins, 1)
                self.assertTrue(sessao.esta_suspenso())

                # Segunda tentativa deve ser bloqueada sem fazer requisição de login
                with self.assertRaises(ErroUfc) as ctx2:
                    await sessao.abrir_portal()
                self.assertEqual(ctx2.exception.codigo, CodigoErro.LOGIN_SUSPENSO)
                self.assertEqual(transporte.contagem_logins, 1)

            asyncio.run(rodar())
