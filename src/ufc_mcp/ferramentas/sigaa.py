"""Ferramentas do Portal do Discente e Ofertas de Turmas (`sigaa_*`)."""

from __future__ import annotations

from ufc_mcp.ferramentas import ContextoApp, DefinicaoFerramenta
from ufc_mcp.fontes.sigaa.modelos import TipoListagemSigaa
from ufc_mcp.servicos.horario import ORDEM_DIAS


def construir_ferramentas_sigaa(ctx: ContextoApp) -> list[DefinicaoFerramenta]:
    async def portal(atualizar: bool = False) -> str:
        """Obtém o resumo institucional do estudante no Portal do Discente (curso, status, integralização, turmas do semestre e atividades próximas)."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            res, em_c, idade = await ctx.sigaa.obter_resumo_portal(atualizar=atualizar)
            tem_ext = bool(res.noticias_portal or res.atividades_proximas)
            return res.model_dump(), em_c, idade, tem_ext, []

        return await ctx.executar_com_envelope(
            nome="portal", grupo="sigaa", fonte="sigaa:portal", corrotina=_impl
        )

    async def turmas(atualizar: bool = False) -> str:
        """Retorna a lista de turmas matriculadas no semestre atual com código, nome, id_turma, local padrão e horários decodificados."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            res, em_c, idade = await ctx.sigaa.obter_resumo_portal(atualizar=atualizar)
            return (
                {"total": len(res.turmas), "turmas": [t.model_dump() for t in res.turmas]},
                em_c,
                idade,
                False,
                [],
            )

        return await ctx.executar_com_envelope(
            nome="turmas", grupo="sigaa", fonte="sigaa:portal", corrotina=_impl
        )

    async def horario(atualizar: bool = False) -> str:
        """Constrói a grade horária semanal ordenada de segunda a sábado a partir das turmas matriculadas."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            res, em_c, idade = await ctx.sigaa.obter_resumo_portal(atualizar=atualizar)
            grade: dict[str, list[dict[str, str]]] = {
                dia: [] for dia in ("SEG", "TER", "QUA", "QUI", "SEX", "SAB")
            }
            for t in res.turmas:
                for h in t.horarios:
                    grade.setdefault(h.dia, []).append(
                        {
                            "inicio": h.inicio,
                            "fim": h.fim,
                            "codigo": t.codigo,
                            "nome": t.nome,
                            "local": t.local,
                            "id_turma": t.id_turma,
                        }
                    )
            for dia in grade:
                grade[dia].sort(key=lambda item: item["inicio"])
            ordenada = {
                k: grade[k]
                for k in sorted(grade.keys(), key=lambda d: ORDEM_DIAS.get(d, 99))
            }
            return {"grade_semanal": ordenada}, em_c, idade, False, []

        return await ctx.executar_com_envelope(
            nome="horario", grupo="sigaa", fonte="sigaa:horario", corrotina=_impl
        )

    async def progresso(atualizar: bool = False) -> str:
        """Lê a árvore de integralização e o grafo de pré-requisitos e co-requisitos do currículo do estudante na tela Progresso no Curso."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            res, em_c, idade = await ctx.sigaa.obter_progresso_curso(atualizar=atualizar)
            return res.model_dump(), em_c, idade, False, []

        return await ctx.executar_com_envelope(
            nome="progresso", grupo="sigaa", fonte="sigaa:progresso", corrotina=_impl
        )

    async def ira(atualizar: bool = False) -> str:
        """Consulta a evolução semestral do Índice de Rendimento Acadêmico (IRA Individual e Geral) do estudante em relação à média e desvio padrão do curso."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            res, em_c, idade = await ctx.sigaa.obter_historico_ira(atualizar=atualizar)
            return res.model_dump(), em_c, idade, False, []

        return await ctx.executar_com_envelope(
            nome="ira", grupo="sigaa", fonte="sigaa:ira", corrotina=_impl
        )

    async def pendencias(atualizar: bool = False) -> str:
        """Consulta o relatório de pendências para conclusão de curso (carga horária pendente, ENADE e biblioteca)."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            res, em_c, idade = await ctx.sigaa.obter_pendencias_conclusao(atualizar=atualizar)
            return res.model_dump(), em_c, idade, False, []

        return await ctx.executar_com_envelope(
            nome="pendencias",
            grupo="sigaa",
            fonte="sigaa:pendencias",
            corrotina=_impl,
        )

    async def biblioteca(atualizar: bool = False) -> str:
        """Verifica a situação de empréstimos e regularidade do estudante junto ao sistema de bibliotecas (Pergamum/SIGAA)."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            res, em_c, idade = await ctx.sigaa.obter_situacao_biblioteca(atualizar=atualizar)
            return res.model_dump(), em_c, idade, False, []

        return await ctx.executar_com_envelope(
            nome="biblioteca",
            grupo="sigaa",
            fonte="sigaa:biblioteca",
            corrotina=_impl,
        )

    async def agenda(atualizar: bool = False) -> str:
        """Consulta a agenda consolidada de turmas do discente no SIGAA."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            res, em_c, idade = await ctx.sigaa.obter_agenda_turmas(atualizar=atualizar)
            return res, em_c, idade, False, []

        return await ctx.executar_com_envelope(
            nome="agenda", grupo="sigaa", fonte="sigaa:agenda", corrotina=_impl
        )

    async def listagem(tipo: TipoListagemSigaa, atualizar: bool = False) -> str:
        """Consulta 15 telas de listagem administrativa e acadêmica do Portal do Discente (ênfases, plano de estudo, ENADE, bloqueios, movimentações, mobilidade, solicitações de matrícula, trancamentos, supressoes, extensão, auxílios, bolsas e estágios)."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            res, em_c, idade = await ctx.sigaa.obter_listagem(tipo, atualizar=atualizar)
            return res.model_dump(), em_c, idade, False, []

        return await ctx.executar_com_envelope(
            nome="listagem",
            grupo="sigaa",
            fonte=f"sigaa:listagem:{tipo}",
            corrotina=_impl,
        )

    async def ofertas(
        ano: int = 2026,
        periodo: int = 2,
        codigo_componente: str | None = None,
        id_curso: int | None = None,
        atualizar: bool = False,
    ) -> str:
        """Consulta as turmas ofertadas no semestre (horários decodificados, locais, docentes e vagas) usando o portal público do curso no SIGAA ou a busca de turmas do discente."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            ofertas, em_c, idade = await ctx.sigaa.obter_ofertas_turmas(
                ano=ano,
                periodo=periodo,
                codigo_componente=codigo_componente,
                id_curso=id_curso,
                atualizar=atualizar,
            )
            return (
                {
                    "ano": ano,
                    "periodo": periodo,
                    "id_curso": id_curso or ctx.config.curso,
                    "total_turmas": len(ofertas),
                    "turmas": [o.model_dump() for o in ofertas],
                },
                em_c,
                idade,
                False,
                [],
            )

        return await ctx.executar_com_envelope(
            nome="ofertas",
            grupo="sigaa",
            fonte="sigaa:ofertas",
            corrotina=_impl,
        )

    return [
        DefinicaoFerramenta("portal", "sigaa", portal.__doc__ or "", portal),
        DefinicaoFerramenta("turmas", "sigaa", turmas.__doc__ or "", turmas),
        DefinicaoFerramenta(
            "horario",
            "sigaa",
            horario.__doc__ or "",
            horario,
        ),
        DefinicaoFerramenta(
            "progresso",
            "sigaa",
            progresso.__doc__ or "",
            progresso,
        ),
        DefinicaoFerramenta(
            "ira", "sigaa", ira.__doc__ or "", ira
        ),
        DefinicaoFerramenta(
            "pendencias",
            "sigaa",
            pendencias.__doc__ or "",
            pendencias,
        ),
        DefinicaoFerramenta(
            "biblioteca",
            "sigaa",
            biblioteca.__doc__ or "",
            biblioteca,
        ),
        DefinicaoFerramenta(
            "agenda", "sigaa", agenda.__doc__ or "", agenda
        ),
        DefinicaoFerramenta(
            "listagem", "sigaa", listagem.__doc__ or "", listagem
        ),
        DefinicaoFerramenta(
            "ofertas",
            "sigaa",
            ofertas.__doc__ or "",
            ofertas,
        ),
    ]
