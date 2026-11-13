"""Cliente autenticado do SIGAA com CachePessoal em RAM (TTL = 300s)."""

from __future__ import annotations

from urllib.parse import urljoin

import httpx

from ufc_mcp.fontes.sigaa.modelos import (
    AvaliacoesTurma,
    FrequenciaTurma,
    NotasTurma,
    NoticiasTurma,
    PlanoCursoTurma,
    ResultadoHistoricoIra,
    ResultadoListagemGenerica,
    ResultadoPendencias,
    ResultadoProgressoCurso,
    ResumoPortalDiscente,
    TarefasTurma,
    TurmaOfertada,
    VisaoGeralTurma,
)
from ufc_mcp.fontes.sigaa.parsers.agenda import parse_agenda_turmas
from ufc_mcp.fontes.sigaa.parsers.ira import parse_historico_ira
from ufc_mcp.fontes.sigaa.parsers.listagem import (
    MAPA_ACAO_MENU_LISTAGEM,
    parse_listagem_generica,
)
from ufc_mcp.fontes.sigaa.parsers.ofertas import parse_ofertas_turmas
from ufc_mcp.fontes.sigaa.parsers.pendencias import parse_pendencias_ou_biblioteca
from ufc_mcp.fontes.sigaa.parsers.portal import parse_portal_discente
from ufc_mcp.fontes.sigaa.parsers.progresso import parse_progresso_curso
from ufc_mcp.fontes.sigaa.parsers.turma_virtual import (
    parse_turma_avaliacoes,
    parse_turma_frequencia,
    parse_turma_notas,
    parse_turma_noticias,
    parse_turma_plano_curso,
    parse_turma_tarefas,
    parse_turma_visao_geral,
)
from ufc_mcp.nucleo.cache import CachePessoal
from ufc_mcp.nucleo.config import Config
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.paginas import extrair_formulario
from ufc_mcp.nucleo.sessao_sigaa import SessaoSigaa

TTL_SIGAA_RAM_S = 300  # 5 min


