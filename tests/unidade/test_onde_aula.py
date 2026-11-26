"""Testes unitários do Filtro de Relevância Temporal em `aula` (T18)."""

from __future__ import annotations

import unittest
from datetime import date

from ufc_mcp.servicos.onde_aula import aviso_eh_relevante_para_data, decompor_local_ufc


class TestOndeAula(unittest.TestCase):
    def test_decomposicao_local(self) -> None:
        c, b, s = decompor_local_ufc("CT - Bloco 710 - Sala B")
        self.assertEqual(c, "CT")
        self.assertEqual(b, "Bloco 710")
        self.assertEqual(s, "Sala B")

    def test_filtro_temporal_bloqueia_aviso_antigo_inicio_semestre(self) -> None:
        dt_alvo = date(2026, 11, 13)
        # Aviso publicado em agosto dizendo que não haverá aula na primeira semana -> NÃO relevante em 13/11!
        rel, motivo = aviso_eh_relevante_para_data(
            texto_aviso="Boas-vindas: nesta semana não haverá aula prática no laboratório.",
            publicada_em_iso="2026-08-15",
            data_alvo=dt_alvo,
            eh_mais_recente_do_topo=False,
        )
        self.assertFalse(rel)
        self.assertEqual(motivo, "fora_da_janela_temporal_7d")

    def test_filtro_temporal_aceita_mencao_explicita_dd_mm(self) -> None:
        dt_alvo = date(2026, 11, 13)
        rel, motivo = aviso_eh_relevante_para_data(
            texto_aviso="A aula do dia 13/11 será no Laboratório do Bloco 709.",
            publicada_em_iso="2026-11-01",
            data_alvo=dt_alvo,
        )
        self.assertTrue(rel)
        self.assertIn("menciona_data_explicita", motivo or "")
