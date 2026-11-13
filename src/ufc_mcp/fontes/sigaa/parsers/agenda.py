"""Parser puro da Agenda Consolidada de Turmas (`consulta_calendario_discente.jsf`)."""

from __future__ import annotations

from bs4 import BeautifulSoup

from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.paginas import achar_tag, titulo_da_tela


def parse_agenda_turmas(html: str) -> dict[str, object]:
    titulo = titulo_da_tela(html)
    soup = BeautifulSoup(html, "lxml")
    conteudo = achar_tag(soup, id="conteudo") or soup

    if "Agenda" not in titulo and "Calendário" not in titulo and "Horário" not in conteudo.get_text():
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            "Assinatura da tela Agenda de Turmas não encontrada.",
        )

    linhas_agenda: list[dict[str, str]] = []
    for tr in conteudo.select("table tr"):
        tds = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all("td")]
        tds = [c for c in tds if c]
        if len(tds) >= 2:
            linhas_agenda.append({"colunas": " | ".join(tds)})

    if not linhas_agenda:
        raise ErroUfc(CodigoErro.LAYOUT_MUDOU, "Tabela da Agenda de Turmas vazia ou ausente.")

    return {"titulo": titulo or "Agenda de Turmas", "itens": linhas_agenda}