class ClienteSigaa:
    def __init__(self, sessao: SessaoSigaa, cache: CachePessoal, config: Config) -> None:
        self.sessao = sessao
        self.cache = cache
        self.config = config

    async def obter_resumo_portal(
        self, *, atualizar: bool = False
    ) -> tuple[ResumoPortalDiscente, bool, int]:
        chave = "sigaa:portal"
        if not atualizar:
            item = self.cache.obter(chave)
            if item is not None:
                return (
                    parse_portal_discente(
                        item.corpo,
                        identificadores=self.config.identificadores,
                    ),
                    True,
                    item.idade_s,
                )
        html = await self.sessao.abrir_portal(forcar_atualizacao=atualizar)
        res = parse_portal_discente(
            html, identificadores=self.config.identificadores
        )
        self.cache.guardar(chave, html, TTL_SIGAA_RAM_S)
        return res, False, 0

    async def obter_progresso_curso(
        self, *, atualizar: bool = False
    ) -> tuple[ResultadoProgressoCurso, bool, int]:
        chave = "sigaa:progresso"
        if not atualizar:
            item = self.cache.obter(chave)
            if item is not None:
                return parse_progresso_curso(item.corpo), True, item.idade_s
        html = await self.sessao.abrir_menu(
            "consultaProgressoDiscenteCurso.iniciarConsultaProgresso"
        )
        res = parse_progresso_curso(html)
        self.cache.guardar(chave, html, TTL_SIGAA_RAM_S)
        return res, False, 0

    async def obter_historico_ira(
        self, *, atualizar: bool = False
    ) -> tuple[ResultadoHistoricoIra, bool, int]:
        chave = "sigaa:ira"
        if not atualizar:
            item = self.cache.obter(chave)
            if item is not None:
                return parse_historico_ira(item.corpo), True, item.idade_s
        html = await self.sessao.abrir_menu("consultaIRADiscente.iniciarConsultaHistoricoIRA")
        res = parse_historico_ira(html)
        self.cache.guardar(chave, html, TTL_SIGAA_RAM_S)
        return res, False, 0

    async def obter_pendencias_conclusao(
        self, *, atualizar: bool = False
    ) -> tuple[ResultadoPendencias, bool, int]:
        chave = "sigaa:pendencias"
        if not atualizar:
            item = self.cache.obter(chave)
            if item is not None:
                return (
                    parse_pendencias_ou_biblioteca(
                        item.corpo, assinatura_esperada="Pendências"
                    ),
                    True,
                    item.idade_s,
                )
        html = await self.sessao.abrir_menu("consultaPendencias.iniciarConsultaPendencias")
        res = parse_pendencias_ou_biblioteca(html, assinatura_esperada="Pendências")
        self.cache.guardar(chave, html, TTL_SIGAA_RAM_S)
        return res, False, 0

    async def obter_situacao_biblioteca(
        self, *, atualizar: bool = False
    ) -> tuple[ResultadoPendencias, bool, int]:
        chave = "sigaa:biblioteca"
        if not atualizar:
            item = self.cache.obter(chave)
            if item is not None:
                return (
                    parse_pendencias_ou_biblioteca(
                        item.corpo, assinatura_esperada="Biblioteca"
                    ),
                    True,
                    item.idade_s,
                )
        html = await self.sessao.abrir_menu(
            "consultaSituacaoDiscenteBiblioteca.iniciarConsultaSituacao"
        )
        res = parse_pendencias_ou_biblioteca(html, assinatura_esperada="Biblioteca")
        self.cache.guardar(chave, html, TTL_SIGAA_RAM_S)
        return res, False, 0

    async def obter_agenda_turmas(
        self, *, atualizar: bool = False
    ) -> tuple[dict[str, object], bool, int]:
        chave = "sigaa:agenda"
        if not atualizar:
            item = self.cache.obter(chave)
            if item is not None:
                return parse_agenda_turmas(item.corpo), True, item.idade_s
        html = await self.sessao.abrir_menu("agendaTurmaDiscenteMBean.visualizarAgendaTurmas")
        res = parse_agenda_turmas(html)
        self.cache.guardar(chave, html, TTL_SIGAA_RAM_S)
        return res, False, 0

    async def obter_listagem(
        self, tipo: str, *, atualizar: bool = False
    ) -> tuple[ResultadoListagemGenerica, bool, int]:
        if tipo not in MAPA_ACAO_MENU_LISTAGEM:
            raise ErroUfc(CodigoErro.PARAMETRO_INVALIDO, f"Tipo de listagem inválido: {tipo}")
        chave = f"sigaa:listagem:{tipo}"
        if not atualizar:
            item = self.cache.obter(chave)
            if item is not None:
                return parse_listagem_generica(item.corpo, tipo=tipo), True, item.idade_s
        html = await self.sessao.abrir_menu(MAPA_ACAO_MENU_LISTAGEM[tipo])
        res = parse_listagem_generica(html, tipo=tipo)
        self.cache.guardar(chave, html, TTL_SIGAA_RAM_S)
        return res, False, 0

    async def obter_ofertas_turmas(
        self,
        *,
        ano: int = 2026,
        periodo: int = 2,
        codigo_componente: str | None = None,
        id_curso: int | None = None,
        atualizar: bool = False,
    ) -> tuple[list[TurmaOfertada], bool, int]:
        curso_id = id_curso or self.config.exigir("curso")
        chave = f"sigaa:ofertas:{curso_id}:{ano}.{periodo}"
        html: str | None = None
        em_cache = False
        idade = 0

        if not atualizar:
            item = self.cache.obter(chave)
            if item is not None:
                html = item.corpo
                em_cache = True
                idade = item.idade_s

        if html is None:
            url_pub = f"https://si3.ufc.br/sigaa/public/curso/turmas.jsf?lc=pt_BR&id={curso_id}"
            # O portal público é anônimo: usamos um jar local e nunca o da sessão autenticada.
            cookies = httpx.Cookies()
            resp_form = await self.sessao.http.get(url_pub, cookies=cookies)

            # Alguns deployments/espelhos já devolvem a listagem no GET (sem formulário).
            try:
                ofertas_diretas = parse_ofertas_turmas(
                    resp_form.texto, codigo_filtro=codigo_componente
                )
            except ErroUfc:
                ofertas_diretas = []
            if ofertas_diretas:
                self.cache.guardar(chave, resp_form.texto, TTL_SIGAA_RAM_S)
                return ofertas_diretas, False, 0

            form = extrair_formulario(resp_form.texto, "form", incluir_botoes=True)
            if "form:inputAno" not in form.campos or "form:inputPeriodo" not in form.campos:
                raise ErroUfc(
                    CodigoErro.LAYOUT_MUDOU,
                    "Formulário público de turmas não possui os campos de ano/período esperados.",
                )
            dados = dict(form.campos)
            dados["form:inputAno"] = str(ano)
            dados["form:inputPeriodo"] = str(periodo)
            action = urljoin(url_pub, form.action)
            resp = await self.sessao.http.post_form_publico(action, dados, cookies=cookies)
            html = resp.texto
            self.cache.guardar(chave, html, TTL_SIGAA_RAM_S)
            em_cache = False
            idade = 0

        ofertas = parse_ofertas_turmas(html, codigo_filtro=codigo_componente)
        return ofertas, em_cache, idade

    async def obter_turma_visao_geral(
        self, id_turma: str, *, atualizar: bool = False
    ) -> tuple[VisaoGeralTurma, bool, int]:
        chave = f"ava:{id_turma}:Principal"
        if not atualizar:
            item = self.cache.obter(chave)
            if item is not None:
                return parse_turma_visao_geral(item.corpo, id_turma=id_turma), True, item.idade_s
        html = await self.sessao.navegar_menu_turma(id_turma, "Principal")
        res = parse_turma_visao_geral(html, id_turma=id_turma)
        self.cache.guardar(chave, html, TTL_SIGAA_RAM_S)
        return res, False, 0

    async def obter_turma_notas(
        self, id_turma: str, *, atualizar: bool = False
    ) -> tuple[NotasTurma, bool, int]:
        chave = f"ava:{id_turma}:Ver Notas"
        if not atualizar:
            item = self.cache.obter(chave)
            if item is not None:
                return parse_turma_notas(item.corpo, id_turma=id_turma), True, item.idade_s
        html = await self.sessao.navegar_menu_turma(id_turma, "Ver Notas")
        res = parse_turma_notas(html, id_turma=id_turma)
        self.cache.guardar(chave, html, TTL_SIGAA_RAM_S)
        return res, False, 0

    async def obter_turma_frequencia(
        self, id_turma: str, *, atualizar: bool = False
    ) -> tuple[FrequenciaTurma, bool, int]:
        chave = f"ava:{id_turma}:Frequência"
        if not atualizar:
            item = self.cache.obter(chave)
            if item is not None:
                return parse_turma_frequencia(item.corpo, id_turma=id_turma), True, item.idade_s
        html = await self.sessao.navegar_menu_turma(id_turma, "Frequência")
        res = parse_turma_frequencia(html, id_turma=id_turma)
        self.cache.guardar(chave, html, TTL_SIGAA_RAM_S)
        return res, False, 0

    async def obter_turma_avaliacoes(
        self, id_turma: str, *, atualizar: bool = False
    ) -> tuple[AvaliacoesTurma, bool, int]:
        chave = f"ava:{id_turma}:Avaliações"
        if not atualizar:
            item = self.cache.obter(chave)
            if item is not None:
                return parse_turma_avaliacoes(item.corpo, id_turma=id_turma), True, item.idade_s
        html = await self.sessao.navegar_menu_turma(id_turma, "Avaliações")
        res = parse_turma_avaliacoes(html, id_turma=id_turma)
        self.cache.guardar(chave, html, TTL_SIGAA_RAM_S)
        return res, False, 0

    async def obter_turma_tarefas(
        self, id_turma: str, *, atualizar: bool = False
    ) -> tuple[TarefasTurma, bool, int]:
        chave = f"ava:{id_turma}:Tarefas"
        if not atualizar:
            item = self.cache.obter(chave)
            if item is not None:
                return parse_turma_tarefas(item.corpo, id_turma=id_turma), True, item.idade_s
        html = await self.sessao.navegar_menu_turma(id_turma, "Tarefas")
        res = parse_turma_tarefas(html, id_turma=id_turma)
        self.cache.guardar(chave, html, TTL_SIGAA_RAM_S)
        return res, False, 0

    async def obter_turma_noticias(
        self, id_turma: str, *, atualizar: bool = False
    ) -> tuple[NoticiasTurma, bool, int]:
        chave = f"ava:{id_turma}:Notícias"
        if not atualizar:
            item = self.cache.obter(chave)
            if item is not None:
                return parse_turma_noticias(item.corpo, id_turma=id_turma), True, item.idade_s
        html = await self.sessao.navegar_menu_turma(id_turma, "Notícias")
        res = parse_turma_noticias(html, id_turma=id_turma)
        self.cache.guardar(chave, html, TTL_SIGAA_RAM_S)
        return res, False, 0

    async def obter_turma_plano_curso(
        self, id_turma: str, *, atualizar: bool = False
    ) -> tuple[PlanoCursoTurma, bool, int]:
        chave = f"ava:{id_turma}:Plano de Curso"
        if not atualizar:
            item = self.cache.obter(chave)
            if item is not None:
                return parse_turma_plano_curso(item.corpo, id_turma=id_turma), True, item.idade_s
        try:
            html = await self.sessao.navegar_menu_turma(id_turma, "Plano de Curso")
            res = parse_turma_plano_curso(html, id_turma=id_turma)
        except ErroUfc:
            html = await self.sessao.navegar_menu_turma(id_turma, "Visualizar Programa")
            res = parse_turma_plano_curso(html, id_turma=id_turma)
        self.cache.guardar(chave, html, TTL_SIGAA_RAM_S)
        return res, False, 0
