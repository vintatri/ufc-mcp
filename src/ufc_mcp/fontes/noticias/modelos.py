"""Modelos de dados dos feeds RSS institucionais da UFC (UFC Informa, PROGRAD, PRAE)."""

from __future__ import annotations

from ufc_mcp.nucleo.higiene import TextoExterno
from ufc_mcp.nucleo.modelos_base import BaseModel

FONTES_RSS_UFC: dict[str, str] = {
    "ufc": "https://ufcinforma.ufc.br/feed",
    "prograd": "https://prograd.ufc.br/pt/feed/",
    "prae": "https://prae.ufc.br/pt/feed/",
}


class ItemNoticiaUfc(BaseModel):
    fonte: str
    titulo: TextoExterno
    link: str
    publicada_em: str | None = None
    resumo: TextoExterno
