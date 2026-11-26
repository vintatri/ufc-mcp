"""Testes unitários da matriz conjunta (enviada x delta_h) e Art. 113 em `alertas` (T18)."""

from __future__ import annotations

import unittest
from datetime import datetime

from ufc_mcp.nucleo.higiene import externo
from ufc_mcp.servicos.alertas import classificar_alerta_nota, classificar_tarefa_prazo_envio
from ufc_mcp.servicos.faltas import calcular_faltas_disciplina
from ufc_mcp.servicos.notas_ufc import diagnosticar_notas_ufc


class TestRadarAlertas(unittest.TestCase):
    def test_matriz_prazo_x_envio(self) -> None:
        agora = datetime(2026, 11, 13, 12, 0, 0)
        tit = externo("Lista 03", origem="teste")

        # 1. Tarefa já enviada -> CONCLUIDA (VERDE), mesmo que vença em 5 horas
        a_env = classificar_tarefa_prazo_envio(
            id_turma="910001",
            turma="EQ0042",
            titulo=tit,
            fim_entrega_iso="2026-11-13T17:00:00",
            enviada=True,
            agora=agora,
        )
        assert a_env is not None
        self.assertEqual(a_env.severidade, "CONCLUIDA")
        self.assertEqual(a_env.semaforo, "VERDE")

        # 2. Tarefa não enviada vencendo em 24h -> CRITICO (VERMELHO)
        a_crit = classificar_tarefa_prazo_envio(
            id_turma="910001",
            turma="EQ0042",
            titulo=tit,
            fim_entrega_iso="2026-11-14T12:00:00",
            enviada=False,
            agora=agora,
        )
        assert a_crit is not None
        self.assertEqual(a_crit.severidade, "CRITICO")

        # 3. Tarefa não enviada vencendo em 10 dias -> INFORMATIVO (VERDE), não CRITICO!
        a_inf = classificar_tarefa_prazo_envio(
            id_turma="910001",
            turma="EQ0042",
            titulo=tit,
            fim_entrega_iso="2026-11-23T12:00:00",
            enviada=False,
            agora=agora,
            dias_antecedencia=15,
        )
        assert a_inf is not None
        self.assertEqual(a_inf.severidade, "INFORMATIVO")

        # 4. Tarefa com enviada=None vencendo em 20h -> ATENCAO com verificacao_envio="indisponivel_confirmar_no_ava"
        a_none = classificar_tarefa_prazo_envio(
            id_turma="910001",
            turma="EQ0042",
            titulo=tit,
            fim_entrega_iso="2026-11-14T08:00:00",
            enviada=None,
            agora=agora,
        )
        assert a_none is not None
        self.assertEqual(a_none.severidade, "ATENCAO")
        self.assertEqual(a_none.verificacao_envio, "indisponivel_confirmar_no_ava")

    def test_faltas_art_113(self) -> None:
        # 64h -> limite 16h (8 encontros de 2h). Com 12h de falta (75% do limite), restam 2 encontros -> CRITICO
        d = calcular_faltas_disciplina(
            id_turma="910001",
            codigo="EQ0042",
            nome="Fenômenos",
            carga_horaria_h=64,
            faltas_registradas_h=12,
        )
        self.assertEqual(d.limite_faltas_h, 16)
        self.assertEqual(d.encontros_2h_restantes, 2)
        self.assertEqual(d.severidade, "CRITICO")

    def _tarefa(self, iso: str, enviada: bool | None, **kw):  # type: ignore[no-untyped-def]
        return classificar_tarefa_prazo_envio(
            id_turma="1",
            turma="T",
            titulo=externo("x", origem="teste"),
            fim_entrega_iso=iso,
            enviada=enviada,
            agora=datetime(2026, 11, 13, 12, 0, 0),
            **kw,
        )

    def test_faixas_tarefa_nao_enviada(self) -> None:
        self.assertEqual(self._tarefa("2026-11-15T12:00:00", False).severidade, "CRITICO")  # 48h
        self.assertEqual(self._tarefa("2026-11-12T12:00:00", False).severidade, "CRITICO")  # -24h
        self.assertEqual(self._tarefa("2026-11-15T13:00:00", False).severidade, "ATENCAO")  # 49h
        self.assertEqual(self._tarefa("2026-11-20T12:00:00", False).severidade, "ATENCAO")  # 168h
        self.assertEqual(self._tarefa("2026-11-20T13:00:00", False).severidade, "INFORMATIVO")
        # 10 dias com o padrão (7) ainda é INFORMATIVO (horizonte mínimo de 14 dias)
        self.assertEqual(self._tarefa("2026-11-23T12:00:00", False).severidade, "INFORMATIVO")
        self.assertIsNone(self._tarefa("2026-12-01T12:00:00", False))  # 18 dias > 14

    def test_tarefa_vencida_sem_envio_e_critica(self) -> None:
        t = self._tarefa("2026-11-10T12:00:00", False)
        assert t is not None
        self.assertEqual(t.severidade, "CRITICO")
        self.assertEqual(t.motivo, "prazo vencido sem envio registrado")
        self.assertIsNone(self._tarefa("2026-11-10T12:00:00", None))

    def test_faixas_nota(self) -> None:
        crit = classificar_alerta_nota(diagnosticar_notas_ufc([2.0, 3.0, 3.0]))
        self.assertEqual(crit[0], "CRITICO")  # REPROVADO_POR_NOTA
        # AF_min = 10 - 5.0 = 5.0 <= 8.5 -> ATENCAO
        self.assertEqual(classificar_alerta_nota(diagnosticar_notas_ufc([5.0, 5.0, 5.0]))[0], "ATENCAO")
        # AF_min > 8.5 exige MP < 1.5, impossível com MP >= 4: não ocorre; AF_min máx. = 6.0
        # Avaliações pendentes: média necessária > 8.5 -> CRITICO
        self.assertEqual(classificar_alerta_nota(diagnosticar_notas_ufc([5.0, 5.0]))[0], "CRITICO")  # precisa 11
        # MP parcial 6.0 com pendente: precisa 9.0 -> CRITICO
        self.assertEqual(classificar_alerta_nota(diagnosticar_notas_ufc([6.0, 6.0]))[0], "CRITICO")
        # MP parcial 6.5 com pendente: precisa 8.0 -> ATENCAO
        self.assertEqual(classificar_alerta_nota(diagnosticar_notas_ufc([6.5, 6.5]))[0], "ATENCAO")
        # Aprovado e sem notas: sem alerta
        self.assertEqual(classificar_alerta_nota(diagnosticar_notas_ufc([8.0, 8.0, 8.0]))[0], "OK")
        self.assertEqual(classificar_alerta_nota(diagnosticar_notas_ufc([]))[0], "OK")
