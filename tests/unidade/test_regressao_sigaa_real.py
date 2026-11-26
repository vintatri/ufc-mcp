"""Regressões encontradas ao rodar o ufc-mcp contra o SIGAA real (13/11/2026).

Os HTMLs abaixo são trechos mínimos e anonimizados que reproduzem a estrutura real
que quebrava os parsers; não contêm dados pessoais.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from types import SimpleNamespace

from ufc_mcp.fontes.sigaa.parsers.ira import _conv_float
from ufc_mcp.fontes.sigaa.parsers.pendencias import parse_pendencias_ou_biblioteca
from ufc_mcp.fontes.sigaa.parsers.portal import parse_portal_discente
from ufc_mcp.fontes.sigaa.parsers.turma_virtual import (
    _normalizar_data_hora_iso,
    parse_turma_avaliacoes,
    parse_turma_noticias,
    parse_turma_plano_curso,
)
from ufc_mcp.nucleo.sessao_sigaa import _serializado
from ufc_mcp.servicos.meu_dia import construir_minha_semana

CABECALHO_AVA = '<form id="formMenu" name="formMenu" action="/sigaa/ava/index.jsf"></form>'


def _linha_turma(id_turma: str, nome: str, local: str, horario: str) -> str:
    return (
        '<tr><td class="descricao">'
        '<form id="form_acessarTurmaVirtual" name="form_acessarTurmaVirtual" method="post" '
        'action="/sigaa/portais/discente/discente.jsf">'
        f'<input type="hidden" value="{id_turma}" name="idTurma" />'
        f'<a href="#" onclick="return false">{nome}</a></form></td>'
        f"<td>01</td><td>{local}</td><td><center>{horario}</center></td></tr>"
    )


def test_portal_tabela_com_quatro_colunas_separa_local_e_horario() -> None:
    html = (
        '<html><body><div id="info-usuario"><div class="nome_usuario"><p> FULANO DE TAL</p></div></div>'
        '<form id="menu:form_menu_discente" name="menu:form_menu_discente"></form>'
        '<div id="agenda-docente"><table>'
        "<tr><td>Matrícula:</td><td>123456</td></tr>"
        "<tr><td>Curso:</td><td>CURSO EXEMPLO - MT</td></tr>"
        "<tr><td>Entrada:</td><td> 2020.1</td></tr></table></div>"
        "<table>"
        + _linha_turma("1", "EQ0901 - DISCIPLINA EXEMPLO A", "CT - Bloco 900 - Sala 01",
                       "SEG 08:00-10:00<br />QUI 08:00-10:00<br />(10/08/2026 - 11/12/2026)")
        + _linha_turma("2", "EQ0902 - DISCIPLINA EXEMPLO B", "CT - Bloco 901 - Sala 02",
                       "QUA 10:00-12:00<br />(10/08/2026 - 11/12/2026)")
        + "</table></body></html>"
    )
    r = parse_portal_discente(html, identificadores=True)
    assert (r.nome, r.matricula, r.entrada) == ("FULANO DE TAL", "123456", "2020.1")
    assert r.curso == "CURSO EXEMPLO - MT"
    t1, t2 = r.turmas
    assert t1.local == "CT - Bloco 900 - Sala 01"
    assert [(h.dia, h.inicio, h.fim) for h in t1.horarios] == [("SEG", "08:00", "10:00"), ("QUI", "08:00", "10:00")]
    assert t2.local == "CT - Bloco 901 - Sala 02"
    assert t1.inicio_vigencia == "2026-08-10"


def test_ira_ponto_decimal_nao_vira_milhar() -> None:
    assert _conv_float("7.6612") == 7.6612
    assert _conv_float("6.286198139190674") == 6.2862
    assert _conv_float("1.234,56") == 1234.56
    assert _conv_float("7,66") == 7.66


def test_biblioteca_sem_debitos_nao_e_layout_mudou() -> None:
    html = (
        '<html><head><title>Consultar Situação na Biblioteca</title></head><body><div id="conteudo">'
        "<h2>Portal do Discente &gt; Consultar Situação na Biblioteca</h2>"
        "<p>Relatório de Situação na Biblioteca Débitos Não foram encontrados débitos. "
        "Empréstimos em Atraso Não foram encontrados empréstimos em situação de atraso.</p>"
        "<p>Copyright STI</p></div></body></html>"
    )
    r = parse_pendencias_ou_biblioteca(html, assinatura_esperada="Biblioteca")
    assert "Não foram encontrados débitos" in r.secoes[0].itens[0]["linha"]


def test_prazo_com_as_18h30() -> None:
    assert _normalizar_data_hora_iso("24/09/2026 às 18h30") == "2026-09-24T18:30:00"
    assert _normalizar_data_hora_iso("30/09/2026 às 23h59") == "2026-09-30T23:59:00"
    assert _normalizar_data_hora_iso("10/10/2026") == "2026-10-10T23:59:00"
    assert _normalizar_data_hora_iso("10/10/2026 08:15") == "2026-10-10T08:15:00"


def test_avaliacoes_vazias_no_painel_da_principal() -> None:
    html = (
        f"<html><body>{CABECALHO_AVA}<div id='conteudo'><p>Notícias</p></div>"
        "<div>Avaliações Nenhuma avaliação cadastrada Datas de Avaliações Nenhum item foi encontrado</div>"
        "</body></html>"
    )
    assert parse_turma_avaliacoes(html, id_turma="1").avaliacoes == []


def test_plano_de_curso_nao_cadastrado_nao_inventa_texto() -> None:
    html = (
        f"<html><body>{CABECALHO_AVA}<div id='conteudo'>O componente curricular EQ0902 - X "
        "não possui um programa cadastrado.</div></body></html>"
    )
    r = parse_turma_plano_curso(html, id_turma="1")
    assert r.metodologia.texto_externo == "Programa não cadastrado no SIGAA."
    assert r.cronograma_aulas == [] and r.referencias == []


def test_noticias_do_painel_da_principal() -> None:
    html = (
        f"<html><body>{CABECALHO_AVA}<div id='conteudo'><div class='rich-stglpanel-body'>"
        "14/10/2026 13:21<br>\n <i>Links Videoaulas </i> <br>"
        "22/09/2026 16:01<br>\n <i>Aula inicio hoje as 16:10 </i> <br></div></div></body></html>"
    )
    r = parse_turma_noticias(html, id_turma="1")
    assert [(n.publicada_em, n.titulo.texto_externo) for n in r.noticias] == [
        ("2026-10-14", "Links Videoaulas"),
        ("2026-09-22", "Aula inicio hoje as 16:10"),
    ]


def test_minha_semana_busca_as_duas_semanas_e_filtra_a_janela() -> None:
    consultadas: list[str] = []

    class RuFalso:
        async def consultar_semana(self, inicio_iso, restaurante=1, *, atualizar=False):
            consultadas.append(inicio_iso)
            seg = date.fromisoformat(inicio_iso)
            dias = [SimpleNamespace(data=(seg + timedelta(days=i)).isoformat(),
                                    model_dump=lambda i=i, seg=seg: {"data": (seg + timedelta(days=i)).isoformat()})
                    for i in range(5)]
            return dias, False, 0, []

    class SigaaFalso:
        async def obter_resumo_portal(self, atualizar=False):
            return SimpleNamespace(turmas=[], atividades_proximas=[]), False, 0

    class CalFalso:
        async def consultar_eventos(self, ini, fim, atualizar=False):
            return [], False, 0, False, []

    dados, _, _ = asyncio.run(
        construir_minha_semana(SigaaFalso(), RuFalso(), CalFalso(), inicio_iso="2026-11-13")
    )
    assert consultadas == ["2026-11-09", "2026-11-16"]
    assert [c["data"] for c in dados["cardapios_uteis"]] == [
        "2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19",
    ]


def test_operacoes_da_sessao_nao_se_misturam_em_paralelo() -> None:
    class Sessao:
        def __init__(self) -> None:
            self._lock_sessao = asyncio.Lock()
            self.ativos = 0
            self.maximo = 0

        @_serializado
        async def interna(self) -> None:
            self.ativos += 1
            self.maximo = max(self.maximo, self.ativos)
            await asyncio.sleep(0.01)
            self.ativos -= 1

        @_serializado
        async def externa(self) -> None:
            await self.interna()  # reentrante: não pode travar

    async def rodar() -> int:
        s = Sessao()
        await asyncio.gather(*(s.externa() for _ in range(5)))
        return s.maximo

    assert asyncio.run(rodar()) == 1


def test_listagem_celula_com_links_aninhados_nao_quebra() -> None:
    from bs4 import BeautifulSoup

    from ufc_mcp.fontes.sigaa.parsers.listagem import _limpar_celula_sem_acao

    td = BeautifulSoup(
        '<td>Projeto X <a onclick="x()"><a onclick="y()"><img src="a.png"></a></a> 2026</td>', "lxml"
    ).find("td")
    assert _limpar_celula_sem_acao(td) == "Projeto X 2026"


def test_listagem_que_volta_ao_portal_sem_aviso_nao_e_layout_mudou() -> None:
    from ufc_mcp.fontes.sigaa.parsers.listagem import parse_listagem_generica

    html = '<html><body><form id="menu:form_menu_discente" name="menu:form_menu_discente"></form></body></html>'
    r = parse_listagem_generica(html, tipo="trancamentos")
    assert r.vazio and "Portal do Discente" in (r.mensagem or "")
