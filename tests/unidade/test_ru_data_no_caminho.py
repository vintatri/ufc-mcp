"""Regressão: o site do RU ignora `?data=` (sempre devolve hoje); a data vai no caminho."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import date, timedelta
from pathlib import Path

from ufc_mcp.fontes.ru.cliente import ClienteRu, url_cardapio_ru
from ufc_mcp.fontes.ru.parser import parse_cardapio_ru
from ufc_mcp.nucleo.cache import CachePublico
from ufc_mcp.nucleo.http import RespostaHttp

_DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def _pagina(dt: date, prato: str) -> str:
    return (
        f'<table><thead><tr><th class="atual">{_DIAS[dt.weekday()]} ({dt:%d/%m})</th></tr></thead></table>'
        '<h3 id="almoco">Almoço</h3><table class="refeicao almoco"><tbody>'
        f'<tr class="item"><td>Principal</td><td><span class="desc">{prato}</span></td></tr>'
        "</tbody></table>"
    )


class _HttpSimulado:
    """Imita o site: só entende a data no caminho; qualquer outra forma devolve hoje."""

    def __init__(self, hoje: date) -> None:
        self.hoje = hoje
        self.urls: list[str] = []

    async def get(self, url: str) -> RespostaHttp:
        self.urls.append(url)
        ultimo = url.rstrip("/").rsplit("/", 1)[-1]
        try:
            dt = date.fromisoformat(ultimo)
        except ValueError:
            dt = self.hoje
        return RespostaHttp(status=200, url_final=url, texto=_pagina(dt, f"Prato {dt.isoformat()}"))


def test_url_leva_a_data_no_caminho_e_nao_na_query() -> None:
    url = url_cardapio_ru("2026-11-11", 1)
    assert url.endswith("/2026-11-11")
    assert "?" not in url


def test_dias_diferentes_nao_repetem_o_cardapio_de_hoje() -> None:
    hoje = date.today()
    with tempfile.TemporaryDirectory() as tmp:
        http = _HttpSimulado(hoje)
        ru = ClienteRu(http, CachePublico(Path(tmp) / "c.sqlite3"))  # type: ignore[arg-type]
        d1, d2 = hoje, hoje - timedelta(days=1)
        c1 = asyncio.run(ru.consultar_dia(d1.isoformat()))[0]
        c2 = asyncio.run(ru.consultar_dia(d2.isoformat()))[0]
    assert c1.refeicoes[0].pratos[0].descricao == f"Prato {d1.isoformat()}"
    assert c2.refeicoes[0].pratos[0].descricao == f"Prato {d2.isoformat()}"


def test_pagina_de_outro_dia_nao_e_atribuida_ao_dia_pedido() -> None:
    html = _pagina(date(2026, 11, 13), "Escondidinho")
    card = parse_cardapio_ru(html, data="2026-11-11")
    assert card.tem_cardapio is False and card.refeicoes == []


def test_cliente_avisa_e_nao_cacheia_pagina_de_outro_dia() -> None:
    hoje = date.today()
    alvo = hoje - timedelta(days=2)

    class _SempreHoje:
        async def get(self, url: str) -> RespostaHttp:
            return RespostaHttp(status=200, url_final=url, texto=_pagina(hoje, "X"))

    with tempfile.TemporaryDirectory() as tmp:
        cache = CachePublico(Path(tmp) / "c.sqlite3")
        ru = ClienteRu(_SempreHoje(), cache)  # type: ignore[arg-type]
        card, _, _, avisos = asyncio.run(ru.consultar_dia(alvo.isoformat()))
        assert cache.obter(f"ru:v2:1:{alvo.isoformat()}") is None
    assert card.tem_cardapio is False
    assert any("não devolveu o cardápio" in a for a in avisos)
