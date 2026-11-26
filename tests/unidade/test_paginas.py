"""Testes unitários de identificação das 7 páginas sintéticas e extração jsfcljs (T06)."""

from __future__ import annotations

import unittest
from pathlib import Path

from ufc_mcp.nucleo.paginas import (
    TipoPagina,
    extrair_formulario,
    extrair_pares_jsfcljs,
    identificar_pagina,
    validar_campos_visiveis_login,
)

RAIZ_SINT = Path(__file__).resolve().parents[1] / "paginas" / "sinteticas"


class TestPaginasJsf(unittest.TestCase):
    def test_identificacao_7_paginas_sinteticas(self) -> None:
        esperados = [
            ("01_tela_login.html", TipoPagina.TELA_LOGIN),
            ("02_login_invalido.html", TipoPagina.LOGIN_INVALIDO),
            ("03_sessao_expirada.html", TipoPagina.SESSAO_EXPIRADA),
            ("04_selecao_vinculo.html", TipoPagina.SELECAO_VINCULO),
            ("05_questionario_intersticial.html", TipoPagina.QUESTIONARIO_INTERSTICIAL),
            ("06_portal_discente.html", TipoPagina.PORTAL_DISCENTE),
            ("07_turma_virtual.html", TipoPagina.TURMA_VIRTUAL),
        ]
        for arq, tipo_esp in esperados:
            html = (RAIZ_SINT / arq).read_text(encoding="utf-8")
            self.assertEqual(identificar_pagina(html), tipo_esp, f"Falha em {arq}")

    def test_extracao_jsfcljs_e_formulario(self) -> None:
        html_login = (RAIZ_SINT / "01_tela_login.html").read_text(encoding="utf-8")
        validar_campos_visiveis_login(html_login)
        form = extrair_formulario(html_login, "loginForm")
        self.assertEqual(form.view, "/sigaa/logar.do")
        self.assertIn("width", form.campos)

        onclick = "jsfcljs(document.forms['formMenu'],'formMenu:j_id1,formMenu:j_id1,idTurma,910001','');return false;"
        nome_f, pares = extrair_pares_jsfcljs(onclick)
        self.assertEqual(nome_f, "formMenu")
        self.assertEqual(pares["idTurma"], "910001")
