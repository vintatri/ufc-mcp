"""Registro unificado das 35 ferramentas MCP (e subconjunto de 15 no perfil `essencial`)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ufc_mcp.fontes.calendario.cliente import ClienteCalendario
from ufc_mcp.fontes.noticias.cliente import ClienteNoticias
from ufc_mcp.fontes.ru.cliente import ClienteRu
from ufc_mcp.fontes.sigaa.cliente import ClienteSigaa
from ufc_mcp.fontes.sigaa_publico.cliente import ClienteSigaaPublico
from ufc_mcp.nucleo.cache import CachePessoal, CachePublico
from ufc_mcp.nucleo.config import Config
from ufc_mcp.nucleo.credenciais import Cofre, cofre_padrao
from ufc_mcp.nucleo.envelope import Envelope, texto_do_envelope
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.http import ClienteEducado
from ufc_mcp.nucleo.sessao_sigaa import SessaoSigaa
from ufc_mcp.servicos.materiais import ServicoMateriais

FERRAMENTAS_PERFIL_ESSENCIAL: frozenset[str] = frozenset({
    "status",
    "configurar",
    "cardapio",
    "calendario",
    "portal",
    "turmas",
    "progresso",
    "ofertas",
    "turma",
    "notas",
    "plano",
    "baixar",
    "aula",
    "alertas",
    "grade",
    "estudo",
})


@dataclass
class DefinicaoFerramenta:
    nome: str
    grupo: str
    descricao: str
    funcao: Callable[..., Awaitable[str]]
    anotacoes: dict[str, bool] = field(
        default_factory=lambda: {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        }
    )


class ContextoApp:
    """Container de injeção de dependências compartilhado pelas 35 ferramentas."""

    def __init__(
        self,
        config: Config | None = None,
        *,
        http: ClienteEducado | None = None,
        cofre: Cofre | None = None,
        cache_publico: CachePublico | None = None,
        cache_pessoal: CachePessoal | None = None,
    ) -> None:
        self.config = config or Config.carregar()
        self.http = http or ClienteEducado(self.config.limites, user_agent=self.config.user_agent)
        self.cofre: Cofre = cofre or cofre_padrao(self.config.pasta_config)
        self.cache_publico = cache_publico or CachePublico(
            self.config.pasta_cache / "cache_publico.sqlite3"
        )
        self.cache_pessoal = cache_pessoal or CachePessoal()
        self.sessao = SessaoSigaa(self.http, self.cofre, self.config.pasta_config)
        self.ru = ClienteRu(self.http, self.cache_publico)
        self.calendario = ClienteCalendario(self.http, self.cache_publico)
        self.sigaa_publico = ClienteSigaaPublico(self.http, self.cache_publico)
        self.noticias = ClienteNoticias(self.http, self.cache_publico)
        self.sigaa = ClienteSigaa(self.sessao, self.cache_pessoal, self.config)
        self.materiais = ServicoMateriais(self.sessao, self.config)
        self.ferramentas_registradas: dict[str, DefinicaoFerramenta] = {}

    def verificar_permissao_execucao(self, nome: str, grupo: str) -> None:
        if nome in self.config.desativadas or grupo in self.config.grupos_desativados:
            raise ErroUfc(
                CodigoErro.FUNCAO_DESATIVADA,
                f"A ferramenta '{nome}' (grupo '{grupo}') está desativada na configuração.",
            )

    async def executar_com_envelope(
        self,
        *,
        nome: str,
        grupo: str,
        fonte: str,
        corrotina: Callable[[], Awaitable[tuple[dict[str, Any], bool, int, bool, list[str]]]],
    ) -> str:
        try:
            self.verificar_permissao_execucao(nome, grupo)
            dados, em_cache, idade_s, contem_ext, avisos = await corrotina()
            env = Envelope.sucesso(
                fonte=fonte,
                dados=dados,
                em_cache=em_cache,
                idade_segundos=idade_s,
                contem_texto_externo=contem_ext,
                avisos=avisos,
            )
            return texto_do_envelope(env)
        except ErroUfc as exc:
            return texto_do_envelope(Envelope.falha(fonte=fonte, erro=exc))
        except Exception as exc:
            erro_int = ErroUfc(
                CodigoErro.ERRO_INTERNO,
                f"Falha inesperada em {nome}: {type(exc).__name__}",
            )
            return texto_do_envelope(Envelope.falha(fonte=fonte, erro=erro_int))
