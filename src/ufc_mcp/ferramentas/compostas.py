"""
Ferramentas Compostas do Copiloto Acadêmico e Tutoria Pedagógica (`compostas.py`):
27. `aula`
28. `alertas`
29. `grade`
30. `estudo`
31. `dia`
32. `semana`
33. `faltas`
34. `matricula`
35. `ics`
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from ufc_mcp.ferramentas import ContextoApp, DefinicaoFerramenta
from ufc_mcp.fontes.ru.resolucao import resolver_restaurante
from ufc_mcp.nucleo.erros import ErroUfc
from ufc_mcp.servicos.agenda_ics import exportar_arquivo_ics
from ufc_mcp.servicos.alertas import gerar_radar_alertas
from ufc_mcp.servicos.faltas import calcular_faltas_disciplina
from ufc_mcp.servicos.meu_dia import construir_meu_dia, construir_minha_semana
from ufc_mcp.servicos.onde_aula import consultar_onde_e_minha_aula
from ufc_mcp.servicos.planejador import (
    EstrategiaSimulacao,
    analisar_elegibilidade_curricular,
    simular_grades_otimizadas,
)
from ufc_mcp.servicos.tutoria import FocoEstudo, construir_plano_estudo_orientado


def construir_ferramentas_compostas(ctx: ContextoApp) -> list[DefinicaoFerramenta]:
    async def aula(
        data: str | None = None,
        id_turma: str | None = None,
        atualizar: bool = False,
    ) -> str:
        """Verifica bloco, sala e horário das aulas do estudante em uma data e cruza automaticamente com os avisos recentes do professor (com filtro temporal de relevância), o cronograma do Plano de Curso, avaliações agendadas e o Calendário Universitário para alertar se a aula foi cancelada, mudou de sala/laboratório ou se é dia de prova."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            dt_iso = data or date.today().isoformat()
            res = await consultar_onde_e_minha_aula(
                ctx.sigaa,
                ctx.calendario,
                data_iso=dt_iso,
                id_turma=id_turma,
                atualizar=atualizar,
            )
            return res, False, 0, True, []

        return await ctx.executar_com_envelope(
            nome="aula",
            grupo="compostas",
            fonte="copiloto:aula",
            corrotina=_impl,
        )

    async def alertas(
        dias_antecedencia: int = 7,
        atualizar: bool = False,
    ) -> str:
        """Painel proativo de riscos acadêmicos do estudante: identifica disciplinas próximas do limite de 25% de faltas (Art. 113), calcula notas necessárias para aprovação ou Avaliação Final (Art. 114), classifica tarefas por prazo e situação de envio, e lista provas próximas e pendências na biblioteca."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            res = await gerar_radar_alertas(
                ctx.sigaa,
                dias_antecedencia=max(1, min(dias_antecedencia, 30)),
                atualizar=atualizar,
            )
            return res, False, 0, True, []

        return await ctx.executar_com_envelope(
            nome="alertas",
            grupo="compostas",
            fonte="copiloto:alertas",
            corrotina=_impl,
        )

    async def grade(
        ano: int = 2026,
        periodo: int = 2,
        max_disciplinas: int = 5,
        estrategia: EstrategiaSimulacao = "diversificada",
        turno_preferido: Literal["manha", "tarde", "noite", "qualquer"] = "qualquer",
        codigos_desejados: list[str] | None = None,
        codigos_ignorar: list[str] | None = None,
        atualizar: bool = False,
    ) -> str:
        """Conselheiro e otimizador combinatório de matrícula: constrói e valida o grafo acíclico direcionado (DAG) de pré-requisitos e co-requisitos do curso, cruza com as turmas ofertadas no semestre e resolve o problema de satisfação de restrições (Branch-and-Bound) sem choque de horário sob 3 perfis de decisão (desbloqueio curricular, grade compacta e carga equilibrada)."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            prog, _, _ = await ctx.sigaa.obter_progresso_curso(atualizar=atualizar)
            ofertas, _, _ = await ctx.sigaa.obter_ofertas_turmas(
                ano=ano, periodo=periodo, atualizar=atualizar
            )
            res = simular_grades_otimizadas(
                prog.componentes,
                ofertas,
                max_disciplinas=max_disciplinas,
                estrategia=estrategia,
                turno_preferido=turno_preferido,
                codigos_desejados=codigos_desejados,
                codigos_ignorar=codigos_ignorar,
            )
            return res, False, 0, False, []

        return await ctx.executar_com_envelope(
            nome="grade",
            grupo="compostas",
            fonte="copiloto:grade",
            corrotina=_impl,
        )

    async def estudo(
        id_turma: str,
        foco: FocoEstudo = "proxima_prova",
        termo_topico: str | None = None,
        atualizar: bool = False,
    ) -> str:
        """Organiza uma intervenção pedagógica e roteiro de estudo ativo para uma disciplina: diagnostica a situação de notas do estudante segundo o Regimento Geral da UFC (Art. 114), cruza o cronograma e a bibliografia do Plano de Curso com os materiais/slides postados pelo professor e a data da próxima prova, e estrutura uma sequência de estudo com recuperação ativa baseada nos documentos reais da turma."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            res = await construir_plano_estudo_orientado(
                ctx.sigaa,
                id_turma=id_turma,
                foco=foco,
                termo_topico=termo_topico,
                atualizar=atualizar,
            )
            return res, False, 0, True, []

        return await ctx.executar_com_envelope(
            nome="estudo",
            grupo="compostas",
            fonte="copiloto:estudo",
            corrotina=_impl,
        )

    async def dia(
        data: str | None = None,
        restaurante: str | None = None,
        atualizar: bool = False,
    ) -> str:
        """Combina em uma única resposta com degradação graciosa as aulas do dia, o cardápio do Restaurante Universitário, os eventos do Calendário Universitário e as atividades próximas."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            dt_iso = data or date.today().isoformat()
            rest = resolver_restaurante(restaurante)
            if rest is None:
                rest = ctx.config.exigir("restaurante")
            dados, avs, contem_ext = await construir_meu_dia(
                ctx.sigaa,
                ctx.ru,
                ctx.calendario,
                data_iso=dt_iso,
                restaurante=rest,
                atualizar=atualizar,
            )
            return dados, False, 0, contem_ext, avs

        return await ctx.executar_com_envelope(
            nome="dia", grupo="compostas", fonte="copiloto:dia", corrotina=_impl
        )

    async def semana(
        inicio: str | None = None,
        restaurante: str | None = None,
        atualizar: bool = False,
    ) -> str:
        """Agrega 7 dias consecutivos a partir da data inicial com uma única sessão SIGAA, cruzando grade horária, prazos de atividades, eventos do Calendário Universitário e cardápios do RU."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            ini_iso = inicio or date.today().isoformat()
            rest = resolver_restaurante(restaurante)
            if rest is None:
                rest = ctx.config.exigir("restaurante")
            dados, avs, contem_ext = await construir_minha_semana(
                ctx.sigaa,
                ctx.ru,
                ctx.calendario,
                inicio_iso=ini_iso,
                restaurante=rest,
                atualizar=atualizar,
            )
            return dados, False, 0, contem_ext, avs

        return await ctx.executar_com_envelope(
            nome="semana", grupo="compostas", fonte="copiloto:semana", corrotina=_impl
        )

    async def faltas(
        id_turma: str | None = None,
        atualizar: bool = False,
    ) -> str:
        """Calcula detalhadamente para cada disciplina a carga horária, faltas registradas, limite regulamentar de 25% (Art. 113 do Regimento Geral da UFC) e encontros de 2h restantes."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            portal, _, _ = await ctx.sigaa.obter_resumo_portal(atualizar=atualizar)
            lista_diag = []
            for t in portal.turmas:
                if id_turma and t.id_turma != id_turma:
                    continue
                faltas_h = 0
                try:
                    nt, _, _ = await ctx.sigaa.obter_turma_notas(t.id_turma, atualizar=atualizar)
                    if nt.faltas is not None:
                        faltas_h = nt.faltas
                except ErroUfc:
                    pass
                try:
                    fr, _, _ = await ctx.sigaa.obter_turma_frequencia(
                        t.id_turma, atualizar=atualizar
                    )
                    faltas_h = max(faltas_h, fr.total_faltas_horas)
                except ErroUfc:
                    pass
                diag = calcular_faltas_disciplina(
                    id_turma=t.id_turma,
                    codigo=t.codigo,
                    nome=t.nome,
                    carga_horaria_h=t.carga_horaria_h,
                    faltas_registradas_h=faltas_h,
                )
                lista_diag.append(diag.model_dump())
            return {"disciplinas": lista_diag}, False, 0, False, []

        return await ctx.executar_com_envelope(
            nome="faltas",
            grupo="compostas",
            fonte="copiloto:faltas",
            corrotina=_impl,
        )

    async def matricula(atualizar: bool = False) -> str:
        """Analisa a elegibilidade de todas as disciplinas pendentes do currículo separando em elegíveis, bloqueadas por pré-requisito e o fecho transitivo destravado no curso."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            prog, em_c, idade = await ctx.sigaa.obter_progresso_curso(atualizar=atualizar)
            res = analisar_elegibilidade_curricular(prog.componentes)
            return res, em_c, idade, False, []

        return await ctx.executar_com_envelope(
            nome="matricula",
            grupo="compostas",
            fonte="copiloto:matricula",
            corrotina=_impl,
        )

    async def ics(atualizar: bool = False) -> str:
        """Exporta a grade horária das turmas do semestre e os eventos do Calendário Universitário em um arquivo iCalendar padrão RFC 5545 (.ics) na pasta de documentos do usuário."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            portal, _, _ = await ctx.sigaa.obter_resumo_portal(atualizar=atualizar)
            hoje = date.today()
            evs, _, _, _, _ = await ctx.calendario.consultar_eventos(
                hoje.isoformat(), (hoje + timedelta(days=120)).isoformat(), atualizar=atualizar
            )
            caminho = exportar_arquivo_ics(
                ctx.config.pasta_documentos, portal.turmas, evs, data_referencia=hoje
            )
            return (
                {
                    "arquivo_ics": str(caminho),
                    "total_turmas": len(portal.turmas),
                    "total_eventos_calendario": len(evs),
                },
                False,
                0,
                False,
                [],
            )

        return await ctx.executar_com_envelope(
            nome="ics",
            grupo="compostas",
            fonte="copiloto:ics",
            corrotina=_impl,
        )

    return [
        DefinicaoFerramenta(
            "aula",
            "compostas",
            aula.__doc__ or "",
            aula,
        ),
        DefinicaoFerramenta(
            "alertas", "compostas", alertas.__doc__ or "", alertas
        ),
        DefinicaoFerramenta(
            "grade",
            "compostas",
            grade.__doc__ or "",
            grade,
        ),
        DefinicaoFerramenta(
            "estudo",
            "compostas",
            estudo.__doc__ or "",
            estudo,
        ),
        DefinicaoFerramenta("dia", "compostas", dia.__doc__ or "", dia),
        DefinicaoFerramenta(
            "semana", "compostas", semana.__doc__ or "", semana
        ),
        DefinicaoFerramenta(
            "faltas", "compostas", faltas.__doc__ or "", faltas
        ),
        DefinicaoFerramenta(
            "matricula",
            "compostas",
            matricula.__doc__ or "",
            matricula,
        ),
        DefinicaoFerramenta(
            "ics",
            "compostas",
            ics.__doc__ or "",
            ics,
            anotacoes={
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
            },
        ),
    ]
