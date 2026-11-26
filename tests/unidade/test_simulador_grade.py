"""Testes unitários do grafo DAG curricular, fecho transitivo, co-requisitos e CSP 3 perfis (T18)."""

from __future__ import annotations

import unittest

from ufc_mcp.fontes.sigaa.modelos import ComponenteProgresso
from ufc_mcp.fontes.sigaa.parsers.ofertas import parse_ofertas_turmas
from ufc_mcp.fontes.sigaa.parsers.progresso import parse_progresso_curso
from ufc_mcp.gravador.gravar import html_ofertas_padrao, html_progresso_padrao
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.servicos.horario import horarios_conflitam
from ufc_mcp.servicos.planejador import (
    simular_grades_otimizadas,
    validar_dag_e_fecho_transitivo,
)


class TestSimuladorGrade(unittest.TestCase):
    def test_validacao_dag_e_deteccao_ciclo(self) -> None:
        prog = parse_progresso_curso(html_progresso_padrao())
        val = validar_dag_e_fecho_transitivo(prog.componentes)
        self.assertTrue(val.eh_dag)
        # EQ0042 destrava EQ0071, EQ0081 e EQ0085
        self.assertIn("EQ0071", val.descendentes_transitivos_por_codigo["EQ0042"])
        self.assertIn("EQ0081", val.descendentes_transitivos_por_codigo["EQ0042"])

        # Injetar ciclo A -> B -> A e verificar detecção determinística
        ciclico = [
            ComponenteProgresso(
                id_componente="1",
                codigo="EQ0001",
                nome="A",
                periodo_sugerido=1,
                carga_horaria_h=64,
                pre_requisitos=["EQ0002"],
            ),
            ComponenteProgresso(
                id_componente="2",
                codigo="EQ0002",
                nome="B",
                periodo_sugerido=2,
                carga_horaria_h=64,
                pre_requisitos=["EQ0001"],
            ),
        ]
        with self.assertRaises(ErroUfc) as ctx:
            validar_dag_e_fecho_transitivo(ciclico)
        self.assertEqual(ctx.exception.codigo, CodigoErro.PARAMETRO_INVALIDO)

    def test_csp_branch_and_bound_co_requisitos_e_3_perfis(self) -> None:
        prog = parse_progresso_curso(html_progresso_padrao())
        ofertas = parse_ofertas_turmas(html_ofertas_padrao())
        res = simular_grades_otimizadas(
            prog.componentes,
            ofertas,
            max_disciplinas=4,
            estrategia="diversificada",
            turno_preferido="manha",
        )
        grades = res["grades_sugeridas"]
        self.assertTrue(len(grades) >= 2)
        for g in grades:
            turmas_g = g["turmas"]
            codigos_g = set(g["codigos_selecionados"])
            # Verificar co-requisito: se EQ0072 está na grade, EQ0071 também precisa estar!
            if "EQ0072" in codigos_g:
                self.assertIn("EQ0071", codigos_g)
            # Verificar zero choque de horário entre quaisquer duas turmas da grade
            for i in range(len(turmas_g)):
                for j in range(i + 1, len(turmas_g)):
                    from ufc_mcp.servicos.horario import Horario
                    h_i = [Horario.model_validate(h) for h in turmas_g[i]["horarios"]]
                    h_j = [Horario.model_validate(h) for h in turmas_g[j]["horarios"]]
                    self.assertEqual(horarios_conflitam(h_i, h_j), [])


class TestSimuladorValidacoes(unittest.TestCase):
    def test_estrategia_invalida_gera_parametro_invalido(self) -> None:
        prog = parse_progresso_curso(html_progresso_padrao())
        ofertas = parse_ofertas_turmas(html_ofertas_padrao())
        with self.assertRaises(ErroUfc) as ctx:
            simular_grades_otimizadas(prog.componentes, ofertas, estrategia="xpto")  # type: ignore[arg-type]
        self.assertEqual(ctx.exception.codigo, CodigoErro.PARAMETRO_INVALIDO)

    def test_co_requisito_inexistente_gera_aviso(self) -> None:
        comp = ComponenteProgresso(
            id_componente="1",
            codigo="EQ0001",
            nome="A",
            periodo_sugerido=1,
            carga_horaria_h=64,
            co_requisitos=["ZZ9999"],
            pre_requisitos=["YY0000"],
        )
        res = simular_grades_otimizadas([comp], [])
        avisos = " ".join(res["avisos"])  # type: ignore[arg-type]
        self.assertIn("ZZ9999", avisos)
        self.assertIn("YY0000", avisos)
