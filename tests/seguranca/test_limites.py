"""Testes de segurança dos limites de taxa de requisição por minuto/hora/dia (T03)."""

from __future__ import annotations

import asyncio
import unittest

from tests.apoio.sigaa_simulado import TransporteUfcSimulado
from ufc_mcp.nucleo.config import Limites
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.http import ClienteEducado


class TestLimitesTaxa(unittest.TestCase):
    def test_espera_a_janela_do_minuto_em_vez_de_falhar(self) -> None:
        t = [1000.0]

        async def dormir(s: float) -> None:
            t[0] += s

        cliente = ClienteEducado(
            Limites(pausa_minima_s=0.5, max_por_minuto=2, max_por_hora=50, max_por_dia=100),
            relogio=lambda: t[0],
            dormir=dormir,
            transporte=TransporteUfcSimulado(),
        )

        async def rodar() -> None:
            inicio = t[0]
            await cliente.get("https://ufcinforma.ufc.br/feed")
            await cliente.get("https://ufcinforma.ufc.br/feed")
            # a terceira requisição cai no mesmo minuto: espera a primeira sair da janela de 60 s
            await cliente.get("https://ufcinforma.ufc.br/feed")
            self.assertGreaterEqual(t[0] - inicio, 60.0)
            self.assertLessEqual(t[0] - inicio, 61.0)
            # nunca passa de max_por_minuto requisições em qualquer janela de 60 s
            for _ in range(7):
                await cliente.get("https://ufcinforma.ufc.br/feed")
            self.assertLessEqual(cliente.contadores_atuais()["usadas_no_minuto"], 2)

        asyncio.run(rodar())

    def test_bloqueio_ao_atingir_max_por_hora(self) -> None:
        t = [1000.0]

        async def dormir(s: float) -> None:
            t[0] += s

        cliente = ClienteEducado(
            Limites(pausa_minima_s=0.5, max_por_minuto=30, max_por_hora=10, max_por_dia=100),
            relogio=lambda: t[0],
            dormir=dormir,
            transporte=TransporteUfcSimulado(),
        )

        async def rodar() -> None:
            for _ in range(10):
                await cliente.get("https://ufcinforma.ufc.br/feed")
            with self.assertRaises(ErroUfc) as ctx:
                await cliente.get("https://ufcinforma.ufc.br/feed")
            self.assertEqual(ctx.exception.codigo, CodigoErro.LIMITE_DE_REQUISICOES)

        asyncio.run(rodar())
