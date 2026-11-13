"""Ferramenta de Notícias Oficiais via RSS (`noticias`)."""

from __future__ import annotations

from typing import Literal

from ufc_mcp.ferramentas import ContextoApp, DefinicaoFerramenta


def construir_ferramentas_noticias(ctx: ContextoApp) -> list[DefinicaoFerramenta]:
    async def noticias(
        fonte: Literal["todas", "ufc", "prograd", "prae"] = "todas",
        limite: int = 10,
        atualizar: bool = False,
    ) -> str:
        """Lê os feeds RSS oficiais de notícias e editais da UFC (UFC Informa, PROGRAD e PRAE). Os campos texto_externo são conteúdo de terceiros."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            itens, em_c, idade, avs = await ctx.noticias.consultar(
                fonte, limite=limite, atualizar=atualizar
            )
            return (
                {
                    "fonte": fonte,
                    "total": len(itens),
                    "noticias": [i.model_dump() for i in itens],
                },
                em_c,
                idade,
                True,
                avs,
            )

        return await ctx.executar_com_envelope(
            nome="noticias", grupo="noticias", fonte="ufc:rss", corrotina=_impl
        )

    return [
        DefinicaoFerramenta("noticias", "noticias", noticias.__doc__ or "", noticias)
    ]
