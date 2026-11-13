"""Cliente assíncrono para os 3 feeds RSS oficiais da UFC."""

from __future__ import annotations

from typing import Literal

from ufc_mcp.fontes.noticias.modelos import FONTES_RSS_UFC, ItemNoticiaUfc
from ufc_mcp.fontes.noticias.parser import parse_rss_noticias
from ufc_mcp.nucleo.cache import CachePublico
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.http import ClienteEducado

TTL_NOTICIAS_S = 1800  # 30 min


class ClienteNoticias:
    def __init__(self, http: ClienteEducado, cache: CachePublico) -> None:
        self.http = http
        self.cache = cache

    async def consultar(
        self,
        fonte: Literal["todas", "ufc", "prograd", "prae"] = "todas",
        *,
        limite: int = 10,
        atualizar: bool = False,
    ) -> tuple[list[ItemNoticiaUfc], bool, int, list[str]]:
        fontes_alvo = list(FONTES_RSS_UFC.keys()) if fonte == "todas" else [fonte]
        for f in fontes_alvo:
            if f not in FONTES_RSS_UFC:
                raise ErroUfc(
                    CodigoErro.PARAMETRO_INVALIDO,
                    f"Fonte de notícia inválida: {f}. Use todas, ufc, prograd ou prae.",
                )

        todas_noticias: list[ItemNoticiaUfc] = []
        algum_cache = False
        maior_idade = 0
        avisos: list[str] = []

        for f in fontes_alvo:
            chave = f"rss:{f}"
            xml_corpo: str | None = None
            if not atualizar:
                em_cache = self.cache.obter(chave)
                if em_cache is not None:
                    xml_corpo = em_cache.corpo
                    algum_cache = True
                    maior_idade = max(maior_idade, em_cache.idade_s)

            if xml_corpo is None:
                try:
                    resp = await self.http.get(FONTES_RSS_UFC[f])
                    xml_corpo = resp.texto
                    self.cache.guardar(chave, xml_corpo, TTL_NOTICIAS_S)
                except ErroUfc as exc:
                    venc = self.cache.obter_vencido(chave, max_idade_s=86400)
                    if venc is not None:
                        xml_corpo = venc.corpo
                        algum_cache = True
                        maior_idade = max(maior_idade, venc.idade_s)
                        avisos.append(f"Feed {f} indisponível; usando cache recente.")
                    elif len(fontes_alvo) > 1:
                        avisos.append(f"Feed {f} indisponível: {exc.mensagem}")
                        continue
                    else:
                        raise

            itens = parse_rss_noticias(xml_corpo, fonte=f, limite=limite)
            todas_noticias.extend(itens)

        return todas_noticias[: max(1, limite)], algum_cache, maior_idade, avisos
