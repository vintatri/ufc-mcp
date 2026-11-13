"""Ferramentas do Restaurante Universitário (`cardapio`, `cardapio_semana`, `restaurantes`)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from ufc_mcp.ferramentas import ContextoApp, DefinicaoFerramenta
from ufc_mcp.fontes.ru.modelos import RESTAURANTES_UFC, UNIDADES_RU
from ufc_mcp.fontes.ru.resolucao import resolver_restaurante
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc


def construir_ferramentas_ru(ctx: ContextoApp) -> list[DefinicaoFerramenta]:
    async def cardapio(
        data: str | None = None,
        restaurante: str | None = None,
        refeicao: Literal["todas", "desjejum", "almoco", "jantar"] = "todas",
        atualizar: bool = False,
    ) -> str:
        """Consulta o cardápio do Restaurante Universitário (RU) da UFC em uma data específica, incluindo opções vegetarianas e alertas de glúten e lactose."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            if refeicao not in ("todas", "desjejum", "almoco", "jantar"):
                raise ErroUfc(
                    CodigoErro.PARAMETRO_INVALIDO,
                    f"Refeição inválida: {refeicao}. Use todas, desjejum, almoco ou jantar.",
                )
            dt_str = data or date.today().isoformat()
            rest_id = resolver_restaurante(restaurante)
            if rest_id is None:
                rest_id = ctx.config.exigir("restaurante")
            card, em_c, idade, avs = await ctx.ru.consultar_dia(
                dt_str, restaurante=rest_id, atualizar=atualizar
            )
            dados = card.model_dump()
            if refeicao != "todas":
                dados["refeicoes"] = [
                    r for r in dados["refeicoes"] if r["tipo"] == refeicao
                ]
            return dados, em_c, idade, False, avs

        return await ctx.executar_com_envelope(
            nome="cardapio", grupo="ru", fonte="ufc2012:ru", corrotina=_impl
        )

    async def cardapio_semana(
        inicio: str | None = None,
        restaurante: str | None = None,
        atualizar: bool = False,
    ) -> str:
        """Retorna os cardápios dos 5 dias úteis (segunda a sexta-feira) do Restaurante Universitário a partir da semana informada."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            ini_str = inicio or date.today().isoformat()
            rest_id = resolver_restaurante(restaurante)
            if rest_id is None:
                rest_id = ctx.config.exigir("restaurante")
            dias, em_c, idade, avs = await ctx.ru.consultar_semana(
                ini_str, restaurante=rest_id, atualizar=atualizar
            )
            return (
                {
                    "inicio_solicitado": ini_str,
                    "restaurante_id": rest_id,
                    "dias": [d.model_dump() for d in dias],
                },
                em_c,
                idade,
                False,
                avs,
            )

        return await ctx.executar_com_envelope(
            nome="cardapio_semana", grupo="ru", fonte="ufc2012:ru", corrotina=_impl
        )

    async def restaurantes() -> str:
        """Lista estática das 5 unidades/campi (Fortaleza, Russas, Quixadá, Crateús, Sobral) do Restaurante Universitário da UFC e seus apelidos; use o nome, ex.: Fortaleza ou Pici."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            unidades = [
                {
                    "id": k,
                    "nome": v["nome"],
                    "cidade": v["cidade"],
                    "aliases": next(
                        (u["aliases"] for u in UNIDADES_RU.values() if u["id"] == k), []
                    ),
                }
                for k, v in sorted(RESTAURANTES_UFC.items())
            ]
            return {"restaurantes": unidades}, True, 0, False, []

        return await ctx.executar_com_envelope(
            nome="restaurantes", grupo="ru", fonte="ufc_mcp:estatico", corrotina=_impl
        )

    return [
        DefinicaoFerramenta("cardapio", "ru", cardapio.__doc__ or "", cardapio),
        DefinicaoFerramenta(
            "cardapio_semana", "ru", cardapio_semana.__doc__ or "", cardapio_semana
        ),
        DefinicaoFerramenta(
            "restaurantes", "ru", restaurantes.__doc__ or "", restaurantes
        ),
    ]
