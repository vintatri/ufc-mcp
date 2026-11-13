"""Parser puro e síncrono do Calendário Universitário da UFC (`ufc2012.ufc.br`)."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date

from bs4 import BeautifulSoup, Tag

from ufc_mcp.fontes.calendario.modelos import EventoCalendario, ResultadoCalendario
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc

MAPA_MESES: dict[str, int] = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

REGEX_CABECALHO_MES = re.compile(
    r"(?i)(janeiro|fevereiro|mar[çc]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+(\d{4})"
)
REGEX_MARCADORES = re.compile(r"\(([^)]+)\)")
REGEX_DIA_UNICO = re.compile(r"^(\d{1,2})$")
REGEX_DIA_INTERVALO = re.compile(r"^(\d{1,2})\s*(?:a|e|-)\s*(\d{1,2})$", re.IGNORECASE)
REGEX_FERIADO_RECESSO = re.compile(
    r"(?i)\b(feriado|recesso|ponto facultativo|sem expediente)\b"
)


def parse_calendario_ufc(html: str, *, ano_padrao: int = 2026) -> ResultadoCalendario:
    """Extrai todos os meses e eventos do Calendário Universitário da UFC."""
    soup = BeautifulSoup(html, "lxml")
    eventos: list[EventoCalendario] = []
    nao_interpretados = 0
    meses_encontrados = 0
    anos_vistos: list[int] = []

    for h3 in soup.find_all("h3"):
        txt_h3 = " ".join(h3.get_text(" ", strip=True).split())
        m_mes = REGEX_CABECALHO_MES.search(txt_h3)
        if not m_mes:
            continue
        meses_encontrados += 1
        nome_mes = m_mes.group(1).lower()
        ano_mes = int(m_mes.group(2))
        anos_vistos.append(ano_mes)
        num_mes = MAPA_MESES[nome_mes]

        tabela = h3.find_next_sibling("table", class_="category")
        if not isinstance(tabela, Tag):
            continue

        for tr in tabela.find_all("tr", class_="item"):
            celulas = tr.find_all("td", class_="cell")
            if len(celulas) < 2:
                celulas = tr.find_all("td")
            if len(celulas) < 2:
                continue

            bruto_dia = " ".join(celulas[0].get_text(" ", strip=True).split())
            descricao = " ".join(celulas[1].get_text(" ", strip=True).split())
            if not descricao:
                continue

            marcadores = [m.strip() for m in REGEX_MARCADORES.findall(bruto_dia) if m.strip()]
            limpo_dia = REGEX_MARCADORES.sub("", bruto_dia).strip()

            m_unico = REGEX_DIA_UNICO.match(limpo_dia)
            m_inter = REGEX_DIA_INTERVALO.match(limpo_dia)
            if m_unico:
                dia_ini = dia_fim = int(m_unico.group(1))
            elif m_inter:
                dia_ini = int(m_inter.group(1))
                dia_fim = int(m_inter.group(2))
            else:
                dia_ini = dia_fim = 1
                nao_interpretados += 1

            try:
                dt_ini = date(ano_mes, num_mes, dia_ini).isoformat()
                dt_fim = date(ano_mes, num_mes, max(dia_ini, dia_fim)).isoformat()
            except ValueError:
                dt_ini = f"{ano_mes:04d}-{num_mes:02d}-01"
                dt_fim = dt_ini
                nao_interpretados += 1

            eh_feriado = bool(REGEX_FERIADO_RECESSO.search(descricao))
            eventos.append(
                EventoCalendario(
                    inicio=dt_ini,
                    fim=dt_fim,
                    descricao=descricao,
                    marcadores=marcadores,
                    eh_feriado_ou_recesso=eh_feriado,
                )
            )

    if meses_encontrados == 0 or not eventos:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            "Layout do Calendário Universitário mudou (nenhum bloco h3 + table.category encontrado).",
        )

    if ano_padrao in anos_vistos:
        ano_detectado = ano_padrao
    else:
        contagem = Counter(anos_vistos)
        topo = max(contagem.values())
        ano_detectado = min(a for a, n in contagem.items() if n == topo)

    return ResultadoCalendario(
        ano=ano_detectado,
        eventos=eventos,
        nao_interpretados=nao_interpretados,
    )
