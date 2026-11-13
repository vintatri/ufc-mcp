"""Códigos de erro canônicos e exceção estruturada do ufc-mcp."""

from enum import StrEnum
from typing import Any


class CodigoErro(StrEnum):
    """17 códigos canônicos de erro do ufc-mcp."""

    SEM_CREDENCIAL = "SEM_CREDENCIAL"
    CREDENCIAL_INVALIDA = "CREDENCIAL_INVALIDA"
    LOGIN_SUSPENSO = "LOGIN_SUSPENSO"
    COFRE_INDISPONIVEL = "COFRE_INDISPONIVEL"
    SIGAA_INDISPONIVEL = "SIGAA_INDISPONIVEL"
    TEMPO_ESGOTADO = "TEMPO_ESGOTADO"
    SESSAO_EXPIRADA = "SESSAO_EXPIRADA"
    LAYOUT_MUDOU = "LAYOUT_MUDOU"
    ACAO_BLOQUEADA = "ACAO_BLOQUEADA"
    PARAMETRO_INVALIDO = "PARAMETRO_INVALIDO"
    NAO_ENCONTRADO = "NAO_ENCONTRADO"
    FONTE_INDISPONIVEL = "FONTE_INDISPONIVEL"
    LIMITE_DE_REQUISICOES = "LIMITE_DE_REQUISICOES"
    FUNCAO_DESATIVADA = "FUNCAO_DESATIVADA"
    ERRO_INTERNO = "ERRO_INTERNO"
    ACESSO_AUTOMATIZADO_NEGADO = "ACESSO_AUTOMATIZADO_NEGADO"
    CONFIGURACAO_PENDENTE = "CONFIGURACAO_PENDENTE"


SUGESTOES_PADRAO: dict[CodigoErro, str] = {
    CodigoErro.SEM_CREDENCIAL: "Execute `ufc-mcp login` ou `ufc-mcp login --so-sessao` no terminal.",
    CodigoErro.CREDENCIAL_INVALIDA: "Credenciais recusadas pelo SIGAA. Execute `ufc-mcp login` no terminal.",
    CodigoErro.LOGIN_SUSPENSO: "Login suspenso preventivamente após falha. Execute `ufc-mcp login`.",
    CodigoErro.COFRE_INDISPONIVEL: "Chaveiro do SO indisponível. Use `ufc-mcp login --cofre arquivo` ou `--so-sessao`.",
    CodigoErro.SIGAA_INDISPONIVEL: "O portal SIGAA está temporariamente indisponível. Tente novamente mais tarde.",
    CodigoErro.TEMPO_ESGOTADO: "A requisição excedeu o tempo limite. Tente novamente em instantes.",
    CodigoErro.SESSAO_EXPIRADA: "A sessão no SIGAA expirou. Execute `ufc-mcp login --so-sessao` ou repita a consulta.",
    CodigoErro.LAYOUT_MUDOU: "A estrutura HTML da página mudou. Execute `ufc-mcp diagnostico` e consulte `docs/reparo.md`.",
    CodigoErro.ACAO_BLOQUEADA: "Operação bloqueada pela barreira de segurança somente leitura (`nucleo/risco.py`).",
    CodigoErro.PARAMETRO_INVALIDO: "Verifique o formato e os limites dos parâmetros informados.",
    CodigoErro.NAO_ENCONTRADO: "O recurso ou registro solicitado não foi encontrado.",
    CodigoErro.FONTE_INDISPONIVEL: "A fonte externa está indisponível e não há cópia em cache recente.",
    CodigoErro.LIMITE_DE_REQUISICOES: "Teto de requisições atingido para proteger o servidor da UFC. Aguarde alguns segundos.",
    CodigoErro.FUNCAO_DESATIVADA: "Esta ferramenta foi desativada na configuração local do usuário.",
    CodigoErro.CONFIGURACAO_PENDENTE: "Dados do primeiro uso ainda não informados. Pergunte ao estudante e chame `configurar`.",
    CodigoErro.ERRO_INTERNO: "Erro interno inesperado. Consulte o log local sanitizado para diagnóstico.",
    CodigoErro.ACESSO_AUTOMATIZADO_NEGADO: (
        "O SIGAA da UFC recusou o login por identificar acesso por aplicativo externo "
        "(\"Tentativa de acesso por aplicativo externo. Operação negada!\"). Não é senha errada nem "
        "mudança de layout. As ferramentas que exigem login ficam indisponíveis e novas tentativas "
        "foram suspensas; as fontes públicas (RU, calendário, notícias) seguem funcionando. "
        "Para liberar a suspensão, execute `ufc-mcp login`."
    ),
}


class ErroUfc(Exception):
    """Exceção tipada de domínio convertida automaticamente em Envelope de erro."""

    def __init__(
        self,
        codigo: CodigoErro,
        mensagem: str,
        *,
        sugestao: str | None = None,
        detalhes: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.sugestao = sugestao or SUGESTOES_PADRAO.get(codigo, "")
        self.detalhes = detalhes or {}
