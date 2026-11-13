"""
Máquina de Estados de Sessão do SIGAA (`si3.ufc.br`).
Único módulo autorizado a invocar `http.post_form` e `http.post_form_binario`.
Gerencia `javax.faces.ViewState`, `ultima_view_ativa` e bloqueio preventivo `login_suspenso`.
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ufc_mcp.nucleo import risco
from ufc_mcp.nucleo.credenciais import Cofre, SessaoGuardada
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.http import ClienteEducado, RespostaBinaria, RespostaHttp
from ufc_mcp.nucleo.paginas import (
    REGEX_JSCOOK_ACTION,
    FormularioJsf,
    TipoPagina,
    achar_tag,
    extrair_formulario,
    extrair_pares_jsfcljs,
    identificar_pagina,
    validar_campos_visiveis_login,
)

URL_BASE_SIGAA = "https://si3.ufc.br"
URL_TELA_LOGIN = "https://si3.ufc.br/sigaa/verTelaLogin.do"
URL_LOGAR = "https://si3.ufc.br/sigaa/logar.do?dispatch=logOn"
URL_PAGINA_INICIAL = "https://si3.ufc.br/sigaa/paginaInicial.do"
URL_PORTAL_DISCENTE = "https://si3.ufc.br/sigaa/verPortalDiscente.do"
URL_DISCENTE_JSF = "https://si3.ufc.br/sigaa/portais/discente/discente.jsf"


_DENTRO_DO_LOCK: contextvars.ContextVar[bool] = contextvars.ContextVar("sigaa_dentro_do_lock", default=False)


_R = TypeVar("_R")


def _serializado(fn: Callable[..., Awaitable[_R]]) -> Callable[..., Awaitable[_R]]:
    """Serializa operações que mutam o estado da sessão JSF (turma atual, ViewState).

    O SIGAA guarda a turma/view atual na sessão; duas chamadas concorrentes (por exemplo, duas
    ferramentas pedidas em paralelo) se misturariam. É reentrante dentro da mesma cadeia de chamadas.
    """

    @functools.wraps(fn)
    async def envoltorio(self: Any, *args: Any, **kwargs: Any) -> _R:
        if _DENTRO_DO_LOCK.get():
            return await fn(self, *args, **kwargs)
        async with self._lock_sessao:
            token = _DENTRO_DO_LOCK.set(True)
            try:
                return await fn(self, *args, **kwargs)
            finally:
                _DENTRO_DO_LOCK.reset(token)

    return envoltorio


class SessaoSigaa:
    """Controla o ciclo de vida da sessão autenticada e do ViewState JSF 1.x."""

    def __init__(
        self,
        http: ClienteEducado,
        cofre: Cofre,
        pasta_config: Path,
    ) -> None:
        self.http = http
        self.cofre = cofre
        self.pasta_config = pasta_config
        self.cookies = httpx.Cookies()
        self._lock_sessao = asyncio.Lock()
        self.logado: bool = False
        self.ultimo_login: str | None = None
        self.ultimo_html_portal: str | None = None
        self.ultima_pagina_principal_turma: dict[str, str] = {}
        self.ultima_view_ativa: tuple[str, str | None] = ("", None)

    @property
    def arquivo_login_suspenso(self) -> Path:
        return self.pasta_config / "login_suspenso"

    def esta_suspenso(self) -> bool:
        return self.arquivo_login_suspenso.exists()

    def limpar_suspensao(self) -> None:
        if self.arquivo_login_suspenso.exists():
            self.arquivo_login_suspenso.unlink()

    def motivo_suspensao(self) -> str | None:
        """Código do erro que originou a suspensão (2ª linha do arquivo), se registrado."""
        try:
            linhas = self.arquivo_login_suspenso.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        return linhas[1].strip() if len(linhas) > 1 and linhas[1].strip() else None

    def _suspender_login(self, motivo: CodigoErro | None = None) -> None:
        self.pasta_config.mkdir(parents=True, exist_ok=True)
        conteudo = datetime.now(UTC).isoformat()
        if motivo is not None:
            conteudo += f"\n{motivo.value}"
        self.arquivo_login_suspenso.write_text(conteudo, encoding="utf-8")

    def _rejeitar_pos_login(self, tipo_pos: TipoPagina) -> None:
        """Trata respostas ao POST de login que não são sucesso: suspende e levanta o erro adequado."""
        if tipo_pos == TipoPagina.LOGIN_INVALIDO:
            self._suspender_login(CodigoErro.CREDENCIAL_INVALIDA)
            raise ErroUfc(
                CodigoErro.CREDENCIAL_INVALIDA,
                "Usuário ou senha recusados pelo SIGAA. Novas tentativas foram suspensas.",
            )
        if tipo_pos == TipoPagina.ACESSO_APLICATIVO_NEGADO:
            self._suspender_login(CodigoErro.ACESSO_AUTOMATIZADO_NEGADO)
            raise ErroUfc(
                CodigoErro.ACESSO_AUTOMATIZADO_NEGADO,
                "O SIGAA recusou o login: 'Tentativa de acesso por aplicativo externo. Operação negada!'. "
                "Novas tentativas foram suspensas.",
            )
        if tipo_pos == TipoPagina.TELA_LOGIN:
            self._suspender_login(CodigoErro.LOGIN_SUSPENSO)
            raise ErroUfc(
                CodigoErro.LOGIN_SUSPENSO,
                "O SIGAA devolveu a tela de login após o envio das credenciais (rejeição não "
                "reconhecida). Novas tentativas foram suspensas.",
            )

    async def _resolver_intersticiais(self, html: str) -> str:
        """Trata vínculo múltiplo (prioriza Graduação Ativo) e questionários puláveis."""
        for _ in range(3):
            tipo = identificar_pagina(html)
            if tipo == TipoPagina.SELECAO_VINCULO:
                soup = BeautifulSoup(html, "lxml")
                link_escolhido = None
                for tr in soup.find_all("tr"):
                    txt = tr.get_text(" ", strip=True).upper()
                    a = tr.find("a", href=re.compile(r"escolheVinculo\.do"))
                    if a and "GRADUA" in txt and "ATIVO" in txt:
                        link_escolhido = a
                        break
                if link_escolhido is None:
                    link_escolhido = achar_tag(soup, "a", href=re.compile(r"escolheVinculo\.do"))
                if link_escolhido is None:
                    raise ErroUfc(
                        CodigoErro.LAYOUT_MUDOU,
                        "Tela de seleção de vínculo não contém link escolheVinculo.do.",
                    )
                url_vinculo = urljoin(URL_BASE_SIGAA, str(link_escolhido["href"]))
                resp = await self.http.get(url_vinculo, cookies=self.cookies)
                html = resp.texto
                continue

            if tipo == TipoPagina.QUESTIONARIO_INTERSTICIAL:
                soup = BeautifulSoup(html, "lxml")
                link_pular = achar_tag(
                    soup, "a", string=re.compile(r"Responder depois|Continuar para o Portal", re.I)
                )
                if link_pular and link_pular.get("href"):
                    url_pular = urljoin(URL_BASE_SIGAA, str(link_pular["href"]))
                    resp = await self.http.get(url_pular, cookies=self.cookies)
                    html = resp.texto
                    continue
                break
            break
        return html

    async def _ir_ao_portal(self, resp_login: RespostaHttp) -> str:
        """Percorre o caminho de um navegador após o login: tela de progresso -> Módulos e Portais -> Portal do Discente."""
        html = await self._resolver_intersticiais(resp_login.texto)
        if identificar_pagina(html) == TipoPagina.PORTAL_DISCENTE:
            return html
        referer = resp_login.url_final
        if urlparse(referer).path.split(";")[0].endswith("/progresso.jsf"):
            # A tela de progresso redireciona por JavaScript para a página de módulos.
            resp_mod = await self.http.get(URL_PAGINA_INICIAL, cookies=self.cookies, referer=referer)
            html = await self._resolver_intersticiais(resp_mod.texto)
            referer = resp_mod.url_final
            if identificar_pagina(html) == TipoPagina.PORTAL_DISCENTE:
                return html
        resp_portal = await self.http.get(URL_PORTAL_DISCENTE, cookies=self.cookies, referer=referer)
        return await self._resolver_intersticiais(resp_portal.texto)

    async def _logar(self) -> str:
        """Autentica via Credencial ou carrega cookies do CofreSessao."""
        if self.esta_suspenso():
            if self.motivo_suspensao() == CodigoErro.ACESSO_AUTOMATIZADO_NEGADO.value:
                raise ErroUfc(
                    CodigoErro.ACESSO_AUTOMATIZADO_NEGADO,
                    "Login suspenso: o SIGAA recusou anteriormente o acesso por aplicativo externo.",
                )
            raise ErroUfc(
                CodigoErro.LOGIN_SUSPENSO,
                "Tentativa de login bloqueada preventivamente após falha anterior.",
            )

        cred = self.cofre.obter_credencial()
        if cred is None:
            sessao_guardada = self.cofre.obter_sessao()
            if sessao_guardada is not None:
                self.cookies.clear()
                for k, v in sessao_guardada.cookies.items():
                    self.cookies.set(k, v)
                resp = await self.http.get(URL_PORTAL_DISCENTE, cookies=self.cookies)
                html = await self._resolver_intersticiais(resp.texto)
                if identificar_pagina(html) == TipoPagina.PORTAL_DISCENTE:
                    self.logado = True
                    self.ultimo_login = sessao_guardada.criada_em
                    self.ultimo_html_portal = html
                    self.ultima_view_ativa = ("/sigaa/portais/discente/discente.jsf", None)
                    return html
                self.cofre.limpar()
                raise ErroUfc(
                    CodigoErro.SEM_CREDENCIAL,
                    "Sessão temporária encerrada. Rode ufc-mcp login --so-sessao.",
                )
            raise ErroUfc(
                CodigoErro.SEM_CREDENCIAL,
                "Nenhuma credencial ou sessão ativa encontrada no cofre.",
            )

        tela_login = await self.http.get(URL_TELA_LOGIN, cookies=self.cookies)
        validar_campos_visiveis_login(tela_login.texto)
        form_login = extrair_formulario(tela_login.texto, "loginForm")
        dados_post = dict(form_login.campos)
        dados_post["user.login"] = cred.usuario
        dados_post["user.senha"] = cred.senha
        dados_post.setdefault("entrar", "Entrar")  # botão submit do loginForm (o navegador o envia)
        # width/height são preenchidos por JS no navegador (screen.width/height)
        if "width" in dados_post:
            dados_post["width"] = "1920"
        if "height" in dados_post:
            dados_post["height"] = "1080"

        # Usa action do formulário (pode conter jsessionid no path)
        from urllib.parse import urljoin
        action_url = urljoin(URL_BASE_SIGAA, form_login.action)

        resp_login = await self.http.post_form(action_url, dados_post, cookies=self.cookies)
        del dados_post
        del cred

        self._rejeitar_pos_login(identificar_pagina(resp_login.texto))

        html = await self._ir_ao_portal(resp_login)

        if identificar_pagina(html) != TipoPagina.PORTAL_DISCENTE:
            raise ErroUfc(
                CodigoErro.LAYOUT_MUDOU,
                "Não foi possível alcançar o Portal do Discente após o login.",
            )

        self.logado = True
        self.ultimo_login = datetime.now(UTC).replace(microsecond=0).isoformat()
        self.ultimo_html_portal = html
        self.ultima_view_ativa = ("/sigaa/portais/discente/discente.jsf", None)
        return html

    async def autenticar_com_credencial_efemera(self, usuario: str, senha: str) -> SessaoGuardada:
        """Realiza login único para `ufc-mcp login --so-sessao` e devolve apenas os cookies."""
        self.limpar_suspensao()
        self.cookies.clear()
        tela_login = await self.http.get(URL_TELA_LOGIN, cookies=self.cookies)
        validar_campos_visiveis_login(tela_login.texto)
        form_login = extrair_formulario(tela_login.texto, "loginForm")
        dados_post = dict(form_login.campos)
        dados_post["user.login"] = usuario
        dados_post["user.senha"] = senha
        dados_post.setdefault("entrar", "Entrar")  # botão submit do loginForm (o navegador o envia)
        # width/height são preenchidos por JS no navegador (screen.width/height)
        if "width" in dados_post:
            dados_post["width"] = "1920"
        if "height" in dados_post:
            dados_post["height"] = "1080"

        # Usa action do formulário (pode conter jsessionid no path)
        from urllib.parse import urljoin
        action_url = urljoin(URL_BASE_SIGAA, form_login.action)

        resp_login = await self.http.post_form(action_url, dados_post, cookies=self.cookies)
        del dados_post
        self._rejeitar_pos_login(identificar_pagina(resp_login.texto))
        html = await self._ir_ao_portal(resp_login)
        if identificar_pagina(html) != TipoPagina.PORTAL_DISCENTE:
            raise ErroUfc(CodigoErro.LAYOUT_MUDOU, "Portal do Discente não carregou após login.")

        sessao = SessaoGuardada(cookies={k: v for k, v in self.cookies.items()})
        self.cofre.salvar_sessao(sessao)
        self.logado = True
        self.ultimo_login = sessao.criada_em
        self.ultimo_html_portal = html
        self.ultima_view_ativa = ("/sigaa/portais/discente/discente.jsf", None)
        return sessao

    @_serializado
    async def abrir_portal(self, *, forcar_atualizacao: bool = False) -> str:
        """Retorna o HTML do Portal do Discente garantindo ViewState válido."""
        if (
            not forcar_atualizacao
            and self.logado
            and self.ultimo_html_portal is not None
            and self.ultima_view_ativa[0] == "/sigaa/portais/discente/discente.jsf"
        ):
            return self.ultimo_html_portal

        if self.logado:
            resp = await self.http.get(URL_PORTAL_DISCENTE, cookies=self.cookies)
            html = await self._resolver_intersticiais(resp.texto)
            if identificar_pagina(html) == TipoPagina.PORTAL_DISCENTE:
                self.ultimo_html_portal = html
                self.ultima_view_ativa = ("/sigaa/portais/discente/discente.jsf", None)
                return html
            self.logado = False

        return await self._logar()

    @_serializado
    async def abrir_menu(self, expressao_bean: str) -> str:
        """
        Executa uma ação de menu do Portal do Discente após validá-la em `risco.exigir_acao_menu`.
        Reconecta 1 vez automaticamente caso a sessão JSF tenha expirado.
        """
        risco.exigir_acao_menu(expressao_bean)
        for tentativa in range(2):
            html_portal = await self.abrir_portal(forcar_atualizacao=(tentativa > 0))
            form_menu = extrair_formulario(html_portal, "menu:form_menu_discente")
            prefixo = "menu_form_menu_discente_j_id_jsp_1_menu"
            for m in REGEX_JSCOOK_ACTION.finditer(html_portal):
                if m.group(2) == expressao_bean:
                    prefixo = m.group(1)
                    break
            dados = dict(form_menu.campos)
            dados["jscook_action"] = f"{prefixo}:A]#{{{expressao_bean}}}"
            url_post = urljoin(URL_BASE_SIGAA, form_menu.action)
            resp = await self.http.post_form(url_post, dados, cookies=self.cookies)
            tipo = identificar_pagina(resp.texto)
            if tipo in (TipoPagina.TELA_LOGIN, TipoPagina.SESSAO_EXPIRADA) and tentativa == 0:
                self.logado = False
                continue
            if tipo in (TipoPagina.TELA_LOGIN, TipoPagina.SESSAO_EXPIRADA):
                raise ErroUfc(CodigoErro.SESSAO_EXPIRADA, "Sessão expirou durante navegação.")
            self.ultima_view_ativa = (f"menu:{expressao_bean}", None)
            return resp.texto
        raise ErroUfc(CodigoErro.SESSAO_EXPIRADA, "Falha ao abrir item de menu no SIGAA.")

    @_serializado
    async def abrir_turma(self, id_turma: str) -> str:
        """Abre a página Principal da Turma Virtual (`id_turma`) a partir do Portal do Discente."""
        if not re.match(r"^\d{1,10}$", id_turma):
            raise ErroUfc(CodigoErro.PARAMETRO_INVALIDO, f"id_turma inválido: {id_turma!r}")

        for tentativa in range(2):
            html_portal = await self.abrir_portal(forcar_atualizacao=(tentativa > 0))
            soup = BeautifulSoup(html_portal, "lxml")
            form_encontrado = None
            for form in soup.find_all("form", attrs={"name": re.compile(r"^form_acessarTurmaVirtual")}):
                inp = form.find("input", attrs={"name": "idTurma", "value": id_turma})
                if inp is not None:
                    form_encontrado = form
                    break

            if form_encontrado is None:
                raise ErroUfc(
                    CodigoErro.NAO_ENCONTRADO,
                    f"Turma {id_turma} não encontrada no Portal do Discente.",
                )

            # Todas as linhas do portal compartilham o mesmo name/id de formulário: os campos devem
            # vir do formulário da turma pedida, nunca do primeiro formulário com esse nome.
            dados = {
                str(i["name"]): str(i.get("value") or "")
                for i in form_encontrado.find_all("input")
                if i.get("name") and str(i.get("type") or "text").lower() not in ("submit", "button", "image", "reset")
            }
            action_form = str(form_encontrado.get("action") or "").strip()
            link = form_encontrado.find("a", onclick=True)
            if link:
                _, pares = extrair_pares_jsfcljs(str(link["onclick"]))
                dados.update(pares)

            url_post = urljoin(URL_BASE_SIGAA, action_form)
            resp = await self.http.post_form(url_post, dados, cookies=self.cookies)
            tipo = identificar_pagina(resp.texto)
            if tipo in (TipoPagina.TELA_LOGIN, TipoPagina.SESSAO_EXPIRADA) and tentativa == 0:
                self.logado = False
                continue
            if tipo != TipoPagina.TURMA_VIRTUAL:
                raise ErroUfc(
                    CodigoErro.LAYOUT_MUDOU,
                    f"Resposta inesperada ao abrir Turma Virtual {id_turma}: {tipo}",
                )
            self.ultima_pagina_principal_turma[id_turma] = resp.texto
            self.ultima_view_ativa = ("/sigaa/ava/index.jsf:Principal", id_turma)
            return resp.texto

        raise ErroUfc(CodigoErro.SESSAO_EXPIRADA, "Sessão expirou ao abrir Turma Virtual.")

    async def postback(
        self,
        html_atual: str,
        nome_form: str,
        pares_extras: dict[str, str],
        *,
        rotulo: str,
        id_turma: str | None = None,
    ) -> str:
        """Executa um postback JSF validado contra `POSTBACKS_PERMITIDOS`."""
        form_jsf: FormularioJsf = extrair_formulario(html_atual, nome_form)
        risco.exigir_postback(form_jsf.view, rotulo)
        dados = dict(form_jsf.campos)
        dados.update(pares_extras)
        url_post = urljoin(URL_BASE_SIGAA, form_jsf.action)
        resp = await self.http.post_form(url_post, dados, cookies=self.cookies)
        tipo = identificar_pagina(resp.texto)
        if tipo in (TipoPagina.TELA_LOGIN, TipoPagina.SESSAO_EXPIRADA):
            self.logado = False
            raise ErroUfc(CodigoErro.SESSAO_EXPIRADA, "Sessão expirou durante postback JSF.")
        self.ultima_view_ativa = (f"{form_jsf.view}:{rotulo}", id_turma)
        return resp.texto

    @_serializado
    async def navegar_menu_turma(self, id_turma: str, rotulo: str) -> str:
        """Abre a Turma Virtual e aciona um item do menu lateral (`formMenu`)."""
        html_principal = await self.abrir_turma(id_turma)
        if rotulo == "Principal":
            return html_principal

        soup = BeautifulSoup(html_principal, "lxml")
        form_menu = achar_tag(soup, "form", id="formMenu") or achar_tag(
            soup, "form", attrs={"name": "formMenu"}
        )
        if form_menu is None:
            raise ErroUfc(CodigoErro.LAYOUT_MUDOU, "formMenu ausente na Turma Virtual.")

        link_alvo = None
        for a in form_menu.find_all("a", onclick=True):
            txt = " ".join(a.get_text(" ", strip=True).split())
            if txt.lower() == rotulo.lower():
                link_alvo = a
                break

        if link_alvo is None:
            raise ErroUfc(
                CodigoErro.NAO_ENCONTRADO,
                f"Opção '{rotulo}' não encontrada no menu da Turma Virtual {id_turma}.",
            )

        nome_form, pares = extrair_pares_jsfcljs(str(link_alvo["onclick"]))
        return await self.postback(
            html_principal, nome_form, pares, rotulo=rotulo, id_turma=id_turma
        )

    @_serializado
    async def baixar_material_turma(
        self, id_turma: str, id_material: str
    ) -> tuple[RespostaBinaria, str]:
        """
        Baixa um arquivo de aula anexado na página Principal da Turma Virtual.
        Garante a consistência do `javax.faces.ViewState` no JSF 1.x: se `ultima_view_ativa`
        não for `("/sigaa/ava/index.jsf:Principal", id_turma)`, reabre `abrir_turma(id_turma)`
        automaticamente antes de submeter o postback binário.
        """
        if (
            self.ultima_view_ativa != ("/sigaa/ava/index.jsf:Principal", id_turma)
            or id_turma not in self.ultima_pagina_principal_turma
        ):
            html_principal = await self.abrir_turma(id_turma)
        else:
            html_principal = self.ultima_pagina_principal_turma[id_turma]

        soup = BeautifulSoup(html_principal, "lxml")
        conteudo = soup.select_one("#conteudo, #ava-conteudo") or soup
        materiais_links: list[tuple[str, str, str]] = []
        contador = 0
        for a in conteudo.find_all("a", onclick=True):
            onclick = str(a.get("onclick") or "")
            if "jsfcljs" not in onclick:
                continue
            form_parent = a.find_parent("form")
            if form_parent and str(form_parent.get("id") or form_parent.get("name")) == "formMenu":
                continue
            titulo_link = " ".join(a.get_text(" ", strip=True).split())
            if not titulo_link:
                continue
            contador += 1
            mat_id = f"mat_{contador:02d}"
            materiais_links.append((mat_id, titulo_link, onclick))

        escolhido = next((m for m in materiais_links if m[0] == id_material), None)
        if escolhido is None:
            raise ErroUfc(
                CodigoErro.NAO_ENCONTRADO,
                f"Material '{id_material}' não encontrado na Turma Virtual {id_turma}.",
            )

        _, titulo_mat, onclick_mat = escolhido
        nome_form, pares = extrair_pares_jsfcljs(onclick_mat)
        form_jsf = extrair_formulario(html_principal, nome_form)
        risco.exigir_postback(form_jsf.view, "Baixar Material")
        dados = dict(form_jsf.campos)
        dados.update(pares)
        url_post = urljoin(URL_BASE_SIGAA, form_jsf.action)

        resp_bin = await self.http.post_form_binario(
            url_post, dados, cookies=self.cookies
        )
        if resp_bin.content_type.lower().startswith("text/html"):
            raise ErroUfc(
                CodigoErro.NAO_ENCONTRADO,
                "O SIGAA não retornou um arquivo binário válido para este material.",
            )
        nome_final = resp_bin.nome_arquivo_sugerido or titulo_mat
        return resp_bin, nome_final
