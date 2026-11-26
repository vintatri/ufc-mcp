"""Testes unitários das regras de aprovação por nota e Avaliação Final da UFC (Art. 114) (T14)."""

from __future__ import annotations

import unittest

from ufc_mcp.servicos.notas_ufc import (
    AVISO_BORDA,
    avaliar_resultado_apos_af,
    diagnosticar_notas_ufc,
)


class TestNotasUfc(unittest.TestCase):
    def test_aprovacao_direta_media_7(self) -> None:
        d = diagnosticar_notas_ufc([7.5, 8.0, 6.5], total_unidades_previstas=3)
        self.assertEqual(d.situacao_regimental, "APROVADO_POR_MEDIA")
        self.assertIsNone(d.nota_minima_avaliacao_final)

    def test_avaliacao_final_calculo_exato(self) -> None:
        # MP = 5.5 -> AF_min = max(4.0, 10.0 - 5.5) = 4.5
        d = diagnosticar_notas_ufc([5.0, 6.0, 5.5], total_unidades_previstas=3)
        self.assertEqual(d.situacao_regimental, "AGUARDANDO_AVALIACAO_FINAL")
        self.assertEqual(d.nota_minima_avaliacao_final, 4.5)

        # MP = 6.5 -> 10 - 6.5 = 3.5, mas Art. 114, §2º exige AF >= 4.0!
        d2 = diagnosticar_notas_ufc([6.5, 6.5, 6.5], total_unidades_previstas=3)
        self.assertEqual(d2.nota_minima_avaliacao_final, 4.0)

    def test_reprovacao_direta_abaixo_de_4(self) -> None:
        d = diagnosticar_notas_ufc([3.0, 3.5, 4.0], total_unidades_previstas=3)
        self.assertEqual(d.situacao_regimental, "REPROVADO_POR_NOTA")

    def test_meta_unidades_restantes(self) -> None:
        # 2 notas lançadas: 6.0 e 6.0 (soma = 12.0). Para média 7.0 em 3 unidades (soma 21.0), precisa de 9.0
        d = diagnosticar_notas_ufc([6.0, 6.0], total_unidades_previstas=3)
        self.assertEqual(d.situacao_regimental, "EM_CURSO_APROVAVEL_POR_MEDIA")
        self.assertEqual(d.nota_necessaria_por_unidade_para_media_7, 9.0)

    def test_limiares_media_parcial(self) -> None:
        d = diagnosticar_notas_ufc([3.9, 3.9], total_unidades_previstas=2)
        self.assertEqual(d.media_parcial_atual, 3.9)
        self.assertEqual(d.situacao_regimental, "REPROVADO_POR_NOTA")
        self.assertIsNone(d.nota_minima_avaliacao_final)

        d = diagnosticar_notas_ufc([4.0, 4.0], total_unidades_previstas=2)
        self.assertEqual(d.situacao_regimental, "AGUARDANDO_AVALIACAO_FINAL")
        self.assertEqual(d.nota_minima_avaliacao_final, 6.0)  # max(4, 10 - 4)

        d = diagnosticar_notas_ufc([6.9, 6.9], total_unidades_previstas=2)
        self.assertEqual(d.situacao_regimental, "AGUARDANDO_AVALIACAO_FINAL")
        self.assertEqual(d.nota_minima_avaliacao_final, 4.0)  # max(4, 3.1)

        d = diagnosticar_notas_ufc([7.0, 7.0], total_unidades_previstas=2)
        self.assertEqual(d.situacao_regimental, "APROVADO_POR_MEDIA")

    def test_af_min_e_media_aritmetica(self) -> None:
        # MP = 5.0 -> AF_min = 5.0; MP = 6.0 -> 4.0 (piso); MP = 5.5 -> 4.5
        for mp, esperado in ((5.0, 5.0), (6.0, 4.0), (5.5, 4.5), (4.5, 5.5)):
            d = diagnosticar_notas_ufc([mp, mp], total_unidades_previstas=2)
            self.assertEqual(d.nota_minima_avaliacao_final, esperado)
        # média aritmética simples: (10 + 2 + 6)/3 = 6.0
        d = diagnosticar_notas_ufc([10.0, 2.0, 6.0], total_unidades_previstas=3)
        self.assertEqual(d.media_parcial_atual, 6.0)


class TestBordasSemArredondar(unittest.TestCase):
    def test_mp_6_95_nao_aprova_direto_e_avisa(self) -> None:
        d = diagnosticar_notas_ufc([6.9, 7.0], total_unidades_previstas=2)  # MP 6,95
        self.assertEqual(d.media_parcial_atual, 7.0)  # exibição arredondada
        self.assertEqual(d.situacao_regimental, "AGUARDANDO_AVALIACAO_FINAL")
        self.assertIn(AVISO_BORDA, d.avisos)
        self.assertEqual(d.nota_minima_avaliacao_final, 4.0)

    def test_mp_3_95_reprova_e_avisa(self) -> None:
        d = diagnosticar_notas_ufc([3.9, 4.0], total_unidades_previstas=2)
        self.assertEqual(d.situacao_regimental, "REPROVADO_POR_NOTA")
        self.assertIn(AVISO_BORDA, d.avisos)

    def test_exatos_nao_avisam_e_classificam(self) -> None:
        d7 = diagnosticar_notas_ufc([7.0, 7.0], total_unidades_previstas=2)
        self.assertEqual(d7.situacao_regimental, "APROVADO_POR_MEDIA")
        self.assertNotIn(AVISO_BORDA, d7.avisos)
        d4 = diagnosticar_notas_ufc([4.0, 4.0], total_unidades_previstas=2)
        self.assertEqual(d4.situacao_regimental, "AGUARDANDO_AVALIACAO_FINAL")
        self.assertNotIn(AVISO_BORDA, d4.avisos)

    def test_total_presumido_avisa(self) -> None:
        d = diagnosticar_notas_ufc([8.0, 8.0, 8.0])
        self.assertTrue(d.total_unidades_presumido)
        self.assertTrue(any("presumido" in a for a in d.avisos))
        d2 = diagnosticar_notas_ufc([8.0, 8.0, 8.0], total_unidades_previstas=3)
        self.assertFalse(d2.total_unidades_presumido)

    def test_resultado_apos_af(self) -> None:
        self.assertEqual(avaliar_resultado_apos_af(6.0, 4.0), "APROVADO_APOS_AF")  # (6+4)/2 = 5
        self.assertEqual(avaliar_resultado_apos_af(5.0, 5.0), "APROVADO_APOS_AF")
        self.assertEqual(avaliar_resultado_apos_af(4.0, 6.0), "APROVADO_APOS_AF")
        self.assertEqual(avaliar_resultado_apos_af(4.0, 5.9), "REPROVADO_APOS_AF")  # média 4,95
        self.assertEqual(avaliar_resultado_apos_af(6.9, 3.9), "REPROVADO_APOS_AF")  # AF < 4,0
        self.assertEqual(avaliar_resultado_apos_af(5.0, 4.9), "REPROVADO_APOS_AF")
