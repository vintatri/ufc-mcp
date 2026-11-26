"""Testes unitários do decodificador de horários do SIGAA e cálculo de conflitos/janelas (T13)."""

from __future__ import annotations

import unittest

from ufc_mcp.servicos.horario import (
    calcular_horas_janela,
    decodificar_horario_sigaa,
    horarios_conflitam,
)


class TestHorarioSigaa(unittest.TestCase):
    def test_decodificar_compacto_simples_e_multiplo(self) -> None:
        h = decodificar_horario_sigaa("24M12 6T34")
        self.assertEqual(len(h), 3)
        self.assertEqual(h[0].dia, "SEG")
        self.assertEqual(h[0].inicio, "07:00")
        self.assertEqual(h[0].fim, "09:00")
        self.assertEqual(h[1].dia, "QUA")
        self.assertEqual(h[2].dia, "SEX")
        self.assertEqual(h[2].inicio, "15:00")
        self.assertEqual(h[2].fim, "17:00")

    def test_decodificar_slots_nao_contiguos(self) -> None:
        h = decodificar_horario_sigaa("2M124")
        self.assertEqual(len(h), 2)
        self.assertEqual((h[0].inicio, h[0].fim), ("07:00", "09:00"))
        self.assertEqual((h[1].inicio, h[1].fim), ("10:00", "11:00"))
        self.assertEqual(calcular_horas_janela(h), 1.0)

    def test_conflito_entre_horarios(self) -> None:
        h1 = decodificar_horario_sigaa("24M12")
        h2 = decodificar_horario_sigaa("4M23")
        conflitos = horarios_conflitam(h1, h2)
        self.assertEqual(conflitos, ["QUA 08:00-09:00"])
