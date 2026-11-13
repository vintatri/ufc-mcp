"""Parser puro de turmas ofertadas no semestre (`turmas.jsf` público e `busca_turma.jsf`)."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ufc_mcp.fontes.sigaa.modelos import TurmaOfertada
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.paginas import REGEX_CODIGO_COMPONENTE
from ufc_mcp.servicos.horario import decodificar_horario_sigaa


def _texto_normalizado(elemento: object) -> str:
    return " ".join(str(elemento.get_text(" ", strip=True)).split())  # type: ignore[attr-defined]


def _nome_componente(texto: str, codigo: str) -> str:
    # O contrato do projeto usa o rótulo completo (código + nome) em `nome_componente`.
    return re.sub(r"\s*-\s*\d+\s*h\s*$", "", texto).strip()


def _parse_layout_publico(
    soup: BeautifulSoup, *, codigo_filtro: str | None = None
) -> list[TurmaOfertada]:
    """Layout atual do portal público: uma tabela `listagem` por componente curricular."""
    ofertas: list[TurmaOfertada] = []
    comp_cod = ""
    comp_nome = ""

    for tabela in soup.select("table.listagem"):
        cabecalho = tabela.find("td", class_="subListagem")
        if cabecalho is None:
            continue
        texto_cab = _texto_normalizado(cabecalho)
        m_cod = REGEX_CODIGO_COMPONENTE.search(texto_cab)
        if m_cod:
            comp_cod = m_cod.group(1)
            comp_nome = _nome_componente(texto_cab, comp_cod)
        if not comp_cod:
            continue

        for tr in tabela.select("tr.linhaPar, tr.linhaImpar"):
            tds = tr.find_all("td", recursive=False)
            if len(tds) < 5:
                continue
            classes = [str(c) for c in (tds[0].get("class") or [])]
            if "anoPeriodo" not in classes:
                continue

            cod_turma = _texto_normalizado(tds[1]) or "01"
            docente = _texto_normalizado(tds[2]) or "DOCENTE NÃO INFORMADO"
            vagas_txt = _texto_normalizado(tds[3])
            horario_bruto = _texto_normalizado(tds[4])
            local = _texto_normalizado(tds[5]) if len(tds) > 5 else ""

            if codigo_filtro and comp_cod.upper() != codigo_filtro.strip().upper():
                continue

            m_vagas = re.search(r"(\d+)", vagas_txt)
            vagas = int(m_vagas.group(1)) if m_vagas else 40
            horarios = decodificar_horario_sigaa(horario_bruto)
            if not horarios:
                continue

            ofertas.append(
                TurmaOfertada(
                    codigo_componente=comp_cod,
                    nome_componente=comp_nome or comp_cod,
                    codigo_turma=cod_turma,
                    docente=docente,
                    horario_bruto=horario_bruto,
                    horarios=horarios,
                    local=local or "Não informado no portal público",
                    capacidade_vagas=vagas,
                    carga_horaria_h=64,
                )
            )
    return ofertas


def _parse_layout_legado(
    soup: BeautifulSoup, *, codigo_filtro: str | None = None
) -> list[TurmaOfertada]:
    """Layout compacto usado no corpus sintético e no `busca_turma.jsf` autenticado."""
    ofertas: list[TurmaOfertada] = []
    comp_atual_cod = ""
    comp_atual_nome = ""
    comp_atual_ch = 64

    for tr in soup.select("table.listagem tr, tr.agrupador"):
        classes = [str(c) for c in (tr.get("class") or [])]
        texto_tr = " ".join(tr.get_text(" ", strip=True).split())

        if "agrupador" in classes or tr.find("td", class_="agrupador"):
            m_cod = REGEX_CODIGO_COMPONENTE.search(texto_tr)
            if m_cod:
                comp_atual_cod = m_cod.group(1)
                resto = re.sub(rf"^.*?{re.escape(comp_atual_cod)}\s*-\s*", "", texto_tr)
                m_ch = re.search(r"(\d{2,3})\s*h\b", resto, re.I)
                comp_atual_ch = int(m_ch.group(1)) if m_ch else 64
                comp_atual_nome = re.sub(r"\s*-\s*\d+\s*h.*$", "", texto_tr, flags=re.I).strip()
            continue

        tds = tr.find_all("td")
        if len(tds) < 4:
            continue

        cod_cand = comp_atual_cod
        nome_cand = comp_atual_nome
        m_inline = REGEX_CODIGO_COMPONENTE.search(
            " ".join(tds[0].get_text(" ", strip=True).split())
        )
        if m_inline:
            cod_cand = m_inline.group(1)
            nome_cand = " ".join(tds[1].get_text(" ", strip=True).split())
            cod_turma = " ".join(tds[2].get_text(" ", strip=True).split()) or "01"
            docente = " ".join(tds[3].get_text(" ", strip=True).split()) or "DOCENTE EXEMPLO"
            horario_bruto = (
                " ".join(tds[4].get_text(" ", strip=True).split())
                if len(tds) > 4
                else texto_tr
            )
            local = (
                " ".join(tds[5].get_text(" ", strip=True).split())
                if len(tds) > 5
                else "CT - Bloco 710"
            )
            vagas_txt = (
                " ".join(tds[6].get_text(" ", strip=True).split())
                if len(tds) > 6
                else "40"
            )
        else:
            if not cod_cand:
                continue
            cod_turma = " ".join(tds[0].get_text(" ", strip=True).split()) or "01"
            docente = " ".join(tds[1].get_text(" ", strip=True).split()) or "DOCENTE EXEMPLO"
            horario_bruto = " ".join(tds[2].get_text(" ", strip=True).split())
            local = " ".join(tds[3].get_text(" ", strip=True).split())
            vagas_txt = (
                " ".join(tds[4].get_text(" ", strip=True).split()) if len(tds) > 4 else "40"
            )

        if codigo_filtro and cod_cand.upper() != codigo_filtro.strip().upper():
            continue

        m_vagas = re.search(r"(\d+)", vagas_txt)
        vagas = int(m_vagas.group(1)) if m_vagas else 40
        horarios = decodificar_horario_sigaa(horario_bruto)
        if not horarios:
            continue

        ofertas.append(
            TurmaOfertada(
                codigo_componente=cod_cand,
                nome_componente=nome_cand or cod_cand,
                codigo_turma=cod_turma,
                docente=docente,
                horario_bruto=horario_bruto,
                horarios=horarios,
                local=local or "CT - Bloco 710",
                capacidade_vagas=vagas,
                carga_horaria_h=comp_atual_ch,
            )
        )
    return ofertas


def parse_ofertas_turmas(html: str, *, codigo_filtro: str | None = None) -> list[TurmaOfertada]:
    soup = BeautifulSoup(html, "lxml")
    ofertas = _parse_layout_publico(soup, codigo_filtro=codigo_filtro)
    if not ofertas:
        ofertas = _parse_layout_legado(soup, codigo_filtro=codigo_filtro)

    if not ofertas and soup.find("input", id="form:inputAno") is not None:
        raise ErroUfc(
            CodigoErro.FONTE_INDISPONIVEL,
            "A página recebida é apenas o formulário de busca de turmas (ano/período), sem "
            "listagem. O formulário precisa ser enviado via POST; se ele já foi enviado, "
            "verifique se existem turmas para o ano/período e o curso informados.",
        )
    if not ofertas and not codigo_filtro:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            "Layout da tela de oferta de turmas mudou (nenhuma turma com horário válido encontrada).",
        )
    return ofertas
