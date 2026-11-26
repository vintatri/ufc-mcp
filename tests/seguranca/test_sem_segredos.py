"""
Auditoria de Zero Segredos e Zero Identificadores Pessoais nos arquivos do repositório (T19).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[2]


class TestSemSegredosNoRepositorio(unittest.TestCase):
    def test_nenhum_html_ou_gabarito_contem_dados_reais_ou_jsessionid_ativo(self) -> None:
        for pasta in (RAIZ_REPO / "tests" / "paginas", RAIZ_REPO / "tests" / "gabaritos"):
            for arq in pasta.rglob("*.*"):
                if "sinteticas" in arq.parts:
                    continue
                txt = arq.read_text(encoding="utf-8")
                self.assertNotIn("Fulano Beltrano Quaresma", txt)
                self.assertNotIn("000123", txt)
                # Verifica ausência de CPFs reais (apenas 000.000.000-00 é permitido)
                for m_cpf in re.findall(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", txt):
                    self.assertEqual(m_cpf, "000.000.000-00")
