"""Parser puro e síncrono do cardápio do Restaurante Universitário da UFC."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from ufc_mcp.fontes.ru.modelos import RESTAURANTES_UFC, CardapioDia, PratoRu, RefeicaoRu
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc


def data_exibida_na_pagina(html: str) -> tuple[int, int] | None:
    """Devolve (dia, mês) do cabeçalho `th.atual` ("Quarta (11/11)"), ou None se ausente."""
    soup = BeautifulSoup(html, "lxml")
    th = soup.select_one("th.atual")
    if th is None:
        return None
    m = re.search(r"\((\d{1,2})/(\d{1,2})\)", th.get_text(" ", strip=True))
    return (int(m.group(1)), int(m.group(2))) if m else None


def pagina_confere_com_data(html: str, data_iso: str) -> bool:
    """False apenas quando a página declara explicitamente um dia diferente do pedido."""
    exibida = data_exibida_na_pagina(html)
    if exibida is None:
        return True
    return exibida == (int(data_iso[8:10]), int(data_iso[5:7]))


def parse_cardapio_ru(html: str, *, data: str, restaurante: int = 1) -> CardapioDia:
    """Extrai o cardápio do RU a partir do HTML de `ufc2012.ufc.br`."""
    soup = BeautifulSoup(html, "lxml")
    nome_rest = RESTAURANTES_UFC.get(restaurante, {}).get("nome", f"Restaurante {restaurante}")

    # Nunca atribuir ao dia pedido o cardápio de outro dia (a página cai no dia corrente
    # quando a data não é entendida).
    if not pagina_confere_com_data(html, data):
        return CardapioDia(
            data=data,
            restaurante_id=restaurante,
            restaurante_nome=nome_rest,
            tem_cardapio=False,
            refeicoes=[],
        )

    if soup.find(string=re.compile(r"N[aã]o h[aá] card[aá]pio cadastrado", re.IGNORECASE)):
        return CardapioDia(
            data=data,
            restaurante_id=restaurante,
            restaurante_nome=nome_rest,
            tem_cardapio=False,
            refeicoes=[],
        )

    refeicoes_extraidas: list[RefeicaoRu] = []
    encontrou_estrutura = False

    for r_id in ("desjejum", "almoco", "jantar"):
        h3 = soup.find("h3", id=r_id)
        table: Tag | None = None
        if isinstance(h3, Tag):
            encontrou_estrutura = True
            sib = h3.find_next_sibling("table", class_="refeicao")
            if isinstance(sib, Tag):
                table = sib
        if table is None:
            cand = soup.select_one(f"table.refeicao.{r_id}")
            if isinstance(cand, Tag):
                encontrou_estrutura = True
                table = cand

        if table is None:
            continue

        pratos: list[PratoRu] = []
        for tr in table.find_all("tr", class_="item"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            categoria = " ".join(tds[0].get_text(" ", strip=True).split()).lower()
            td_pratos = tds[1]
            texto_linha = td_pratos.get_text(" ", strip=True)
            spans = td_pratos.find_all("span", class_="desc")

            if not spans:
                desc_limpa = " ".join(texto_linha.split())
                if desc_limpa:
                    pratos.append(
                        PratoRu(
                            categoria=categoria,
                            descricao=desc_limpa,
                            contem_gluten=bool(re.search(r"cont[eé]m gl[uú]ten", texto_linha, re.I)),
                            contem_lactose=bool(re.search(r"cont[eé]m lactose", texto_linha, re.I)),
                        )
                    )
                continue

            prato_atual: PratoRu | None = None
            for sp in spans:
                classes_sp = [str(c).lower() for c in (sp.get("class") or [])]
                txt_sp = " ".join(sp.get_text(" ", strip=True).split())
                eh_gluten = "gluten" in classes_sp or bool(
                    re.search(r"cont[eé]m gl[uú]ten", txt_sp, re.I)
                )
                eh_lactose = "lactose" in classes_sp or bool(
                    re.search(r"cont[eé]m lactose", txt_sp, re.I)
                )
                if eh_gluten or eh_lactose:
                    if prato_atual is not None:
                        if eh_gluten:
                            prato_atual.contem_gluten = True
                        if eh_lactose:
                            prato_atual.contem_lactose = True
                    continue

                if txt_sp:
                    prato_atual = PratoRu(
                        categoria=categoria,
                        descricao=txt_sp.strip("() "),
                        contem_gluten=False,
                        contem_lactose=False,
                    )
                    pratos.append(prato_atual)

        if pratos:
            refeicoes_extraidas.append(RefeicaoRu(tipo=r_id, pratos=pratos))

    if not encontrou_estrutura:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            "Layout da página do Restaurante Universitário mudou (h3#almoco e mensagem de ausência não encontrados).",
        )

    return CardapioDia(
        data=data,
        restaurante_id=restaurante,
        restaurante_nome=nome_rest,
        tem_cardapio=len(refeicoes_extraidas) > 0,
        refeicoes=refeicoes_extraidas,
    )
