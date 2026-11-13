"""Cliente HTTP Educado com allowlist de hosts, TLS forçado, rate limiting e download binário."""

from __future__ import annotations

import asyncio
import re
import time
from collections import deque
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

from ufc_mcp.nucleo.config import Limites
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.modelos_base import BaseModel, Field

HOSTS_PERMITIDOS: frozenset[str] = frozenset({
    "si3.ufc.br",
    "ufc2012.ufc.br",
    "ufcinforma.ufc.br",
    "prograd.ufc.br",
    "prae.ufc.br",
    "dados.ufc.br",
})

# Únicos formulários públicos (sem autenticação) em que um POST de leitura é aceito.
CAMINHOS_POST_PUBLICOS: frozenset[str] = frozenset({
    "/sigaa/public/curso/turmas.jsf",
})

USER_AGENT_PADRAO = (
    "ufc-mcp/0.9 (cliente pessoal de estudante da UFC; leitura da propria conta; projeto academico de codigo aberto)"
)

REGEX_CONTENT_DISPOSITION_FILENAME = re.compile(
    r"""filename\*?=(?:UTF-8'')?["']?([^"';\r\n]+)""", re.IGNORECASE
)


class RespostaHttp(BaseModel):
    """Resposta textual decodificada de uma requisição HTTP."""

    status: int
    url_final: str
    texto: str
    cabecalhos: dict[str, str] = Field(default_factory=dict)


class RespostaBinaria(BaseModel):
    """Resposta binária segura para download de materiais da Turma Virtual."""

    status: int
    url_final: str
    conteudo: bytes
    content_type: str
    nome_arquivo_sugerido: str | None = None
    cabecalhos: dict[str, str] = Field(default_factory=dict)


def validar_e_normalizar_url(url: str) -> tuple[str, str]:
    """
    Reescreve http:// para https:// e valida se o host pertence a HOSTS_PERMITIDOS.
    Retorna (url_https, host).
    """
    parsed = urlparse(url)
    esquema = parsed.scheme.lower()
    if esquema not in ("http", "https"):
        raise ErroUfc(
            CodigoErro.ACAO_BLOQUEADA,
            f"Esquema de URL não permitido: {esquema}",
        )
    host = (parsed.hostname or "").lower()
    if host not in HOSTS_PERMITIDOS:
        raise ErroUfc(
            CodigoErro.ACAO_BLOQUEADA,
            f"Domínio bloqueado pela política de segurança: {host}",
            detalhes={"host": host},
        )
    if esquema == "http":
        parsed = parsed._replace(scheme="https")
    return urlunparse(parsed), host


