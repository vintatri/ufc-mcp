"""
Testes de Segurança das 25 Páginas Adversariais de Indirect Prompt Injection (Experimento E3-A / T19).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ufc_mcp.fontes.sigaa.parsers.turma_virtual import parse_turma_noticias
from ufc_mcp.nucleo.envelope import AVISO_TEXTO_EXTERNO, Envelope, texto_do_envelope
from ufc_mcp.nucleo.higiene import CATEGORIAS_UNICODE_PROIBIDAS

PASTA_INJ = Path(__file__).resolve().parents[1] / "paginas" / "sinteticas" / "injecao"


class TestInjecaoPrompt25Vetores(unittest.TestCase):
    def test_25_paginas_adversariais_sanitizadas_e_confinadas(self) -> None:
        arquivos = sorted(PASTA_INJ.glob("*.html"))
        self.assertEqual(len(arquivos), 25)

        for arq in arquivos:
            html_adv = arq.read_text(encoding="utf-8")
            res = parse_turma_noticias(html_adv, id_turma="910001")
            env = Envelope.sucesso(
                fonte="sigaa:ava:noticias",
                dados=res.model_dump(),
                contem_texto_externo=True,
            )
            serializado = texto_do_envelope(env)
            self.assertTrue(serializado.startswith(AVISO_TEXTO_EXTERNO))

            corpo_json = serializado.split("\n", 1)[1]
            # Garantir que o JSON não foi quebrado por ataque de fechamento (Vetor V5)
            obj = json.loads(corpo_json)
            self.assertTrue(obj["ok"])
            texto_noticia = obj["dados"]["noticias"][0]["corpo"]["texto_externo"]
            self.assertNotIn("<script>", texto_noticia.lower())

            import unicodedata
            for ch in texto_noticia:
                if ch not in ("\n", "\t"):
                    self.assertNotIn(
                        unicodedata.category(ch),
                        CATEGORIAS_UNICODE_PROIBIDAS,
                        f"Caractere proibido sobreviveu em {arq.name}",
                    )
