"""Resolução de nome ou alias de restaurante universitário para o id interno do site."""

from __future__ import annotations

import itertools
import re
import unicodedata

from ufc_mcp.fontes.ru.modelos import RESTAURANTES_UFC, UNIDADES_RU
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc

_PALAVRAS_VAZIAS = frozenset(
    {"restaurante", "universitario", "ru", "de", "do", "da", "campus", "em", "unidade"}
)


def _normalizar(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return re.sub(r"[\W_]+", " ", sem_acento.lower()).strip()


_ALIAS_PARA_ID: dict[str, int] = {
    _normalizar(alias): int(dados["id"])  # type: ignore[call-overload]
    for dados in UNIDADES_RU.values()
    for alias in dados["aliases"]  # type: ignore[attr-defined]
}
_ID_PARA_SLUG: dict[int, str] = {
    int(dados["id"]): slug for slug, dados in UNIDADES_RU.items()  # type: ignore[call-overload]
}


def _nomes_validos() -> str:
    return ", ".join(str(RESTAURANTES_UFC[i]["cidade"]) for i in sorted(RESTAURANTES_UFC))


def resolver_restaurante(valor: str | int | None) -> int | None:
    """Converte nome ou alias (ex.: "Pici", "RU de Quixadá") no id interno do site."""
    if valor is None:
        return None
    if isinstance(valor, int) and not isinstance(valor, bool):
        if valor in RESTAURANTES_UFC:
            return valor
        raise ErroUfc(
            CodigoErro.PARAMETRO_INVALIDO,
            f"Restaurante inválido: {valor}. Informe o nome da unidade. Opções: {_nomes_validos()}.",
        )
    if not isinstance(valor, str):
        raise ErroUfc(
            CodigoErro.PARAMETRO_INVALIDO,
            f"Restaurante inválido. Informe o nome da unidade. Opções: {_nomes_validos()}.",
        )

    palavras = [p for p in _normalizar(valor).split() if p not in _PALAVRAS_VAZIAS]
    candidatos = list(palavras)
    candidatos += [f"{a} {b}" for a, b in itertools.pairwise(palavras)]
    encontrados = {_ALIAS_PARA_ID[c] for c in candidatos if c in _ALIAS_PARA_ID}

    if len(encontrados) == 1:
        return next(iter(encontrados))
    if len(encontrados) > 1:
        raise ErroUfc(
            CodigoErro.PARAMETRO_INVALIDO,
            f"Informe uma única unidade. Opções: {_nomes_validos()}.",
        )
    raise ErroUfc(
        CodigoErro.PARAMETRO_INVALIDO,
        f"Restaurante '{valor}' não encontrado. Opções: {_nomes_validos()} "
        "(Pici, Benfica, Porangabuçu e Labomar fazem parte de Fortaleza).",
    )


def slug_restaurante(valor: str | int | None) -> str | None:
    """Slug canônico (ex.: "fortaleza") para nome, alias ou id legado."""
    id_ = resolver_restaurante(valor)
    return None if id_ is None else _ID_PARA_SLUG[id_]
