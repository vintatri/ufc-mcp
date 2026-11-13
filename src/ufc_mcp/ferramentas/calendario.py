"""Ferramentas do Calendário Universitário (`calendario`, `calendario_curso`)."""

from __future__ import annotations

from datetime import date, timedelta

from ufc_mcp.ferramentas import ContextoApp, DefinicaoFerramenta


def construir_ferramentas_calendario(ctx: ContextoApp) -> list[DefinicaoFerramenta]:
    async def calendario(
        inicio: str | None = None,
        fim: str | None = None,
        texto: str | None = None,
        limite: int = 50,
        atualizar: bool = False,
    ) -> str:
        """Consulta eventos, feriados, recessos e prazos de matrícula/trancamento no Calendário Universitário oficial da UFC."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            hoje = date.today()
            ini_iso = inicio or hoje.isoformat()
            fim_iso = fim or (date.fromisoformat(ini_iso) + timedelta(days=30)).isoformat()
            evs, nao_int, em_c, idade, avs = await ctx.calendario.consultar_eventos(
                ini_iso, fim_iso, texto=texto, limite=limite, atualizar=atualizar
            )
            return (
                {
                    "inicio": ini_iso,
                    "fim": fim_iso,
                    "total": len(evs),
                    "nao_interpretados": nao_int,
                    "eventos": [e.model_dump() for e in evs],
                },
                em_c,
                idade,
                False,
                avs,
            )

        return await ctx.executar_com_envelope(
            nome="calendario",
            grupo="calendario",
            fonte="ufc2012:calendario",
            corrotina=_impl,
        )

    async def calendario_curso(
        id_curso: int | None = None,
        atualizar: bool = False,
    ) -> str:
        """Consulta o calendário específico de períodos de matrícula e processamento de um curso de graduação no portal público do SIGAA."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            cid = id_curso if id_curso is not None else ctx.config.exigir("curso")
            cal, em_c, idade = await ctx.sigaa_publico.consultar_calendario_curso(
                cid, atualizar=atualizar
            )
            return cal.model_dump(), em_c, idade, False, []

        return await ctx.executar_com_envelope(
            nome="calendario_curso",
            grupo="calendario",
            fonte="sigaa_publico:calendario_curso",
            corrotina=_impl,
        )

    return [
        DefinicaoFerramenta(
            "calendario",
            "calendario",
            calendario.__doc__ or "",
            calendario,
        ),
        DefinicaoFerramenta(
            "calendario_curso",
            "calendario",
            calendario_curso.__doc__ or "",
            calendario_curso,
        ),
    ]
