"""Testes exaustivos da Barreira Determinística `nucleo/risco.py` (T06)."""

from __future__ import annotations

import unittest

from ufc_mcp.nucleo import risco
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc


class TestBarreiraRisco(unittest.TestCase):
    def test_22_acoes_menu_permitidas(self) -> None:
        self.assertEqual(len(risco.ACOES_MENU_PERMITIDAS), 22)
        for acao in risco.ACOES_MENU_PERMITIDAS:
            risco.exigir_acao_menu(acao)

    def test_12_postbacks_permitidos(self) -> None:
        self.assertEqual(len(risco.POSTBACKS_PERMITIDOS), 12)
        for view, rotulo in risco.POSTBACKS_PERMITIDOS:
            risco.exigir_postback(view, rotulo)

    def test_bloqueio_total_acoes_proibidas_e_emissao_documentos(self) -> None:
        for proibida in risco.ACOES_PROIBIDAS_CONHECIDAS:
            with self.assertRaises(ErroUfc) as ctx:
                risco.exigir_acao_menu(proibida)
            self.assertEqual(ctx.exception.codigo, CodigoErro.ACAO_BLOQUEADA)

        for rotulo_malicioso in (
            "Trancar Matrícula",
            "Confirmar Solicitação",
            "Enviar Tarefa",
            "Postar Mensagem no Fórum",
            "Emitir Atestado de Matrícula",
            "Participantes",
            "Dar Aceite na Indicação",
        ):
            with self.assertRaises(ErroUfc) as ctx:
                risco.exigir_postback("/sigaa/ava/index.jsf", rotulo_malicioso)
            self.assertEqual(ctx.exception.codigo, CodigoErro.ACAO_BLOQUEADA)
