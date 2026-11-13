"""Sanitização determinística contra Indirect Prompt Injection (Nível 1 de Defesa)."""

from __future__ import annotations

import html
import re
import unicodedata

from bs4 import BeautifulSoup

from ufc_mcp.nucleo.modelos_base import BaseModel

CATEGORIAS_UNICODE_PROIBIDAS = frozenset({"Cc", "Cf", "Co", "Cs"})
REGEX_ESPACOS_HORIZONTAIS = re.compile(r"[ \t\r\f\v]+")
REGEX_QUEBRAS_EXCESSIVAS = re.compile(r"\n{3,}")


class TextoExterno(BaseModel):
    """Invólucro tipado para todo texto proveniente de terceiros (notícias, avisos, PDFs)."""

    texto_externo: str
    origem: str
    cortado: bool = False


def limpar_texto(bruto: str, max_chars: int = 2000) -> tuple[str, bool]:
    """
    Limpa HTML, remove tags <script>/<style>, filtra categorias Unicode invisíveis/bidi
    (Cc, Cf, Co, Cs) e trunca em max_chars.
    """
    if not bruto:
        return "", False

    texto = bruto
    if "<" in texto and ">" in texto:
        soup = BeautifulSoup(texto, "lxml")
        for tag in soup(["script", "style", "iframe", "object", "embed"]):
            tag.decompose()
        texto = soup.get_text(separator=" ")

    texto = html.unescape(texto)
    texto = unicodedata.normalize("NFC", texto)

    caracteres_limpos: list[str] = []
    for ch in texto:
        if ch in ("\n", "\t"):
            caracteres_limpos.append(ch)
            continue
        cat = unicodedata.category(ch)
        if cat in CATEGORIAS_UNICODE_PROIBIDAS:
            continue
        caracteres_limpos.append(ch)

    texto = "".join(caracteres_limpos)
    linhas = [REGEX_ESPACOS_HORIZONTAIS.sub(" ", linha).strip() for linha in texto.split("\n")]
    texto = "\n".join(linhas).strip()
    texto = REGEX_QUEBRAS_EXCESSIVAS.sub("\n\n", texto)

    if len(texto) > max_chars:
        return f"{texto[:max_chars]} […cortado]", True
    return texto, False


def externo(bruto: str, origem: str, max_chars: int = 2000) -> TextoExterno:
    """Encapsula texto bruto em TextoExterno devidamente higienizado."""
    limpo, cortado = limpar_texto(bruto, max_chars=max_chars)
    return TextoExterno(texto_externo=limpo, origem=origem, cortado=cortado)


def sem_acentos_minusculo(s: str) -> str:
    """Decompõe em NFD, remove diacríticos (Mn) e converte para casefold."""
    decomposto = unicodedata.normalize("NFD", s)
    sem_marcas = "".join(ch for ch in decomposto if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", sem_marcas).casefold().strip()
