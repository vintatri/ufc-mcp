"""Parser puro do Portal do Discente (`discente.jsf`)."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ufc_mcp.fontes.sigaa.modelos import AtividadePortal, ResumoPortalDiscente, TurmaPortal
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.higiene import TextoExterno, externo
from ufc_mcp.nucleo.paginas import (
    REGEX_CODIGO_COMPONENTE,
    REGEX_VIGENCIA_TURMA,
    TipoPagina,
    achar_tag,
    identificar_pagina,
)
from ufc_mcp.servicos.horario import decodificar_horario_sigaa


def _ddmmaaaa_para_iso(s: str) -> str:
    d, m, a = s.strip().split("/")
    return f"{int(a):04d}-{int(m):02d}-{int(d):02d}"


def parse_portal_discente(
    html: str, *, identificadores: bool = False
) -> ResumoPortalDiscente:
    if identificar_pagina(html) != TipoPagina.PORTAL_DISCENTE:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            "A página fornecida não possui a assinatura estrutural do Portal do Discente.",
        )

    soup = BeautifulSoup(html, "lxml")
    nome: str | None = None
    matricula: str | None = None
    curso = "GRADUAÇÃO UFC"
    nivel = "GRADUAÇÃO"
    status = "ATIVO"
    entrada: str | None = None
    integralizacao: str | None = None

    bloco_perfil = (
        achar_tag(soup, id="agenda-docente") or achar_tag(soup, id="perfil-docente") or soup
    )
    for tr in bloco_perfil.find_all("tr"):
        # Layout real: linhas "<td>Chave:</td><td>valor</td>"; o layout antigo usava <th>.
        celulas = tr.find_all(["th", "td"], recursive=False)
        if len(celulas) < 2:
            continue
        th, td = celulas[0], celulas[1]
        chave = " ".join(th.get_text(" ", strip=True).split()).lower()
        val = " ".join(td.get_text(" ", strip=True).split())
        if "matr" in chave:
            matricula = val
        elif "nome" in chave or "discente" in chave:
            nome = val
        elif "curso" in chave:
            curso = val
        elif "nível" in chave or "nivel" in chave:
            nivel = val
        elif "status" in chave:
            status = val
        elif "entrada" in chave:
            entrada = val
        elif "integraliza" in chave:
            integralizacao = val
        elif "ch. total exigida" in chave:
            integralizacao = f"CH total exigida do currículo: {val} h"

    if nome is None:
        el_nome = soup.select_one("div.nome_usuario p")
        if el_nome is not None:
            nome = " ".join(el_nome.get_text(" ", strip=True).split()) or None

    if not identificadores:
        nome = None
        matricula = None

    turmas: list[TurmaPortal] = []
    bloco_turmas = achar_tag(soup, id="turmas-portal") or soup
    for tr in bloco_turmas.find_all("tr"):
        form = tr.find("form", attrs={"name": re.compile(r"^form_acessarTurmaVirtual")})
        if form is None:
            continue
        inp_turma = form.find("input", attrs={"name": "idTurma"})
        if inp_turma is None or not inp_turma.get("value"):
            continue
        id_turma = str(inp_turma["value"]).strip()

        tds = tr.find_all("td")
        texto_linha = " ".join(tr.get_text(" ", strip=True).split())
        m_cod = REGEX_CODIGO_COMPONENTE.search(texto_linha)
        codigo = m_cod.group(1) if m_cod else f"DISC{id_turma[-4:]}"

        nome_disc = texto_linha
        link_disc = form.find("a")
        if link_disc:
            txt_link = " ".join(link_disc.get_text(" ", strip=True).split())
            if txt_link:
                nome_disc = re.sub(rf"^{re.escape(codigo)}\s*-\s*", "", txt_link).strip()

        local = "Campus do Pici"
        horario_bruto = texto_linha
        if len(tds) >= 3:
            # Layout real do portal: [0]=disciplina, [1]=código da turma, [2]=local, [3]=horário.
            # Layout antigo (3 colunas): [1]=local, [2]=horário.
            i_local, i_hor = (2, 3) if len(tds) >= 4 else (1, 2)
            local_cand = " ".join(tds[i_local].get_text(" ", strip=True).split())
            hor_cand = " ".join(tds[i_hor].get_text(" ", strip=True).split())
            if local_cand:
                local = local_cand
            if hor_cand:
                horario_bruto = hor_cand

        horarios = decodificar_horario_sigaa(horario_bruto)
        ini_vig: str | None = None
        fim_vig: str | None = None
        m_vig = REGEX_VIGENCIA_TURMA.search(texto_linha)
        if m_vig:
            ini_vig = _ddmmaaaa_para_iso(m_vig.group(1))
            fim_vig = _ddmmaaaa_para_iso(m_vig.group(2))

        m_ch = re.search(r"(\d{2,3})\s*h\b", texto_linha, re.I)
        ch_h = int(m_ch.group(1)) if m_ch else 64

        turmas.append(
            TurmaPortal(
                id_turma=id_turma,
                codigo=codigo,
                nome=nome_disc,
                local=local,
                horario_bruto=horario_bruto,
                horarios=horarios,
                inicio_vigencia=ini_vig,
                fim_vigencia=fim_vig,
                carga_horaria_h=ch_h,
            )
        )

    noticias_portal: list[TextoExterno] = []
    bloco_not = achar_tag(soup, id="noticias-portal")
    if bloco_not:
        for item in bloco_not.find_all(["li", "p", "div"], recursive=True):
            txt = " ".join(item.get_text(" ", strip=True).split())
            if txt and len(txt) > 10:
                noticias_portal.append(externo(txt, origem="portal:noticia", max_chars=600))
                if len(noticias_portal) >= 10:
                    break

    atividades: list[AtividadePortal] = []
    bloco_ativ = achar_tag(soup, id="avaliacoes-portal") or achar_tag(soup, id="minhas-atividades")
    if bloco_ativ:
        for tr in bloco_ativ.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            dt_txt = " ".join(tds[0].get_text(" ", strip=True).split())
            m_dt = re.search(r"(\d{2}/\d{2}/\d{4})", dt_txt)
            dt_iso = _ddmmaaaa_para_iso(m_dt.group(1)) if m_dt else None
            turma_txt = " ".join(tds[1].get_text(" ", strip=True).split()) if len(tds) >= 3 else "Geral"
            desc_txt = " ".join(tds[-1].get_text(" ", strip=True).split())
            if desc_txt:
                atividades.append(
                    AtividadePortal(
                        data=dt_iso,
                        turma=turma_txt,
                        descricao=externo(desc_txt, origem="portal:atividade", max_chars=500),
                    )
                )

    return ResumoPortalDiscente(
        nome=nome,
        matricula=matricula,
        curso=curso,
        nivel=nivel,
        status=status,
        entrada=entrada,
        integralizacao=integralizacao,
        turmas=turmas,
        noticias_portal=noticias_portal,
        atividades_proximas=atividades,
    )
