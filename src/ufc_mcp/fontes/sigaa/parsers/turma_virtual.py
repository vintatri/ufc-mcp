"""
Parsers resilientes em dois níveis das 7 telas da Turma Virtual (AVA):
Principal (`turma`), Ver Notas (`notas`), Frequência (`frequencia`),
Avaliações (`avaliacoes`), Tarefas (`tarefas`), Notícias (`avisos`) e
Plano de Curso (`plano`).
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ufc_mcp.fontes.sigaa.modelos import (
    AvaliacaoNota,
    AvaliacoesTurma,
    FrequenciaTurma,
    ItemAvaliacaoAgendada,
    ItemCronogramaPlano,
    ItemNoticiaTurma,
    ItemTarefaTurma,
    MaterialAula,
    NotasTurma,
    NoticiasTurma,
    PlanoCursoTurma,
    RegistroFrequenciaDia,
    TarefasTurma,
    TopicoAulaTurma,
    VisaoGeralTurma,
)
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.higiene import TextoExterno, externo
from ufc_mcp.nucleo.paginas import achar_tag


def _extrair_nome_turma(soup: BeautifulSoup, id_turma: str) -> str:
    for sel in ("#nomeTurma", ".nomeTurma", "#cabecalho-turma h3", "h2", "h3"):
        el = soup.select_one(sel)
        if el:
            txt = " ".join(el.get_text(" ", strip=True).split())
            if txt and len(txt) > 3:
                return txt
    return f"Turma {id_turma}"


def _normalizar_data_texto(s: str) -> str | None:
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m_iso = re.search(r"(\d{4}-\d{2}-\d{2})", s)
    if m_iso:
        return m_iso.group(1)
    return None


def parse_turma_visao_geral(html: str, *, id_turma: str) -> VisaoGeralTurma:
    soup = BeautifulSoup(html, "lxml")
    nome_turma = _extrair_nome_turma(soup, id_turma)
    conteudo = soup.select_one("#conteudo, #ava-conteudo") or soup

    blocos = conteudo.select("div.topico-aula, div[id^='topico']")
    if not blocos:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            "Layout da página Principal da Turma Virtual mudou (nenhum bloco de tópico de aula encontrado).",
        )

    topicos: list[TopicoAulaTurma] = []
    contador_mat = 0

    for bloco in blocos[:60]:
        cab = bloco.find(["h3", "h4", "span", "strong"], class_=re.compile(r"titulo|cabecalho", re.I)) or bloco.find(["h3", "h4"])
        titulo_bruto = (
            " ".join(cab.get_text(" ", strip=True).split())
            if cab
            else " ".join(bloco.get_text(" ", strip=True).split())[:120]
        )
        data_iso = _normalizar_data_texto(titulo_bruto)
        desc_el = bloco.find("div", class_=re.compile(r"descricao|conteudo", re.I)) or bloco.find("p")
        resumo_ext: TextoExterno | None = None
        if desc_el:
            txt_d = " ".join(desc_el.get_text(" ", strip=True).split())
            if txt_d:
                resumo_ext = externo(txt_d, origem=f"turma:{id_turma}:topico_resumo", max_chars=1000)

        materiais: list[MaterialAula] = []
        for a in bloco.find_all("a", onclick=True):
            onclick = str(a.get("onclick") or "")
            if "jsfcljs" not in onclick:
                continue
            txt_mat = " ".join(a.get_text(" ", strip=True).split())
            if not txt_mat:
                continue
            contador_mat += 1
            id_mat = f"mat_{contador_mat:02d}"
            materiais.append(
                MaterialAula(
                    id_material=id_mat,
                    titulo=externo(txt_mat, origem=f"turma:{id_turma}:material", max_chars=300),
                )
            )

        topicos.append(
            TopicoAulaTurma(
                data=data_iso,
                titulo=externo(titulo_bruto, origem=f"turma:{id_turma}:topico", max_chars=400),
                resumo=resumo_ext,
                materiais=materiais,
            )
        )

    return VisaoGeralTurma(id_turma=id_turma, turma=nome_turma, topicos=topicos)


def _para_float_nota(txt: str) -> float | None:
    limpo = txt.strip().replace(",", ".")
    if not limpo or limpo in ("-", "--", "S/N"):
        return None
    try:
        return round(float(limpo), 2)
    except ValueError:
        return None


def parse_turma_notas(html: str, *, id_turma: str) -> NotasTurma:
    soup = BeautifulSoup(html, "lxml")
    nome_turma = _extrair_nome_turma(soup, id_turma)
    conteudo = soup.select_one("#conteudo, #ava-conteudo") or soup

    tabela = (
        conteudo.select_one("table.tabelaRelatorio")
        or conteudo.select_one("table.listagem")
        or achar_tag(conteudo, "table")
    )
    if tabela is None:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            "Tabela de notas não encontrada na Turma Virtual.",
        )

    ths = [" ".join(th.get_text(" ", strip=True).split()) for th in tabela.find_all("th")]
    trs_dados = [tr for tr in tabela.find_all("tr") if tr.find_all("td")]
    if not ths or not trs_dados:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            "Tabela de notas sem cabeçalhos ou sem linha de dados.",
        )

    tds = [" ".join(td.get_text(" ", strip=True).split()) for td in trs_dados[0].find_all("td")]
    avaliacoes: list[AvaliacaoNota] = []
    media_parcial: float | None = None
    faltas: int | None = None
    situacao: str | None = None

    for idx, nome_col in enumerate(ths):
        if idx >= len(tds):
            break
        val_str = tds[idx]
        col_up = nome_col.upper()
        if any(col_up.startswith(pref) for pref in ("UNID", "AVAL", "NOTA", "N1", "N2", "N3", "AP")):
            avaliacoes.append(AvaliacaoNota(nome=nome_col, nota=_para_float_nota(val_str)))
        elif any(k in col_up for k in ("MÉDIA", "MEDIA", "RESULTADO")):
            media_parcial = _para_float_nota(val_str)
        elif "FALTA" in col_up:
            m_f = re.search(r"(\d+)", val_str)
            faltas = int(m_f.group(1)) if m_f else 0
        elif "SITUA" in col_up or "STATUS" in col_up:
            situacao = val_str or None

    return NotasTurma(
        id_turma=id_turma,
        turma=nome_turma,
        avaliacoes=avaliacoes,
        media_parcial=media_parcial,
        faltas=faltas,
        situacao=situacao,
    )


def parse_turma_frequencia(html: str, *, id_turma: str) -> FrequenciaTurma:
    soup = BeautifulSoup(html, "lxml")
    nome_turma = _extrair_nome_turma(soup, id_turma)
    conteudo = soup.select_one("#conteudo, #ava-conteudo") or soup

    tabela = conteudo.select_one("table.listagem, table.tabelaRelatorio") or achar_tag(conteudo, "table")
    if tabela is None:
        raise ErroUfc(CodigoErro.LAYOUT_MUDOU, "Tabela de frequência não encontrada.")

    registros: list[RegistroFrequenciaDia] = []
    soma_faltas = 0

    for tr in tabela.find_all("tr"):
        tds = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all("td")]
        if len(tds) < 2:
            continue
        dt_iso = _normalizar_data_texto(tds[0])
        if not dt_iso:
            continue
        sit = tds[1]
        faltas_dia = 0
        m_num = re.search(r"(\d+)\s*falta", sit, re.I)
        if m_num:
            faltas_dia = int(m_num.group(1))
        elif re.search(r"\b(falta|ausente|f)\b", sit, re.I):
            faltas_dia = 2
        soma_faltas += faltas_dia
        registros.append(
            RegistroFrequenciaDia(data=dt_iso, situacao=sit, faltas_no_dia=faltas_dia)
        )

    m_resumo = re.search(r"Total de Faltas\s*:\s*(\d+)", conteudo.get_text(" ", strip=True), re.I)
    if m_resumo:
        soma_faltas = int(m_resumo.group(1))

    return FrequenciaTurma(
        id_turma=id_turma,
        turma=nome_turma,
        total_faltas_horas=soma_faltas,
        registros=registros,
    )


def parse_turma_avaliacoes(html: str, *, id_turma: str) -> AvaliacoesTurma:
    soup = BeautifulSoup(html, "lxml")
    nome_turma = _extrair_nome_turma(soup, id_turma)
    conteudo = soup.select_one("#conteudo, #ava-conteudo") or soup

    texto_pagina = soup.get_text(" ", strip=True)
    if re.search(r"Nenhuma avalia[cç][aã]o cadastrada", texto_pagina, re.I) and not re.search(
        r"Datas de Avalia[cç][oõ]es\s+\d", texto_pagina, re.I
    ):
        return AvaliacoesTurma(id_turma=id_turma, turma=nome_turma, avaliacoes=[])

    tabela = conteudo.select_one("table.listagem, table.tabelaRelatorio") or achar_tag(conteudo, "table")
    if tabela is None:
        raise ErroUfc(CodigoErro.LAYOUT_MUDOU, "Tabela de avaliações não encontrada.")

    itens: list[ItemAvaliacaoAgendada] = []
    for tr in tabela.find_all("tr"):
        tds = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all("td")]
        if len(tds) < 2:
            continue
        dt_iso = _normalizar_data_texto(tds[0]) or tds[0]
        hora = tds[1] if len(tds) >= 3 else None
        desc = tds[-1]
        itens.append(
            ItemAvaliacaoAgendada(
                data=dt_iso,
                hora=hora,
                descricao=externo(desc, origem=f"turma:{id_turma}:avaliacao", max_chars=400),
            )
        )

    return AvaliacoesTurma(id_turma=id_turma, turma=nome_turma, avaliacoes=itens)


def parse_turma_tarefas(html: str, *, id_turma: str) -> TarefasTurma:
    soup = BeautifulSoup(html, "lxml")
    nome_turma = _extrair_nome_turma(soup, id_turma)
    conteudo = soup.select_one("#conteudo, #ava-conteudo") or soup

    if re.search(r"Nenhuma tarefa cadastrada", conteudo.get_text(" ", strip=True), re.I):
        return TarefasTurma(id_turma=id_turma, turma=nome_turma, tarefas=[])

    tabela = conteudo.select_one("table.listagem, table.tabelaRelatorio") or achar_tag(conteudo, "table")
    if tabela is None:
        raise ErroUfc(CodigoErro.LAYOUT_MUDOU, "Tabela de tarefas não encontrada.")

    tarefas: list[ItemTarefaTurma] = []
    for tr in tabela.find_all("tr"):
        tds = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all("td")]
        if len(tds) < 2:
            continue
        titulo_bruto = tds[0]
        desc_bruta = tds[1] if len(tds) >= 3 else tds[0]
        ini_iso: str | None = None
        fim_iso: str | None = None
        enviada: bool | None = None

        texto_tr = " | ".join(tds)
        datas_achadas = re.findall(
            r"(\d{2}/\d{2}/\d{4}(?:\s+(?:às\s+)?\d{2}[:h]\d{2})?|\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2})?)",
            texto_tr,
        )
        if len(datas_achadas) >= 2:
            ini_iso = _normalizar_data_hora_iso(datas_achadas[0])
            fim_iso = _normalizar_data_hora_iso(datas_achadas[1])
        elif len(datas_achadas) == 1:
            fim_iso = _normalizar_data_hora_iso(datas_achadas[0])

        if re.search(r"\b(n[aã]o\s+enviada|n[aã]o\s+submetida|pendente)\b", texto_tr, re.I):
            enviada = False
        elif re.search(r"\b(enviada|submetida|entregue)\b", texto_tr, re.I):
            enviada = True

        tarefas.append(
            ItemTarefaTurma(
                titulo=externo(titulo_bruto, origem=f"turma:{id_turma}:tarefa_titulo", max_chars=300),
                descricao=externo(desc_bruta, origem=f"turma:{id_turma}:tarefa_desc", max_chars=1000),
                inicio_entrega=ini_iso,
                fim_entrega=fim_iso,
                enviada=enviada,
            )
        )

    return TarefasTurma(id_turma=id_turma, turma=nome_turma, tarefas=tarefas)


def _normalizar_data_hora_iso(s: str) -> str:
    s_limpo = s.strip()
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})(?:\s+(?:às\s+)?(\d{2})[:h](\d{2}))?", s_limpo)
    if m:
        hora = f"{m.group(4)}:{m.group(5)}" if m.group(4) else "23:59"
        return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}T{hora}:00"
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s_limpo):
        return f"{s_limpo}T23:59:00"
    return s_limpo


def parse_turma_noticias(html: str, *, id_turma: str) -> NoticiasTurma:
    soup = BeautifulSoup(html, "lxml")
    nome_turma = _extrair_nome_turma(soup, id_turma)
    conteudo = soup.select_one("#conteudo, #ava-conteudo") or soup

    if re.search(r"Nenhuma not[ií]cia cadastrada", conteudo.get_text(" ", strip=True), re.I):
        return NoticiasTurma(id_turma=id_turma, turma=nome_turma, noticias=[])

    blocos = conteudo.select("div.noticia, table.listagem tr.noticia, div.item-noticia, table.listagem tbody tr")
    if not blocos:
        # Layout real: painel "Notícias" da página Principal, com pares "dd/mm/aaaa hh:mm <br> <i>título</i>".
        pares = re.findall(
            r"(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})\s*<br\s*/?>\s*<i>(.*?)</i>", str(soup), re.S | re.I
        )
        if pares:
            noticias_painel: list[ItemNoticiaTurma] = []
            for data_txt, titulo_html in pares[:20]:
                titulo = " ".join(BeautifulSoup(titulo_html, "lxml").get_text(" ", strip=True).split())
                if not titulo:
                    continue
                noticias_painel.append(
                    ItemNoticiaTurma(
                        titulo=externo(titulo, origem=f"turma:{id_turma}:noticia_titulo", max_chars=300),
                        corpo=externo(titulo, origem=f"turma:{id_turma}:noticia_corpo", max_chars=1500),
                        publicada_em=_normalizar_data_texto(data_txt),
                    )
                )
            return NoticiasTurma(id_turma=id_turma, turma=nome_turma, noticias=noticias_painel)
        raise ErroUfc(CodigoErro.LAYOUT_MUDOU, "Estrutura de notícias da Turma Virtual não encontrada.")

    noticias: list[ItemNoticiaTurma] = []
    for b in blocos[:20]:
        tds = b.find_all("td")
        if len(tds) >= 2:
            dt_iso = _normalizar_data_texto(tds[0].get_text(" ", strip=True))
            tit = " ".join(tds[1].get_text(" ", strip=True).split())
            corpo = " ".join(tds[-1].get_text(" ", strip=True).split())
        else:
            cab = b.find(["h3", "h4", "strong", "span"])
            tit = " ".join(cab.get_text(" ", strip=True).split()) if cab else "Aviso da Turma"
            corpo = " ".join(b.get_text(" ", strip=True).split())
            dt_iso = _normalizar_data_texto(corpo)

        if not corpo:
            continue
        noticias.append(
            ItemNoticiaTurma(
                titulo=externo(tit, origem=f"turma:{id_turma}:noticia_titulo", max_chars=300),
                corpo=externo(corpo, origem=f"turma:{id_turma}:noticia_corpo", max_chars=1500),
                publicada_em=dt_iso,
            )
        )

    return NoticiasTurma(id_turma=id_turma, turma=nome_turma, noticias=noticias)


def parse_turma_plano_curso(html: str, *, id_turma: str) -> PlanoCursoTurma:
    soup = BeautifulSoup(html, "lxml")
    nome_turma = _extrair_nome_turma(soup, id_turma)
    conteudo = soup.select_one("#conteudo, #ava-conteudo") or soup

    met_el = conteudo.find(id="metodologia") or conteudo.find(attrs={"data-secao": "metodologia"})
    aval_el = conteudo.find(id="procedimentos-avaliacao") or conteudo.find(attrs={"data-secao": "avaliacao"})

    met_txt = " ".join(met_el.get_text(" ", strip=True).split()) if met_el else ""
    aval_txt = " ".join(aval_el.get_text(" ", strip=True).split()) if aval_el else ""

    if not met_txt or not aval_txt:
        for tr in conteudo.find_all("tr"):
            th = tr.find("th")
            td = tr.find("td")
            if not th or not td:
                continue
            rot = th.get_text(" ", strip=True).lower()
            val = " ".join(td.get_text(" ", strip=True).split())
            if "metodologia" in rot and not met_txt:
                met_txt = val
            elif "avalia" in rot and not aval_txt:
                aval_txt = val

    cronograma: list[ItemCronogramaPlano] = []
    tab_cron = achar_tag(conteudo, "table", id="tabela-cronograma") or conteudo.select_one("table.cronograma, table.listagem")
    if tab_cron:
        for tr in tab_cron.find_all("tr"):
            tds = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all("td")]
            if len(tds) >= 2:
                dt_iso = _normalizar_data_texto(tds[0])
                topico_txt = tds[1]
                if topico_txt:
                    cronograma.append(
                        ItemCronogramaPlano(
                            data=dt_iso,
                            topico=externo(topico_txt, origem=f"plano_curso:{id_turma}:cronograma", max_chars=500),
                        )
                    )

    referencias: list[TextoExterno] = []
    bloco_ref = achar_tag(conteudo, id="referencias") or achar_tag(conteudo, "ul", class_="referencias")
    if bloco_ref:
        for li in bloco_ref.find_all(["li", "tr", "p"]):
            txt_r = " ".join(li.get_text(" ", strip=True).split())
            if txt_r:
                referencias.append(externo(txt_r, origem=f"plano_curso:{id_turma}:referencias", max_chars=500))

    if not met_txt and not cronograma and not referencias:
        if re.search(r"n[aã]o possui um programa cadastrado", soup.get_text(" ", strip=True), re.I):
            # Resultado válido: o professor não publicou o programa desta turma.
            return PlanoCursoTurma(
                id_turma=id_turma,
                turma=nome_turma,
                metodologia=externo("Programa não cadastrado no SIGAA.", origem="plano_curso:metodologia"),
                procedimentos_avaliacao=externo(
                    "Programa não cadastrado no SIGAA.", origem="plano_curso:avaliacao"
                ),
            )
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            "Layout do Plano de Curso da Turma Virtual mudou (nenhuma seção encontrada).",
        )

    return PlanoCursoTurma(
        id_turma=id_turma,
        turma=nome_turma,
        metodologia=externo(met_txt or "Não informado no SIGAA.", origem="plano_curso:metodologia"),
        procedimentos_avaliacao=externo(
            aval_txt or "Não informado no SIGAA.",
            origem="plano_curso:avaliacao",
        ),
        cronograma_aulas=cronograma,
        referencias=referencias,
    )
