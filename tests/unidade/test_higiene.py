"""Testes unitários de sanitização Unicode e HTML contra Indirect Prompt Injection (T02)."""

from __future__ import annotations

import unittest

from ufc_mcp.nucleo.higiene import externo, limpar_texto, sem_acentos_minusculo


class TestHigiene(unittest.TestCase):
    def test_remocao_script_e_style(self) -> None:
        bruto = "<div>Olá<script>alert('xss')</script><style>body{display:none}</style> Mundo</div>"
        limpo, cortado = limpar_texto(bruto)
        self.assertEqual(limpo, "Olá Mundo")
        self.assertFalse(cortado)

    def test_remocao_zero_width_e_bidi(self) -> None:
        bruto = "Texto​com‌zero‍width﻿ e bidi ‮override‬"
        limpo, _ = limpar_texto(bruto)
        self.assertNotIn("​", limpo)
        self.assertNotIn("‮", limpo)
        self.assertNotIn("﻿", limpo)
        self.assertEqual(limpo, "Textocomzerowidth e bidi override")

    def test_remocao_unicode_tags_e0000(self) -> None:
        bruto = "Normal󠁁󠁂󠁿Final"
        limpo, _ = limpar_texto(bruto)
        self.assertEqual(limpo, "NormalFinal")

    def test_truncamento_max_chars(self) -> None:
        bruto = "A" * 500
        limpo, cortado = limpar_texto(bruto, max_chars=100)
        self.assertTrue(cortado)
        self.assertTrue(limpo.endswith(" […cortado]"))
        self.assertEqual(len(limpo), 100 + len(" […cortado]"))

    def test_envelope_texto_externo(self) -> None:
        obj = externo("<b>Aviso</b>​ do professor", origem="turma:noticia")
        self.assertEqual(obj.texto_externo, "Aviso do professor")
        self.assertEqual(obj.origem, "turma:noticia")
        self.assertFalse(obj.cortado)

    def test_sem_acentos_minusculo(self) -> None:
        self.assertEqual(
            sem_acentos_minusculo("Fenômenos de Transporte — Avaliação Ç"),
            "fenomenos de transporte — avaliacao c",
        )
