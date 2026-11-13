"""Parser puro da árvore de integralização e pré/co-requisitos (`dados_progresso_discente.jsf`)."""

from __future__ import annotations

import re
from typing import Literal

from bs4 import BeautifulSoup

from ufc_mcp.fontes.sigaa.modelos import ComponenteProgresso, ResultadoProgressoCurso
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.paginas import (
    REGEX_CODIGO_COMPONENTE,
    REGEX_ID_PROGRESSO,
    achar_tag,
    titulo_da_tela,
)


def parse_progresso_curso(html: str) -> ResultadoProgressoCurso:
    titulo = titulo_da_tela(html)
    soup = BeautifulSoup(html, "lxml")

    if "Progresso no Curso" not in titulo and soup.find("div", class_="descricaoComponente") is None:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            "Assinatura da tela 'Progresso no Curso' não encontrada.",
        )

    mapa_obrigatoria: dict[str, bool] = {}
    mapa_situacao: dict[str, Literal["cursado", "cursando", "a_cursar"]] = {}

    for id_svg, eh_obrig in (("progressoObrigatorias", True), ("progressoOptativas", False)):
        svg = achar_tag(soup, id=id_svg)
        if not svg:
            continue
        for el in svg.find_all(id=re.compile(r"_cc_(\d+)")):
            m_cc = re.search(r"_cc_(\d+)", str(el.get("id")))
            if not m_cc:
                continue
            id_cc = m_cc.group(1)
            mapa_obrigatoria[id_cc] = eh_obrig
            classes_acumuladas: set[str] = set()
            for c in el.get("class") or []:
                classes_acumuladas.add(str(c).lower())
            for rect in el.find_all(["rect", "g"]):
                for c in rect.get("class") or []:
                    classes_acumuladas.add(str(c).lower())
            if "cursado" in classes_acumuladas:
                mapa_situacao[id_cc] = "cursado"
            elif "cursando" in classes_acumuladas:
                mapa_situacao[id_cc] = "cursando"
            elif "a_cursar" in classes_acumuladas:
                mapa_situacao[id_cc] = "a_cursar"

    componentes: list[ComponenteProgresso] = []
    for div in soup.find_all("div", class_="descricaoComponente"):
        id_div = str(div.get("id") or "")
        m_id = REGEX_ID_PROGRESSO.match(id_div)
        if not m_id:
            continue
        periodo = int(m_id.group(1))
        id_comp = m_id.group(2)

        codigo = f"DISC{id_comp}"
        nome = codigo
        ch_h = 64
        pre_reqs: list[str] = []
        co_reqs: list[str] = []

        for p in div.find_all(["p", "div", "li"]):
            txt = " ".join(p.get_text(" ", strip=True).split())
            lower = txt.lower()
            if lower.startswith("componente:"):
                valor = txt.split(":", 1)[1].strip()
                m_c = REGEX_CODIGO_COMPONENTE.search(valor)
                if m_c:
                    codigo = m_c.group(1)
                    nome = re.sub(rf"^.*?{re.escape(codigo)}\s*-\s*", "", valor).strip() or codigo
            elif "carga hor" in lower:
                m_ch = re.search(r"(\d+)", txt)
                if m_ch:
                    ch_h = int(m_ch.group(1))
            elif "pré-requisito" in lower or "pre-requisito" in lower:
                pre_reqs = REGEX_CODIGO_COMPONENTE.findall(txt.split(":", 1)[-1])
            elif "co-requisito" in lower:
                co_reqs = REGEX_CODIGO_COMPONENTE.findall(txt.split(":", 1)[-1])

        situacao_attr = str(div.get("data-situacao") or "").lower()
        situacao: Literal["cursado", "cursando", "a_cursar"] = mapa_situacao.get(id_comp, "a_cursar")
        if situacao_attr in ("cursado", "cursando", "a_cursar"):
            situacao = situacao_attr  # type: ignore[assignment]

        obrigatoria = mapa_obrigatoria.get(id_comp, True)
        if str(div.get("data-obrigatoria") or "").lower() == "false":
            obrigatoria = False

        componentes.append(
            ComponenteProgresso(
                id_componente=id_comp,
                codigo=codigo,
                nome=nome,
                periodo_sugerido=periodo,
                carga_horaria_h=ch_h,
                obrigatoria=obrigatoria,
                situacao=situacao,
                pre_requisitos=list(dict.fromkeys(pre_reqs)),
                co_requisitos=list(dict.fromkeys(co_reqs)),
            )
        )

    if not componentes:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            "Nenhum componente `div.descricaoComponente` válido encontrado em Progresso no Curso.",
        )

    curso_el = soup.select_one(".nomeCurso, #conteudo h3")
    nome_curso = " ".join(curso_el.get_text(" ", strip=True).split()) if curso_el else "GRADUAÇÃO UFC"
    return ResultadoProgressoCurso(curso=nome_curso, componentes=componentes)
