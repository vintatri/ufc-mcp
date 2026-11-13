"""Ferramentas de Diagnóstico e Metadados (`status`, `diagnostico`)."""

from __future__ import annotations

from ufc_mcp.ferramentas import ContextoApp, DefinicaoFerramenta
from ufc_mcp.fontes.ru.resolucao import resolver_restaurante
from ufc_mcp.nucleo.config import salvar_configuracao
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.servicos.diagnostico import executar_diagnostico_canarios


def construir_ferramentas_meta(ctx: ContextoApp) -> list[DefinicaoFerramenta]:
    async def status() -> str:
        """Retorna estado do cofre de credenciais, estado da sessão no SIGAA, contadores de limite de taxa e perfil de ferramentas ativo."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            cofre_info: dict[str, object] = {}
            try:
                cofre_info["estado"] = ctx.cofre.estado()
            except Exception:
                cofre_info["estado"] = "chaveiro_indisponivel"
            try:
                cofre_info["descricao"] = ctx.cofre.descricao()
            except Exception:
                cofre_info["descricao"] = "Cofre indisponível"
            if cofre_info["estado"] == "chaveiro_indisponivel":
                cofre_info["sugestao"] = (
                    "Chaveiro do sistema indisponível: use `ufc-mcp login --so-sessao` "
                    "ou o cofre em arquivo criptografado (`--cofre arquivo`)."
                )
            dados: dict[str, object] = {
                "versao": "0.9.0",
                "cofre": cofre_info,
                "sessao_sigaa": {
                    "logado": ctx.sessao.logado,
                    "ultimo_login": ctx.sessao.ultimo_login,
                    "suspenso": ctx.sessao.esta_suspenso(),
                    "motivo_suspensao": ctx.sessao.motivo_suspensao(),
                    "ultima_view_ativa": list(ctx.sessao.ultima_view_ativa),
                },
                "limites_taxa": ctx.http.contadores_atuais(),
                "perfil": ctx.config.perfil,
                "total_ferramentas_ativas": len(ctx.ferramentas_registradas),
                "identificadores": ctx.config.identificadores,
                "pendentes": ctx.config.pendentes(),
            }
            return dados, False, 0, False, []

        return await ctx.executar_com_envelope(
            nome="status", grupo="meta", fonte="ufc_mcp:meta", corrotina=_impl
        )

    async def diagnostico(fontes: list[str] | None = None) -> str:
        """Executa os canários de saúde e integridade estrutural (C1 a C8) para verificar se o layout das fontes públicas e do SIGAA permanece compatível."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            relatorio = await executar_diagnostico_canarios(
                ru=ctx.ru,
                calendario=ctx.calendario,
                noticias=ctx.noticias,
                sigaa=ctx.sigaa,
                fontes_filtro=fontes,
            )
            return relatorio, False, 0, False, []

        return await ctx.executar_com_envelope(
            nome="diagnostico", grupo="meta", fonte="ufc_mcp:diagnostico", corrotina=_impl
        )

    async def configurar(curso: int | None = None, restaurante: str | None = None) -> str:
        """Primeiro uso: grava o id numérico do seu curso (o mesmo do calendário público do SIGAA) e o nome do restaurante universitário (ex.: Fortaleza, Pici, Quixadá, Sobral). Pergunte esses dados ao estudante antes de chamar; não invente valores."""

        async def _impl() -> tuple[dict[str, object], bool, int, bool, list[str]]:
            if curso is None and restaurante is None:
                raise ErroUfc(CodigoErro.PARAMETRO_INVALIDO, "Informe o curso, o restaurante ou ambos.")
            if curso is not None and curso <= 0:
                raise ErroUfc(CodigoErro.PARAMETRO_INVALIDO, "O curso deve ser um número positivo.")
            if restaurante is not None:
                resolver_restaurante(restaurante)
            salvos = salvar_configuracao(ctx.config, curso=curso, restaurante=restaurante)
            return (
                {"salvo": salvos, "pendentes": ctx.config.pendentes()},
                False,
                0,
                False,
                [],
            )

        return await ctx.executar_com_envelope(
            nome="configurar", grupo="meta", fonte="ufc_mcp:configurar", corrotina=_impl
        )

    return [
        DefinicaoFerramenta(
            nome="status",
            grupo="meta",
            descricao=status.__doc__ or "",
            funcao=status,
        ),
        DefinicaoFerramenta(
            nome="diagnostico",
            grupo="meta",
            descricao=diagnostico.__doc__ or "",
            funcao=diagnostico,
        ),
        DefinicaoFerramenta(
            nome="configurar",
            grupo="meta",
            descricao=configurar.__doc__ or "",
            funcao=configurar,
            anotacoes={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
        ),
    ]
