"""Bloqueio do SIGAA a aplicativo externo: detecta, suspende e não reenvia a senha."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

import httpx

from tests.apoio.sigaa_simulado import TransporteUfcSimulado
from tests.seguranca.test_cofre import KeyringSeguroMemoria
from ufc_mcp.nucleo.config import Limites
from ufc_mcp.nucleo.credenciais import CofreSistema, Credencial
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.http import ClienteEducado
from ufc_mcp.nucleo.paginas import TipoPagina, identificar_pagina
from ufc_mcp.nucleo.sessao_sigaa import SessaoSigaa

HTML_NEGADO = (
    '<html><body><form name="loginForm" action="/sigaa/logar.do?dispatch=logOn" method="post">'
    '<center style="color: #922; font-weight: bold;">'
    "Tentativa de acesso por aplicativo externo. Operação negada!</center>"
    '<input type="text" name="user.login" value="" />'
    '<input type="password" name="user.senha" value="" />'
    "</form></body></html>"
)
HTML_TELA_LOGIN_PURA = (
    '<html><body><form name="loginForm" action="/sigaa/logar.do?dispatch=logOn" method="post">'
    '<input type="text" name="user.login" value="" />'
    '<input type="password" name="user.senha" value="" /></form></body></html>'
)


class TransporteBloqueio(TransporteUfcSimulado):
    def __init__(self, html_pos_login: str) -> None:
        super().__init__()
        self.html_pos_login = html_pos_login

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sigaa/logar.do":
            self.contagem_logins += 1
            return httpx.Response(200, content=self.html_pos_login.encode("utf-8"))
        return await super().handle_async_request(request)


def _montar(tmp: str, html: str) -> tuple[SessaoSigaa, TransporteBloqueio]:
    cofre = CofreSistema(backend_keyring=KeyringSeguroMemoria())
    cofre.salvar_credencial(Credencial(usuario="aluno", senha="senha_qualquer"))
    transporte = TransporteBloqueio(html)
    http = ClienteEducado(
        Limites(pausa_minima_s=0.5),
        relogio=lambda: 10.0,
        dormir=lambda _s: asyncio.sleep(0),
        transporte=transporte,
    )
    return SessaoSigaa(http, cofre, Path(tmp)), transporte


class TestAcessoAutomatizadoNegado(unittest.TestCase):
    def test_deteccao_do_tipo_de_pagina(self) -> None:
        self.assertEqual(identificar_pagina(HTML_NEGADO), TipoPagina.ACESSO_APLICATIVO_NEGADO)
        variante = HTML_NEGADO.replace("Tentativa de acesso", "TENTATIVA DE ACESSO").replace(
            "Operação", "OPERACAO"
        )
        self.assertEqual(identificar_pagina(variante), TipoPagina.ACESSO_APLICATIVO_NEGADO)
        self.assertEqual(identificar_pagina(HTML_TELA_LOGIN_PURA), TipoPagina.TELA_LOGIN)

    def test_logar_levanta_suspende_e_nao_reenvia(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sessao, transporte = _montar(tmp, HTML_NEGADO)

            async def rodar() -> None:
                with self.assertRaises(ErroUfc) as c1:
                    await sessao.abrir_portal()
                self.assertEqual(c1.exception.codigo, CodigoErro.ACESSO_AUTOMATIZADO_NEGADO)
                self.assertTrue(sessao.esta_suspenso())
                self.assertEqual(transporte.contagem_logins, 1)

                with self.assertRaises(ErroUfc) as c2:
                    await sessao.abrir_portal()
                self.assertEqual(c2.exception.codigo, CodigoErro.ACESSO_AUTOMATIZADO_NEGADO)
                self.assertEqual(transporte.contagem_logins, 1)

                sessao.limpar_suspensao()
                self.assertFalse(sessao.esta_suspenso())

            asyncio.run(rodar())

    def test_tela_login_nao_reconhecida_suspende(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sessao, transporte = _montar(tmp, HTML_TELA_LOGIN_PURA)

            async def rodar() -> None:
                with self.assertRaises(ErroUfc) as c1:
                    await sessao.abrir_portal()
                self.assertEqual(c1.exception.codigo, CodigoErro.LOGIN_SUSPENSO)
                self.assertIn("tela de login", c1.exception.mensagem)
                self.assertTrue(sessao.esta_suspenso())
                with self.assertRaises(ErroUfc):
                    await sessao.abrir_portal()
                self.assertEqual(transporte.contagem_logins, 1)

            asyncio.run(rodar())

    def test_login_efemero_levanta_e_suspende(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sessao, transporte = _montar(tmp, HTML_NEGADO)

            async def rodar() -> None:
                with self.assertRaises(ErroUfc) as c1:
                    await sessao.autenticar_com_credencial_efemera("aluno", "x")
                self.assertEqual(c1.exception.codigo, CodigoErro.ACESSO_AUTOMATIZADO_NEGADO)
                self.assertTrue(sessao.esta_suspenso())
                self.assertEqual(sessao.motivo_suspensao(), "ACESSO_AUTOMATIZADO_NEGADO")
                self.assertEqual(transporte.contagem_logins, 1)

            asyncio.run(rodar())
