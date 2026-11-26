"""Testes unitários de `dia`, `semana`, `ics` e `diagnostico` (T18)."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tests.apoio.sigaa_simulado import TransporteUfcSimulado
from tests.seguranca.test_cofre import KeyringSeguroMemoria
from ufc_mcp.ferramentas import ContextoApp
from ufc_mcp.nucleo.config import Config, Limites
from ufc_mcp.nucleo.credenciais import CofreSistema, Credencial
from ufc_mcp.nucleo.http import ClienteEducado
from ufc_mcp.servicos.agenda_ics import dobrar_linha_ics, exportar_arquivo_ics
from ufc_mcp.servicos.diagnostico import executar_diagnostico_canarios
from ufc_mcp.servicos.meu_dia import construir_meu_dia


class TestCompostasEDiagnostico(unittest.TestCase):
    def test_dobrar_linha_ics_75_octetos(self) -> None:
        linha_longa = "SUMMARY:" + ("FENÔMENOS DE TRANSPORTE AVANÇADO " * 5)
        dobrada = dobrar_linha_ics(linha_longa)
        for parte in dobrada.split("\r\n"):
            self.assertLessEqual(len(parte.encode("utf-8")), 75)

    def test_meu_dia_ics_e_8_canarios(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t_sim = [100.0]

            async def dormir_sim(s: float) -> None:
                t_sim[0] += max(s, 3.0)

            cfg = Config(
                curso=657468,
                restaurante=1,
                pasta_config=Path(tmp) / "c",
                pasta_cache=Path(tmp) / "ca",
                pasta_documentos=Path(tmp) / "d",
                limites=Limites(pausa_minima_s=0.5),
            )
            kr = KeyringSeguroMemoria()
            cofre = CofreSistema(backend_keyring=kr)
            cofre.salvar_credencial(Credencial(usuario="aluno", senha="senha_correta_123"))
            http = ClienteEducado(
                cfg.limites,
                relogio=lambda: t_sim[0],
                dormir=dormir_sim,
                transporte=TransporteUfcSimulado(),
            )
            ctx = ContextoApp(config=cfg, http=http, cofre=cofre)

            async def rodar() -> None:
                dados_dia, avs, _ = await construir_meu_dia(
                    ctx.sigaa, ctx.ru, ctx.calendario, data_iso="2026-11-13"
                )
                self.assertEqual(dados_dia["dia_semana"], "SEX")
                self.assertEqual(avs, [])

                portal, _, _ = await ctx.sigaa.obter_resumo_portal()
                evs, _, _, _, _ = await ctx.calendario.consultar_eventos("2026-11-01", "2026-11-30")
                arq_ics = exportar_arquivo_ics(
                    cfg.pasta_documentos, portal.turmas, evs, data_referencia=date(2026, 11, 13)
                )
                self.assertTrue(arq_ics.exists())
                self.assertIn("BEGIN:VCALENDAR", arq_ics.read_text(encoding="utf-8"))

                rel_canarios = await executar_diagnostico_canarios(
                    ru=ctx.ru,
                    calendario=ctx.calendario,
                    noticias=ctx.noticias,
                    sigaa=ctx.sigaa,
                )
                self.assertEqual(rel_canarios["total_canarios"], 8)
                self.assertTrue(rel_canarios["todos_ok"])

            asyncio.run(rodar())


class TestPeriodoPadraoDaGrade(unittest.TestCase):
    def test_proximo_periodo_letivo(self) -> None:
        from datetime import date

        from ufc_mcp.servicos.planejador import proximo_periodo_letivo

        self.assertEqual(proximo_periodo_letivo(date(2026, 11, 13)), (2027, 1))
        self.assertEqual(proximo_periodo_letivo(date(2026, 3, 1)), (2026, 2))
        self.assertEqual(proximo_periodo_letivo(date(2026, 7, 31)), (2026, 2))
        self.assertEqual(proximo_periodo_letivo(date(2026, 8, 1)), (2027, 1))

    def test_grade_nao_tem_periodo_fixo(self) -> None:
        import inspect

        from ufc_mcp.ferramentas import ContextoApp
        from ufc_mcp.ferramentas.compostas import construir_ferramentas_compostas

        df = next(d for d in construir_ferramentas_compostas(ContextoApp()) if d.nome == "grade")
        params = inspect.signature(df.funcao).parameters
        self.assertIsNone(params["ano"].default)
        self.assertIsNone(params["periodo"].default)

    def test_texto_exibido_usa_contagem_do_registro(self) -> None:
        from ufc_mcp.cli import construir_parser_cli
        from ufc_mcp.ferramentas import FERRAMENTAS_PERFIL_ESSENCIAL

        ajuda = construir_parser_cli().format_help() + " ".join(
            a.format_help() for a in _subparsers(construir_parser_cli())
        )
        self.assertIn(f"essencial = {len(FERRAMENTAS_PERFIL_ESSENCIAL)} ferramentas", ajuda)
        self.assertNotIn("35 em completo", ajuda)


def _subparsers(parser):  # type: ignore[no-untyped-def]
    import argparse

    for acao in parser._actions:
        if isinstance(acao, argparse._SubParsersAction):
            return list(acao.choices.values())
    return []
