"""Testes unitários das 9 regras determinísticas do Anonimizador (`gravador/anonimizar.py` — T09)."""

from __future__ import annotations

import unittest

from ufc_mcp.gravador.anonimizar import anonimizar_html, verificar_vazamento


class TestAnonimizador(unittest.TestCase):
    def test_9_regras_anonimizacao_e_verificacao_vazamento(self) -> None:
        bruto = (
            "<html><body>"
            "<p>Discente: Fulano Beltrano Quaresma | Matrícula: 000123 | CPF: 123.456.789-00</p>"
            "<p>E-mail: aluno.exemplo@alu.ufc.br | Cookie: JSESSIONID=SEGREDO999</p>"
            "<p>Docente: Prof. Carlos Alberto Silva</p>"
            '<input name="javax.faces.ViewState" value="j_id_98765" />'
            '<input name="id" value="000123" />'
            "<table><tr><td>8,5</td></tr></table>"
            "</body></html>"
        )
        anon = anonimizar_html(
            bruto,
            nome_estudante="Fulano Beltrano Quaresma",
            matricula="000123",
            segredos_extras=["SEGREDO999"],
        )
        vazados = verificar_vazamento(
            anon,
            ["Fulano", "Beltrano", "Quaresma", "000123", "123.456.789-00", "aluno.exemplo@alu.ufc.br", "SEGREDO999", "Carlos Alberto"],
        )
        self.assertEqual(vazados, [])
        self.assertIn("000.000.000-00", anon)
        self.assertIn("discente@exemplo.ufc.br", anon)
        self.assertIn("j_id_anonimo", anon)
        self.assertIn("Prof. DOCENTE EXEMPLO", anon)
