"""Testes unitários de `estudo` (`servicos/tutoria.py` — T18)."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tests.apoio.sigaa_simulado import TransporteUfcSimulado
from tests.seguranca.test_cofre import KeyringSeguroMemoria
from ufc_mcp.fontes.sigaa.cliente import ClienteSigaa
from ufc_mcp.fontes.sigaa.modelos import (
    AvaliacaoNota,
    AvaliacoesTurma,
    ItemAvaliacaoAgendada,
    ItemCronogramaPlano,
    MaterialAula,
    NotasTurma,
    PlanoCursoTurma,
    TarefasTurma,
    TopicoAulaTurma,
    VisaoGeralTurma,
)
from ufc_mcp.nucleo.cache import CachePessoal
from ufc_mcp.nucleo.config import Config, Limites
from ufc_mcp.nucleo.credenciais import CofreSistema, Credencial
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.higiene import externo
from ufc_mcp.nucleo.http import ClienteEducado
from ufc_mcp.nucleo.sessao_sigaa import SessaoSigaa
from ufc_mcp.servicos.tutoria import construir_plano_estudo_orientado


class _SigaaFalsoTutoria:
    """Stub assíncrono de ClienteSigaa para testar casos de borda de tutoria."""

    def __init__(
        self,
        *,
        notas_por_turma: dict[str, NotasTurma | ErroUfc],
        avaliacoes_por_turma: dict[str, AvaliacoesTurma],
        plano_por_turma: dict[str, PlanoCursoTurma],
        visao_por_turma: dict[str, VisaoGeralTurma],
    ) -> None:
        self._notas = notas_por_turma
        self._avaliacoes = avaliacoes_por_turma
        self._plano = plano_por_turma
        self._visao = visao_por_turma

    async def obter_turma_notas(self, id_turma: str, *, atualizar: bool = False) -> tuple[NotasTurma, bool, int]:
        res = self._notas[id_turma]
        if isinstance(res, ErroUfc):
            raise res
        return res, False, 0

    async def obter_turma_avaliacoes(self, id_turma: str, *, atualizar: bool = False) -> tuple[AvaliacoesTurma, bool, int]:
        return self._avaliacoes[id_turma], False, 0

    async def obter_turma_tarefas(self, id_turma: str, *, atualizar: bool = False) -> tuple[TarefasTurma, bool, int]:
        return TarefasTurma(id_turma=id_turma, turma=f"TURMA {id_turma}", tarefas=[]), False, 0

    async def obter_turma_plano_curso(self, id_turma: str, *, atualizar: bool = False) -> tuple[PlanoCursoTurma, bool, int]:
        return self._plano[id_turma], False, 0

    async def obter_turma_visao_geral(self, id_turma: str, *, atualizar: bool = False) -> tuple[VisaoGeralTurma, bool, int]:
        return self._visao[id_turma], False, 0


def _stub_duas_turmas(
    *,
    avaliacoes_t1: list[ItemAvaliacaoAgendada] | None = None,
    erro_notas_t1: ErroUfc | None = None,
) -> Any:
    notas_t1: NotasTurma | ErroUfc = erro_notas_t1 or NotasTurma(
        id_turma="101",
        turma="EQ0001 - FENOMENOS",
        avaliacoes=[AvaliacaoNota(nome="AP1", nota=7.0), AvaliacaoNota(nome="AP2", nota=None)],
    )
    notas_t2 = NotasTurma(
        id_turma="102",
        turma="EQ0002 - TERMODINAMICA",
        avaliacoes=[AvaliacaoNota(nome="AP1", nota=8.0)],
    )
    avals_1 = AvaliacoesTurma(
        id_turma="101",
        turma="EQ0001 - FENOMENOS",
        avaliacoes=avaliacoes_t1 if avaliacoes_t1 is not None else [],
    )
    avals_2 = AvaliacoesTurma(id_turma="102", turma="EQ0002 - TERMODINAMICA", avaliacoes=[])

    plano_1 = PlanoCursoTurma(
        id_turma="101",
        turma="EQ0001 - FENOMENOS",
        metodologia=externo("Aulas expositivas", origem="teste"),
        procedimentos_avaliacao=externo("Duas provas", origem="teste"),
        cronograma_aulas=[
            ItemCronogramaPlano(data="2026-09-01", topico=externo("Escoamento laminar", origem="teste")),
            ItemCronogramaPlano(data="2026-09-10", topico=externo("Destilacao fracionada", origem="teste")),
        ],
        referencias=[externo("Bird", origem="teste")],
    )
    visao_1 = VisaoGeralTurma(
        id_turma="101",
        turma="EQ0001 - FENOMENOS",
        topicos=[
            TopicoAulaTurma(
                data="2026-09-01",
                titulo=externo("Aula 1 - Escoamento", origem="teste"),
                materiais=[MaterialAula(id_material="mat_01", titulo=externo("slides_escoamento.pdf", origem="teste"))],
            ),
            TopicoAulaTurma(
                data="2026-09-10",
                titulo=externo("Aula 2 - Destilacao", origem="teste"),
                materiais=[MaterialAula(id_material="mat_02", titulo=externo("slides_destilacao.pdf", origem="teste"))],
            ),
        ],
    )

    # Turma 102 sem nenhum material
    plano_2 = PlanoCursoTurma(
        id_turma="102",
        turma="EQ0002 - TERMODINAMICA",
        metodologia=externo("Seminarios", origem="teste"),
        procedimentos_avaliacao=externo("Provas", origem="teste"),
        cronograma_aulas=[
            ItemCronogramaPlano(data="2026-09-05", topico=externo("Entropia e segunda lei", origem="teste")),
        ],
        referencias=[],
    )
    visao_2 = VisaoGeralTurma(
        id_turma="102",
        turma="EQ0002 - TERMODINAMICA",
        topicos=[
            TopicoAulaTurma(
                data="2026-09-05",
                titulo=externo("Aula 1 - Entropia", origem="teste"),
                materiais=[],
            ),
        ],
    )

    return _SigaaFalsoTutoria(
        notas_por_turma={"101": notas_t1, "102": notas_t2},
        avaliacoes_por_turma={"101": avals_1, "102": avals_2},
        plano_por_turma={"101": plano_1, "102": plano_2},
        visao_por_turma={"101": visao_1, "102": visao_2},
    )


class TestTutoriaPedagogica(unittest.TestCase):
    def test_alinhamento_construtivo_e_active_recall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(
                curso=657468,
                restaurante=1,
                pasta_config=Path(tmp) / "c",
                pasta_cache=Path(tmp) / "ca",
                pasta_documentos=Path(tmp) / "d",
                limites=Limites(pausa_minima_s=0.5),
            )
            kr = KeyringSeguroMemoria()
            cofre = CofreSistema(backend_keyring=kr)
            cofre.salvar_credencial(Credencial(usuario="aluno", senha="senha_correta_123"))
            http = ClienteEducado(
                cfg.limites,
                relogio=lambda: 10.0,
                dormir=lambda _s: asyncio.sleep(0),
                transporte=TransporteUfcSimulado(),
            )
            sessao = SessaoSigaa(http, cofre, cfg.pasta_config)
            sigaa = ClienteSigaa(sessao, CachePessoal(), cfg)

            async def rodar() -> None:
                plano = await construir_plano_estudo_orientado(
                    sigaa, id_turma="910001", foco="proxima_prova"
                )
                self.assertEqual(plano["id_turma"], "910001")
                self.assertTrue(len(plano["referencias_bibliograficas"]) >= 2)
                self.assertTrue(len(plano["materiais_disponiveis_para_download"]) >= 2)
                rot = plano["roteiro_pedagogico"]
                self.assertIn("baixar", rot["passos_execucao_agente"][0])
                self.assertIn("[Material:", rot["formato_citacao_obrigatorio"])

            asyncio.run(rodar())

    def test_tema_so_no_segundo_material_seleciona_segundo(self) -> None:
        stub = _stub_duas_turmas()
        plano = asyncio.run(
            construir_plano_estudo_orientado(
                stub,
                id_turma="101",
                foco="topico_especifico",
                termo_topico="destilacao",
            )
        )
        alinh = plano["alinhamento_cronograma_materiais"]
        self.assertEqual(len(alinh), 1)
        self.assertEqual(alinh[0]["materiais_associados"][0]["id_material"], "mat_02")
        passo1 = plano["roteiro_pedagogico"]["passos_execucao_agente"][0]
        self.assertIn("id_material='mat_02'", passo1)

    def test_tema_ausente_devolve_lista_vazia_e_aviso(self) -> None:
        stub = _stub_duas_turmas()
        plano = asyncio.run(
            construir_plano_estudo_orientado(
                stub,
                id_turma="101",
                foco="topico_especifico",
                termo_topico="mecanica quantica",
            )
        )
        self.assertEqual(plano["alinhamento_cronograma_materiais"], [])
        self.assertTrue(any("não foi encontrado no cronograma" in a for a in plano["avisos"]))
        passo1 = plano["roteiro_pedagogico"]["passos_execucao_agente"][0]
        self.assertNotIn("baixar(", passo1)
        self.assertNotIn("mat_01", passo1)

    def test_turma_sem_material_nao_inventa_mat_01(self) -> None:
        stub = _stub_duas_turmas()
        plano = asyncio.run(
            construir_plano_estudo_orientado(stub, id_turma="102", foco="proxima_prova")
        )
        self.assertEqual(plano["alinhamento_cronograma_materiais"][0]["materiais_associados"], [])
        passo1 = plano["roteiro_pedagogico"]["passos_execucao_agente"][0]
        self.assertNotIn("baixar(", passo1)
        self.assertNotIn("mat_01", passo1)
        self.assertIn("não tem material associado", passo1)

    def test_proxima_avaliacao_escolhe_futura_mais_proxima_e_aceita_hoje(self) -> None:
        fuso = ZoneInfo("America/Fortaleza")
        avals = [
            ItemAvaliacaoAgendada(data="2026-10-01", hora="08:00", descricao=externo("AP1 passada", origem="t")),
            ItemAvaliacaoAgendada(data="data-invalida", hora=None, descricao=externo("Sem data", origem="t")),
            ItemAvaliacaoAgendada(data="2026-11-20", hora="10:00", descricao=externo("AP3 distante", origem="t")),
            ItemAvaliacaoAgendada(data="2026-11-05", hora="14:00", descricao=externo("AP2 proxima", origem="t")),
        ]
        stub = _stub_duas_turmas(avaliacoes_t1=avals)

        # Relógio em 2026-10-20 -> escolhe 2026-11-05 (e não 2026-10-01 nem 2026-11-20)
        plano = asyncio.run(
            construir_plano_estudo_orientado(
                stub,
                id_turma="101",
                agora=lambda: datetime(2026, 10, 20, 12, 0, tzinfo=fuso),
            )
        )
        self.assertIsNotNone(plano["proxima_avaliacao"])
        self.assertEqual(plano["proxima_avaliacao"]["data"], "2026-11-05")

        # Prova no próprio dia conta como futura
        plano_hoje = asyncio.run(
            construir_plano_estudo_orientado(
                stub,
                id_turma="101",
                agora=lambda: datetime(2026, 11, 5, 23, 30, tzinfo=fuso),
            )
        )
        self.assertIsNotNone(plano_hoje["proxima_avaliacao"])
        self.assertEqual(plano_hoje["proxima_avaliacao"]["data"], "2026-11-05")

        # Nenhuma futura -> None + aviso
        plano_sem = asyncio.run(
            construir_plano_estudo_orientado(
                stub,
                id_turma="101",
                agora=lambda: datetime(2026, 12, 1, 9, 0, tzinfo=fuso),
            )
        )
        self.assertIsNone(plano_sem["proxima_avaliacao"])
        self.assertTrue(any("avaliação futura" in a.lower() for a in plano_sem["avisos"]))

    def test_falha_em_notas_segue_com_materiais_e_aviso(self) -> None:
        stub = _stub_duas_turmas(
            erro_notas_t1=ErroUfc(CodigoErro.LAYOUT_MUDOU, "Tabela de notas ausente")
        )
        plano = asyncio.run(construir_plano_estudo_orientado(stub, id_turma="101"))
        self.assertIsNone(plano["diagnostico_notas_ufc"])
        self.assertEqual(len(plano["materiais_disponiveis_para_download"]), 2)
        self.assertTrue(any("notas falhou" in a.lower() for a in plano["avisos"]))
