"""Parser RSS seguro (com proteção anti-XXE e higienização em TextoExterno)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from ufc_mcp.fontes.noticias.modelos import ItemNoticiaUfc
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.higiene import externo

REGEX_PROIBIDO_XML = re.compile(r"<!\s*(DOCTYPE|ENTITY)\b", re.IGNORECASE)


def parse_rss_noticias(xml_texto: str, *, fonte: str, limite: int = 10) -> list[ItemNoticiaUfc]:
    """Valida que o XML não contém declarações DOCTYPE/ENTITY (anti-XXE) e extrai notícias."""
    if REGEX_PROIBIDO_XML.search(xml_texto):
        raise ErroUfc(
            CodigoErro.ACAO_BLOQUEADA,
            "Feed XML rejeitado por conter declaração DOCTYPE ou ENTITY (proteção anti-XXE).",
        )

    try:
        root = ET.fromstring(xml_texto.strip())
    except ET.ParseError as exc:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            f"Feed RSS de '{fonte}' não é um XML bem formado.",
        ) from exc

    itens_xml = root.findall(".//item")
    if not itens_xml:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            f"Feed RSS de '{fonte}' não contém elementos <item>.",
        )

    noticias: list[ItemNoticiaUfc] = []
    for item in itens_xml[: max(1, limite)]:
        titulo_el = item.find("title")
        link_el = item.find("link")
        desc_el = item.find("description")
        pub_el = item.find("pubDate")

        titulo_bruto = (titulo_el.text or "").strip() if titulo_el is not None else ""
        link_bruto = (link_el.text or "").strip() if link_el is not None else ""
        desc_bruto = (desc_el.text or "").strip() if desc_el is not None else ""
        pub_bruto = (pub_el.text or "").strip() if pub_el is not None else None

        if not titulo_bruto or not link_bruto:
            continue

        noticias.append(
            ItemNoticiaUfc(
                fonte=fonte,
                titulo=externo(titulo_bruto, origem=f"rss:{fonte}:titulo", max_chars=300),
                link=link_bruto,
                publicada_em=pub_bruto,
                resumo=externo(desc_bruto, origem=f"rss:{fonte}:resumo", max_chars=1200),
            )
        )

    if not noticias:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            f"Feed RSS de '{fonte}' não possui itens com <title> e <link> válidos.",
        )
    return noticias
