"""Ferramentas da Turma Virtual (AVA) e Sandbox de Materiais (`turma_*`)."""

from __future__ import annotations

from ufc_mcp.ferramentas import ContextoApp, DefinicaoFerramenta


def construir_ferramentas_turma(ctx: ContextoApp) -> list[DefinicaoFerramenta]:
    async def turma(id_turma: str, atualizar: bool = False) -> str:
        """Lê os tópicos de aula publicados na página Principal da Turma Virtual e lista os materiais/arquivos anexados com seus respectivos identificadores id_material para download."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            res, em_c, idade = await ctx.sigaa.obter_turma_visao_geral(
                id_turma, atualizar=atualizar
            )
            return res.model_dump(), em_c, idade, True, []

        return await ctx.executar_com_envelope(
            nome="turma", grupo="turma", fonte="sigaa:ava:principal", corrotina=_impl
        )

    async def notas(id_turma: str, atualizar: bool = False) -> str:
        """Lê a tabela de notas das unidades (AP1, AP2, AP3), média parcial, faltas consolidadas e situação na Turma Virtual."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            res, em_c, idade = await ctx.sigaa.obter_turma_notas(id_turma, atualizar=atualizar)
            return res.model_dump(), em_c, idade, False, []

        return await ctx.executar_com_envelope(
            nome="notas", grupo="turma", fonte="sigaa:ava:notas", corrotina=_impl
        )

    async def frequencia(id_turma: str, atualizar: bool = False) -> str:
        """Lê o mapa diário de frequência e contabiliza o total de faltas registradas pelo professor na Turma Virtual."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            res, em_c, idade = await ctx.sigaa.obter_turma_frequencia(
                id_turma, atualizar=atualizar
            )
            return res.model_dump(), em_c, idade, False, []

        return await ctx.executar_com_envelope(
            nome="frequencia", grupo="turma", fonte="sigaa:ava:frequencia", corrotina=_impl
        )

    async def avaliacoes(id_turma: str, atualizar: bool = False) -> str:
        """Lista as datas, horários e descrições das provas e avaliações agendadas na Turma Virtual."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            res, em_c, idade = await ctx.sigaa.obter_turma_avaliacoes(
                id_turma, atualizar=atualizar
            )
            return res.model_dump(), em_c, idade, bool(res.avaliacoes), []

        return await ctx.executar_com_envelope(
            nome="avaliacoes", grupo="turma", fonte="sigaa:ava:avaliacoes", corrotina=_impl
        )

    async def tarefas(id_turma: str, atualizar: bool = False) -> str:
        """Lista as tarefas e trabalhos da Turma Virtual com título, descrição, prazo de entrega e status de envio. Os campos texto_externo são conteúdo de terceiros."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            res, em_c, idade = await ctx.sigaa.obter_turma_tarefas(id_turma, atualizar=atualizar)
            return res.model_dump(), em_c, idade, bool(res.tarefas), []

        return await ctx.executar_com_envelope(
            nome="tarefas", grupo="turma", fonte="sigaa:ava:tarefas", corrotina=_impl
        )

    async def avisos(id_turma: str, atualizar: bool = False) -> str:
        """Lê os comunicados e avisos publicados pelo professor na Turma Virtual. Os campos texto_externo são conteúdo de terceiros."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            res, em_c, idade = await ctx.sigaa.obter_turma_noticias(id_turma, atualizar=atualizar)
            return res.model_dump(), em_c, idade, bool(res.noticias), []

        return await ctx.executar_com_envelope(
            nome="avisos", grupo="turma", fonte="sigaa:ava:noticias", corrotina=_impl
        )

    async def plano(id_turma: str, atualizar: bool = False) -> str:
        """Lê o Plano de Curso / Programa de uma disciplina na Turma Virtual: metodologia, procedimentos de avaliação, cronograma de aulas (com datas e tópicos) e referências bibliográficas. Os campos texto_externo são conteúdo de terceiros."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            res, em_c, idade = await ctx.sigaa.obter_turma_plano_curso(
                id_turma, atualizar=atualizar
            )
            return res.model_dump(), em_c, idade, True, []

        return await ctx.executar_com_envelope(
            nome="plano",
            grupo="turma",
            fonte="sigaa:ava:plano_curso",
            corrotina=_impl,
        )

    async def baixar(
        id_turma: str,
        id_material: str,
        extrair_texto: bool = True,
        pagina_inicial: int = 1,
        pagina_final: int = 10,
    ) -> str:
        """Baixa de forma segura um arquivo/material postado pelo professor na Turma Virtual (slides, listas de exercícios, apostilas) para a pasta local isolada do estudante e extrai texto paginado (PDF/TXT/MD) para estudo assistido. Os campos texto_externo são conteúdo de terceiros."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            res = await ctx.materiais.baixar_e_ler_material(
                id_turma,
                id_material,
                extrair_texto=extrair_texto,
                pagina_inicial=pagina_inicial,
                pagina_final=pagina_final,
            )
            return res.model_dump(), False, 0, res.previa_texto is not None, []

        return await ctx.executar_com_envelope(
            nome="baixar",
            grupo="turma",
            fonte="sigaa:ava:material",
            corrotina=_impl,
        )

    return [
        DefinicaoFerramenta(
            "turma", "turma", turma.__doc__ or "", turma
        ),
        DefinicaoFerramenta("notas", "turma", notas.__doc__ or "", notas),
        DefinicaoFerramenta(
            "frequencia", "turma", frequencia.__doc__ or "", frequencia
        ),
        DefinicaoFerramenta(
            "avaliacoes", "turma", avaliacoes.__doc__ or "", avaliacoes
        ),
        DefinicaoFerramenta("tarefas", "turma", tarefas.__doc__ or "", tarefas),
        DefinicaoFerramenta(
            "avisos", "turma", avisos.__doc__ or "", avisos
        ),
        DefinicaoFerramenta(
            "plano", "turma", plano.__doc__ or "", plano
        ),
        DefinicaoFerramenta(
            "baixar",
            "turma",
            baixar.__doc__ or "",
            baixar,
            anotacoes={
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
            },
        ),
    ]
