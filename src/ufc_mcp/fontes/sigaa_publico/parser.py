"""Parser puro das páginas públicas do SIGAA (`calendario.jsf`, `curriculo.jsf`)."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ufc_mcp.fontes.sigaa_publico.modelos import (
    CalendarioCursoPublico,
    ComponenteCurriculoPublico,
    PeriodoCalendarioCurso,
)
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.paginas import REGEX_CODIGO_COMPONENTE

REGEX_LINHA_CALENDARIO_CURSO = re.compile(
    r"(\d{4}\.\d)\s+(\d{2}/\d{2}/\d{4})\s+(?:a|à|-)\s+(\d{2}/\d{2}/\d{4})\s*[-→]+\s*(.+)"
)


def _ddmmaaaa_para_iso(s: str) -> str:
    d, m, a = s.strip().split("/")
    return f"{int(a):04d}-{int(m):02d}-{int(d):02d}"


REGEX_DATAS_CALENDARIO = re.compile(
    r"(\d{2}/\d{2}/\d{4})(?:\s*(?:a|à|-)\s*(\d{2}/\d{2}/\d{4}))?"
)
REGEX_SEMESTRE = re.compile(r"^\d{4}\.\d$")


def _limpar(el) -> str:  # type: ignore[no-untyped-def]
    return " ".join(el.get_text(" ", strip=True).split())


def _nome_curso(soup: BeautifulSoup, id_curso: int) -> str:
    """Nome do curso: primeiro `<h1>` do cabeçalho (o `<h1 class="calendario">` é o título da seção)."""
    for h1 in soup.find_all("h1"):
        if "calendario" in (h1.get("class") or []):
            continue
        txt = _limpar(h1)
        if txt and not txt.upper().startswith("SIGAA"):
            return txt
    titulo_el = soup.select_one(".tituloCurso, caption")
    return _limpar(titulo_el) if titulo_el else f"Curso {id_curso}"


def parse_calendario_curso_publico(html: str, *, id_curso: int) -> CalendarioCursoPublico:
    """Layout real: `table.listagem` por período; `td.subListagem` = semestre; cada `tr` com `<b>datas</b>` + `→ evento`.

    Mantém suporte à forma linear antiga (`2026.1 dd/mm/aaaa a dd/mm/aaaa - evento`).
    """
    soup = BeautifulSoup(html, "lxml")
    nome_curso = _nome_curso(soup, id_curso)

    periodos: list[PeriodoCalendarioCurso] = []
    for tabela in soup.select("table.listagem"):
        sub = tabela.select_one("td.subListagem")
        semestre = _limpar(sub) if sub else ""
        if not REGEX_SEMESTRE.match(semestre):
            continue
        for td in tabela.find_all("td"):
            if "subListagem" in (td.get("class") or []):
                continue
            negrito = td.find("b")
            if negrito is None:
                continue
            m = REGEX_DATAS_CALENDARIO.search(_limpar(negrito))
            if not m:
                continue
            evento = _limpar(td).replace(_limpar(negrito), "", 1).strip()
            evento = re.sub(r"^[\s→\u2192&-]+", "", evento).strip()
            if not evento:
                continue
            inicio = _ddmmaaaa_para_iso(m.group(1))
            fim = _ddmmaaaa_para_iso(m.group(2)) if m.group(2) else inicio
            periodos.append(
                PeriodoCalendarioCurso(semestre=semestre, inicio=inicio, fim=fim, evento=evento)
            )

    if not periodos:
        for tr in soup.find_all(["tr", "li", "p"]):
            linha = " ".join(tr.get_text(" ", strip=True).split())
            m = REGEX_LINHA_CALENDARIO_CURSO.search(linha)
            if m:
                periodos.append(
                    PeriodoCalendarioCurso(
                        semestre=m.group(1),
                        inicio=_ddmmaaaa_para_iso(m.group(2)),
                        fim=_ddmmaaaa_para_iso(m.group(3)),
                        evento=m.group(4).strip(),
                    )
                )

    if not periodos and _sem_dados_calendario(soup):
        raise ErroUfc(
            CodigoErro.NAO_ENCONTRADO,
            f"O curso público id={id_curso} respondeu, mas não publica calendário (página sem períodos). "
            "Confira o id do seu curso e configure `UFC_MCP_ID_CURSO_PUBLICO` "
            "(ou `curso` no config.toml), ou passe `id_curso` na chamada.",
            detalhes={"id_curso": id_curso},
        )

    if not periodos:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            "Layout do calendário público do curso no SIGAA mudou (nenhum período encontrado).",
        )

    return CalendarioCursoPublico(id_curso=id_curso, curso=nome_curso, periodos=periodos)


def _sem_dados_calendario(soup: BeautifulSoup) -> bool:
    """True se a página tem o contêiner de calendário do portal público mas nenhuma tabela de período."""
    return soup.find(id="calendario") is not None and not soup.select("table.listagem td.subListagem")


def parse_curriculo_publico(html: str) -> list[ComponenteCurriculoPublico]:
    """Extrai componentes curriculares de `curriculo.jsf` no portal público do SIGAA."""
    soup = BeautifulSoup(html, "lxml")
    componentes: list[ComponenteCurriculoPublico] = []

    for tr in soup.select("table.listagem tr, table.subFormulario tr, tr.linhaPar, tr.linhaImpar"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        txt_cod = " ".join(tds[0].get_text(" ", strip=True).split())
        m_cod = REGEX_CODIGO_COMPONENTE.search(txt_cod)
        if not m_cod:
            continue
        codigo = m_cod.group(1)
        nome = " ".join(tds[1].get_text(" ", strip=True).split())
        txt_ch = " ".join(tds[2].get_text(" ", strip=True).split())
        m_ch = re.search(r"(\d+)", txt_ch)
        ch = int(m_ch.group(1)) if m_ch else 64
        periodo_bruto = tr.get("data-periodo")
        periodo = int(periodo_bruto) if isinstance(periodo_bruto, str) else 1
        obrigatoria = "optativa" not in tr.get_text(" ", strip=True).lower()
        pre_reqs = REGEX_CODIGO_COMPONENTE.findall(tds[3].get_text(" ", strip=True)) if len(tds) > 3 else []
        co_reqs = REGEX_CODIGO_COMPONENTE.findall(tds[4].get_text(" ", strip=True)) if len(tds) > 4 else []
        componentes.append(
            ComponenteCurriculoPublico(
                codigo=codigo,
                nome=nome,
                carga_horaria_h=ch,
                periodo_sugerido=periodo,
                obrigatoria=obrigatoria,
                pre_requisitos=pre_reqs,
                co_requisitos=co_reqs,
            )
        )

    if not componentes:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            "Layout da estrutura curricular pública mudou (nenhum componente encontrado).",
        )
    return componentes