class ClienteEducado:
    """
    Único ponto do sistema autorizado a instanciar httpx.AsyncClient.
    Impõe serialização por host (asyncio.Lock), pausa mínima >= 2.0s e tetos de taxa.
    """

    def __init__(
        self,
        limites: Limites | None = None,
        *,
        user_agent: str = USER_AGENT_PADRAO,
        relogio: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], Any] = asyncio.sleep,
        transporte: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.limites = limites or Limites()
        self.user_agent = user_agent
        self._relogio = relogio
        self._dormir = dormir
        self._transporte = transporte
        self._locks_host: dict[str, asyncio.Lock] = {}
        self._ultimo_acesso_host: dict[str, float] = {}
        self._janela_minuto: deque[float] = deque()
        self._janela_hora: deque[float] = deque()
        self._janela_dia: deque[float] = deque()
        self.total_requisicoes: int = 0
        self.intervalos_observados: list[float] = []

    def _obter_lock(self, host: str) -> asyncio.Lock:
        if host not in self._locks_host:
            self._locks_host[host] = asyncio.Lock()
        return self._locks_host[host]

    def _limpar_janelas(self, agora: float) -> None:
        while self._janela_minuto and agora - self._janela_minuto[0] >= 60.0:
            self._janela_minuto.popleft()
        while self._janela_hora and agora - self._janela_hora[0] >= 3600.0:
            self._janela_hora.popleft()
        while self._janela_dia and agora - self._janela_dia[0] >= 86400.0:
            self._janela_dia.popleft()

    def contadores_atuais(self) -> dict[str, int]:
        agora = self._relogio()
        self._limpar_janelas(agora)
        return {
            "usadas_no_minuto": len(self._janela_minuto),
            "usadas_na_hora": len(self._janela_hora),
            "usadas_no_dia": len(self._janela_dia),
            "total_requisicoes": self.total_requisicoes,
        }

    async def _aguardar_vez_e_contabilizar(self, host: str) -> None:
        agora = self._relogio()
        self._limpar_janelas(agora)
        if len(self._janela_minuto) >= self.limites.max_por_minuto:
            raise ErroUfc(
                CodigoErro.LIMITE_DE_REQUISICOES,
                f"Limite de {self.limites.max_por_minuto} requisições/minuto atingido.",
            )
        if len(self._janela_hora) >= self.limites.max_por_hora:
            raise ErroUfc(
                CodigoErro.LIMITE_DE_REQUISICOES,
                f"Limite de {self.limites.max_por_hora} requisições/hora atingido.",
            )
        if len(self._janela_dia) >= self.limites.max_por_dia:
            raise ErroUfc(
                CodigoErro.LIMITE_DE_REQUISICOES,
                f"Limite de {self.limites.max_por_dia} requisições/dia atingido.",
            )

        ultimo = self._ultimo_acesso_host.get(host)
        if ultimo is not None:
            decorrido = agora - ultimo
            if decorrido < self.limites.pausa_minima_s:
                espera = self.limites.pausa_minima_s - decorrido
                await self._dormir(espera)
                agora = self._relogio()
            self.intervalos_observados.append(agora - ultimo)

        self._ultimo_acesso_host[host] = agora
        self._janela_minuto.append(agora)
        self._janela_hora.append(agora)
        self._janela_dia.append(agora)
        self.total_requisicoes += 1

    def _decodificar_corpo(self, resp: httpx.Response, host: str) -> str:
        ct = resp.headers.get("content-type", "")
        if "charset=" in ct.lower():
            return resp.text
        if host == "si3.ufc.br":
            return resp.content.decode("iso-8859-1", errors="replace")
        return resp.content.decode("utf-8", errors="replace")

    async def _executar_com_redirecionamento(
        self,
        metodo: str,
        url: str,
        *,
        dados: dict[str, str] | None = None,
        cookies: httpx.Cookies | None = None,
        referer_inicial: str | None = None,
    ) -> tuple[httpx.Response, str, str]:
        url_atual, host_atual = validar_e_normalizar_url(url)
        metodo_atual = metodo.upper()
        dados_atuais = dados

        jar = cookies if cookies is not None else httpx.Cookies()
        base_headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
        }

        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=self.limites.timeout_s,
            headers=base_headers,
            cookies=jar,
            transport=self._transporte,
        ) as client:
            referer = referer_inicial or "https://si3.ufc.br/sigaa/verTelaLogin.do"
            for _salto in range(6):
                lock = self._obter_lock(host_atual)
                async with lock:
                    await self._aguardar_vez_e_contabilizar(host_atual)
                    try:
                        request_headers = dict(base_headers)
                        request_headers["Referer"] = referer
                        if metodo_atual == "POST":
                            resp = await client.post(url_atual, data=dados_atuais or {}, headers=request_headers)
                        else:
                            resp = await client.get(url_atual, headers=request_headers)
                    except httpx.TimeoutException as exc:
                        raise ErroUfc(
                            CodigoErro.TEMPO_ESGOTADO,
                            f"Tempo esgotado ao acessar {host_atual}.",
                        ) from exc
                    except httpx.RequestError as exc:
                        codigo = (
                            CodigoErro.SIGAA_INDISPONIVEL
                            if host_atual == "si3.ufc.br"
                            else CodigoErro.FONTE_INDISPONIVEL
                        )
                        raise ErroUfc(
                            codigo,
                            f"Falha de rede ao conectar a {host_atual}: {exc}",
                        ) from exc

                if cookies is not None:
                    cookies.update(client.cookies)
                    for k, v in resp.cookies.items():
                        cookies.set(k, v)

                if resp.status_code in (301, 302, 303, 307, 308):
                    loc = resp.headers.get("location")
                    if not loc:
                        break
                    proxima_url = urljoin(url_atual, loc)
                    url_atual, host_atual = validar_e_normalizar_url(proxima_url)
                    referer = url_atual
                    if resp.status_code in (301, 302, 303):
                        metodo_atual = "GET"
                        dados_atuais = None
                    continue

                if resp.status_code >= 500:
                    codigo = (
                        CodigoErro.SIGAA_INDISPONIVEL
                        if host_atual == "si3.ufc.br"
                        else CodigoErro.FONTE_INDISPONIVEL
                    )
                    raise ErroUfc(
                        codigo,
                        f"Servidor {host_atual} respondeu com erro HTTP {resp.status_code} "
                        f"em {metodo_atual} {urlparse(url_atual).path.split(';')[0]} (salto {_salto + 1}).",
                    )

                return resp, url_atual, host_atual

        raise ErroUfc(
            CodigoErro.SIGAA_INDISPONIVEL,
            "Número máximo de redirecionamentos HTTP excedido (limite = 5).",
        )


    async def get(
        self,
        url: str,
        *,
        cookies: httpx.Cookies | None = None,
        referer: str | None = None,
    ) -> RespostaHttp:
        resp, url_final, host_final = await self._executar_com_redirecionamento(
            "GET", url, cookies=cookies, referer_inicial=referer
        )
        texto = self._decodificar_corpo(resp, host_final)
        return RespostaHttp(
            status=resp.status_code,
            url_final=url_final,
            texto=texto,
            cabecalhos={k.lower(): v for k, v in resp.headers.items()},
        )

    async def post_form_publico(
        self,
        url: str,
        dados: dict[str, str],
        *,
        cookies: httpx.Cookies | None = None,
    ) -> RespostaHttp:
        """
        Envia o formulário de busca pública do SIGAA (sem autenticação e sem cookies de sessão).

        Só é permitido para páginas públicas explicitamente listadas; nunca envia
        credenciais nem reaproveita o jar de sessão autenticada.
        """
        url_https, host = validar_e_normalizar_url(url)
        caminho = urlparse(url_https).path
        if host != "si3.ufc.br" or caminho not in CAMINHOS_POST_PUBLICOS:
            raise ErroUfc(
                CodigoErro.ACAO_BLOQUEADA,
                f"POST público bloqueado para {host}{caminho}.",
                detalhes={"host": host, "caminho": caminho},
            )
        resp, url_final, host_final = await self._executar_com_redirecionamento(
            "POST", url_https, dados=dados, cookies=cookies
        )
        texto = self._decodificar_corpo(resp, host_final)
        return RespostaHttp(
            status=resp.status_code,
            url_final=url_final,
            texto=texto,
            cabecalhos={k.lower(): v for k, v in resp.headers.items()},
        )

    async def post_form(
        self,
        url: str,
        dados: dict[str, str],
        *,
        cookies: httpx.Cookies | None = None,
    ) -> RespostaHttp:
        resp, url_final, host_final = await self._executar_com_redirecionamento(
            "POST", url, dados=dados, cookies=cookies
        )
        texto = self._decodificar_corpo(resp, host_final)
        return RespostaHttp(
            status=resp.status_code,
            url_final=url_final,
            texto=texto,
            cabecalhos={k.lower(): v for k, v in resp.headers.items()},
        )

    async def post_form_binario(
        self,
        url: str,
        dados: dict[str, str],
        *,
        cookies: httpx.Cookies,
        max_bytes: int = 26_214_400,
    ) -> RespostaBinaria:
        resp, url_final, _host_final = await self._executar_com_redirecionamento(
            "POST", url, dados=dados, cookies=cookies
        )
        conteudo = resp.content
        if len(conteudo) > max_bytes:
            raise ErroUfc(
                CodigoErro.PARAMETRO_INVALIDO,
                "Arquivo excede o limite de segurança de 25 MB.",
            )
        cd = resp.headers.get("content-disposition", "")
        nome_sugerido: str | None = None
        m = REGEX_CONTENT_DISPOSITION_FILENAME.search(cd)
        if m:
            nome_sugerido = m.group(1).strip()
        return RespostaBinaria(
            status=resp.status_code,
            url_final=url_final,
            conteudo=conteudo,
            content_type=resp.headers.get("content-type", "application/octet-stream"),
            nome_arquivo_sugerido=nome_sugerido,
            cabecalhos={k.lower(): v for k, v in resp.headers.items()},
        )
