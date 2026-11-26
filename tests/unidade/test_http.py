"""Testes unitários do ClienteEducado, redirecionamento HTTP->HTTPS e download binário (T03)."""

from __future__ import annotations

import asyncio
import unittest

import httpx

from tests.apoio.sigaa_simulado import TransporteUfcSimulado
from ufc_mcp.nucleo.config import Limites
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.http import ClienteEducado


class TestHttpEducado(unittest.TestCase):
    def test_redirecionamento_http_para_https_e_pausa(self) -> None:
        tempo_atual = [100.0]

        def relogio() -> float:
            return tempo_atual[0]

        async def dormir(seg: float) -> None:
            tempo_atual[0] += seg

        transporte = TransporteUfcSimulado()
        cliente = ClienteEducado(
            Limites(pausa_minima_s=1.0),
            relogio=relogio,
            dormir=dormir,
            transporte=transporte,
        )

        async def rodar() -> None:
            r1 = await cliente.get("http://si3.ufc.br/sigaa/verPortalDiscente.do")
            self.assertEqual(r1.status, 200)
            self.assertTrue(r1.url_final.startswith("https://si3.ufc.br"))

            r2 = await cliente.get("https://si3.ufc.br/sigaa/verTelaLogin.do")
            self.assertEqual(r2.status, 200)
            self.assertTrue(all(dt >= 1.0 for dt in cliente.intervalos_observados))

        asyncio.run(rodar())

    def test_post_form_binario_limite_25mb(self) -> None:
        class TransporteGigante(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                return httpx.Response(
                    200,
                    headers={"Content-Type": "application/pdf"},
                    content=b"X" * 1024,
                )

        cliente = ClienteEducado(
            Limites(pausa_minima_s=0.5),
            relogio=lambda: 10.0,
            dormir=lambda _s: asyncio.sleep(0),
            transporte=TransporteGigante(),
        )

        async def rodar() -> None:
            with self.assertRaises(ErroUfc) as ctx:
                await cliente.post_form_binario(
                    "https://si3.ufc.br/sigaa/ava/index.jsf",
                    {},
                    cookies=httpx.Cookies(),
                    max_bytes=512,
                )
            self.assertEqual(ctx.exception.codigo, CodigoErro.PARAMETRO_INVALIDO)

        asyncio.run(rodar())


class TestHttpEndurecido(unittest.TestCase):
    def _cliente(self, transporte: httpx.AsyncBaseTransport) -> ClienteEducado:
        return ClienteEducado(
            Limites(pausa_minima_s=0.5),
            relogio=lambda: 10.0,
            dormir=lambda _s: asyncio.sleep(0),
            transporte=transporte,
        )

    def test_cabecalhos_nao_imitam_navegador(self) -> None:
        vistos: list[httpx.Headers] = []

        class T(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                vistos.append(request.headers)
                return httpx.Response(200, text="ok")

        asyncio.run(self._cliente(T()).get("https://si3.ufc.br/x"))
        h = vistos[0]
        self.assertFalse([k for k in h if k.lower().startswith("sec-fetch")])
        self.assertNotIn("upgrade-insecure-requests", h)
        self.assertEqual(h["accept-encoding"], "gzip, deflate")
        self.assertEqual(h["accept"], "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
        self.assertTrue(h["user-agent"].startswith("ufc-mcp/"))

    def test_porta_diferente_de_443_recusada(self) -> None:
        class T(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                return httpx.Response(200, text="ok")

        cliente = self._cliente(T())
        for url in ("https://si3.ufc.br:8443/x", "http://si3.ufc.br:8080/x"):
            with self.assertRaises(ErroUfc) as ctx:
                asyncio.run(cliente.get(url))
            self.assertEqual(ctx.exception.codigo, CodigoErro.ACAO_BLOQUEADA)
        asyncio.run(cliente.get("https://si3.ufc.br:443/x"))

    def test_limite_verificado_durante_o_streaming(self) -> None:
        lidos = [0]

        class Fluxo(httpx.AsyncByteStream):
            async def __aiter__(self):  # type: ignore[no-untyped-def]
                for _ in range(1000):
                    lidos[0] += 1
                    yield b"x" * 1024

        class T(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                return httpx.Response(200, headers={"Content-Type": "application/pdf"}, stream=Fluxo())

        with self.assertRaises(ErroUfc):
            asyncio.run(
                self._cliente(T()).post_form_binario(
                    "https://si3.ufc.br/x", {}, cookies=httpx.Cookies(), max_bytes=10 * 1024
                )
            )
        self.assertLess(lidos[0], 20)  # abortou cedo, sem consumir os 1000 pedaços

    def test_mensagem_de_redirecionamentos_coerente_com_saltos(self) -> None:
        pedidos = [0]

        class T(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                pedidos[0] += 1
                return httpx.Response(302, headers={"Location": "https://si3.ufc.br/loop"})

        with self.assertRaises(ErroUfc) as ctx:
            asyncio.run(self._cliente(T()).get("https://si3.ufc.br/loop"))
        self.assertEqual(pedidos[0], 6)
        self.assertIn("6 saltos", ctx.exception.mensagem)
        self.assertNotIn("limite = 5", ctx.exception.mensagem)
