"""Parser puro de Pendências de Conclusão e Situação na Biblioteca (descarta identificação civil)."""

from __future__ import annotations

from bs4 import BeautifulSoup

from ufc_mcp.fontes.sigaa.modelos import ResultadoPendencias, SecaoPendencias
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.paginas import achar_tag, titulo_da_tela


def parse_pendencias_ou_biblioteca(html: str, *, assinatura_esperada: str) -> ResultadoPendencias:
    titulo = titulo_da_tela(html)
    soup = BeautifulSoup(html, "lxml")
    conteudo = achar_tag(soup, id="conteudo") or soup

    if assinatura_esperada.lower() not in titulo.lower() and assinatura_esperada.lower() not in conteudo.get_text(" ", strip=True).lower():
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            f"Assinatura '{assinatura_esperada}' não encontrada na página.",
        )

    secoes: list[SecaoPendencias] = []
    for table in conteudo.find_all("table"):
        ths_texto = " ".join(th.get_text(" ", strip=True) for th in table.find_all("th")).lower()
        if "matrícula:" in ths_texto or "discente:" in ths_texto or "cpf:" in ths_texto:
            continue

        cap = table.find("caption") or table.find("td", class_="subFormulario")
        titulo_sec = (
            " ".join(cap.get_text(" ", strip=True).split())
            if cap
            else assinatura_esperada.upper()
        )
        itens: list[dict[str, str]] = []
        for tr in table.find_all("tr"):
            if "subFormulario" in (tr.get("class") or []):
                continue
            celulas = [
                " ".join(c.get_text(" ", strip=True).split())
                for c in tr.find_all(["th", "td"])
                if "subFormulario" not in (c.get("class") or [])
            ]
            celulas = [c for c in celulas if c]
            if len(celulas) == 2:
                if any(p in celulas[0].lower() for p in ("matrícula", "discente", "cpf")):
                    continue
                itens.append({"campo": celulas[0].rstrip(":"), "valor": celulas[1]})
            elif len(celulas) > 2:
                itens.append({"linha": " | ".join(celulas)})

        if itens:
            secoes.append(SecaoPendencias(titulo=titulo_sec, itens=itens))

    if not secoes:
        # Sem tabelas de dados: o SIGAA mostra só mensagens ("Não foram encontrados débitos."),
        # o que é um resultado válido (sem pendências), não mudança de layout.
        texto = " ".join(conteudo.get_text(" ", strip=True).split())
        inicio = texto.find("Relatório de")
        if inicio >= 0:
            fim = texto.find("Copyright", inicio)
            trecho = texto[inicio : fim if fim > 0 else None].strip()
            trecho = trecho.rsplit(" Portal do Discente", 1)[0][:1500]
            secoes.append(
                SecaoPendencias(titulo=assinatura_esperada.upper(), itens=[{"linha": trecho}])
            )

    if not secoes:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            f"Nenhuma seção de dados encontrada para '{assinatura_esperada}'.",
        )
    return ResultadoPendencias(titulo_tela=titulo or assinatura_esperada, secoes=secoes)
