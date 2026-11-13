"""
Interface de Linha de Comando (`cli.py` — Tarefa T08):
Subcomandos: `login`, `logout`, `status`, `servir`, `diagnostico`, `gravar`, `instalar`.
Códigos de saída: 0 ok, 1 erro geral, 2 credencial inválida, 3 SIGAA indisponível,
4 cofre indisponível, 5 vazamento detectado na gravação.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import getpass
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from ufc_mcp.ferramentas import ContextoApp
from ufc_mcp.gravador.gravar import gerar_corpus_sintetico
from ufc_mcp.nucleo.config import Config, caminho_config_toml, salvar_configuracao
from ufc_mcp.nucleo.credenciais import (
    Cofre,
    CofreArquivo,
    CofreSessao,
    CofreSistema,
    Credencial,
)
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.registro import configurar_registro
from ufc_mcp.servidor import AplicacaoServidorUfcMcp


def _perguntar_inteiro(pergunta: str) -> int:
    while True:
        resposta = input(pergunta).strip()
        if resposta.isdigit() and int(resposta) > 0:
            return int(resposta)
        sys.stderr.write("Digite um número inteiro positivo.\n")


def _codigo_saida_para_erro(erro: ErroUfc) -> int:
    if erro.codigo in (CodigoErro.CREDENCIAL_INVALIDA, CodigoErro.SEM_CREDENCIAL, CodigoErro.LOGIN_SUSPENSO):
        return 2
    if erro.codigo in (CodigoErro.SIGAA_INDISPONIVEL, CodigoErro.FONTE_INDISPONIVEL, CodigoErro.TEMPO_ESGOTADO):
        return 3
    if erro.codigo == CodigoErro.COFRE_INDISPONIVEL:
        return 4
    return 1


def construir_parser_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ufc-mcp",
        description="Copiloto Acadêmico MCP com Governança de Dados e Tutoria Fundamentada para a UFC",
    )
    sub = parser.add_subparsers(dest="subcomando", required=True)

    # 1. login
    p_login = sub.add_parser("login", help="Autentica e armazena credenciais ou sessão temporária.")
    p_login.add_argument(
        "--cofre",
        choices=["auto", "sistema", "arquivo"],
        default="auto",
        help="Tipo de cofre de credenciais.",
    )
    p_login.add_argument(
        "--so-sessao",
        action="store_true",
        help="Guarda apenas o cookie temporário da sessão (zero senha persistente).",
    )
    # A senha e a frase-mestra NUNCA são aceitas por argumento: ficariam no histórico do shell
    # e na lista de processos. Ambas são lidas por prompt oculto (getpass).
    p_login.add_argument("--usuario", help="Usuário do SIGAA (opcional, pergunta no terminal).")

    # 2. logout
    sub.add_parser("logout", help="Remove credenciais, cookies de sessão e limpa caches.")
    p_conf = sub.add_parser(
        "configurar", help="Grava curso e restaurante (pergunta o que faltar)."
    )
    p_conf.add_argument("--curso", type=int, default=None, help="Id numérico do curso.")
    p_conf.add_argument(
        "--restaurante",
        type=str,
        default=None,
        help="Nome do restaurante universitário (ex.: Fortaleza, Pici, Quixadá).",
    )

    # 3. status
    p_status = sub.add_parser("status", help="Exibe o estado do cofre, sessão e limites de taxa.")
    p_status.add_argument("--json", action="store_true", help="Saída em JSON.")

    # 4. servir
    p_servir = sub.add_parser("servir", help="Inicia o servidor MCP via transporte stdio.")
    p_servir.add_argument(
        "--perfil",
        choices=["completo", "essencial"],
        default=None,
        help="Perfil do catálogo de ferramentas (35 em completo, 15 em essencial).",
    )

    # 5. diagnostico
    p_diag = sub.add_parser("diagnostico", help="Executa os canários de saúde estrutural (C1 a C8).")
    p_diag.add_argument(
        "--fontes",
        nargs="*",
        default=None,
        help="Fontes a testar (ru, calendario, noticias, sigaa_publico, sigaa).",
    )
    p_diag.add_argument("--json", action="store_true", help="Saída em formato JSON.")

    # 6. gravar
    p_gravar = sub.add_parser("gravar", help="Grava e anonimiza páginas de teste e gabaritos.")
    p_gravar.add_argument("--telas", nargs="*", default=None)
    p_gravar.add_argument(
        "--conjunto",
        choices=["dev", "validacao", "ambos"],
        default="ambos",
    )
    p_gravar.add_argument(
        "--sintetico",
        action="store_true",
        help="Gera os conjuntos dev e validacao (hold-out) sintéticos de referência.",
    )
    p_gravar.add_argument(
        "--destino",
        type=Path,
        default=Path("tests"),
        help="Diretório raiz de testes onde páginas e gabaritos serão gravados.",
    )

    # 7. instalar
    p_inst = sub.add_parser("instalar", help="Gera a configuração JSON para clientes MCP.")
    p_inst.add_argument(
        "--cliente",
        choices=["claude-desktop", "claude-code", "cursor", "vscode", "gemini"],
        default="claude-desktop",
    )
    p_inst.add_argument(
        "--perfil",
        choices=["completo", "essencial"],
        default="completo",
        help="Perfil de ferramentas exposto ao cliente MCP.",
    )
    p_inst.add_argument(
        "--aplicar",
        action="store_true",
        help="Grava (com backup) o bloco no arquivo de configuração do cliente.",
    )

    return parser


def _entrada_servidor(perfil: str) -> dict[str, object]:
    """Comando absoluto e independente do diretório atual do cliente MCP."""
    return {
        "type": "stdio",
        "command": sys.executable,
        "args": ["-m", "ufc_mcp", "servir", "--perfil", perfil],
        "env": {},
    }


def _caminho_config_cliente(cliente: str) -> Path:
    casa = Path.home()
    if cliente == "claude-desktop":
        if sys.platform == "darwin":
            return casa / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        if os.name == "nt":
            return Path(os.environ.get("APPDATA", str(casa))) / "Claude" / "claude_desktop_config.json"
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(casa / ".config")))
        return base / "Claude" / "claude_desktop_config.json"
    if cliente == "claude-code":
        return casa / ".claude.json"
    if cliente == "cursor":
        return casa / ".cursor" / "mcp.json"
    if cliente == "gemini":
        return casa / ".gemini" / "settings.json"
    return Path.cwd() / ".vscode" / "mcp.json"


def _bloco_cliente(cliente: str, perfil: str) -> dict[str, object]:
    entrada = _entrada_servidor(perfil)
    if cliente == "vscode":
        return {"servers": {"ufc-mcp": entrada}}
    return {"mcpServers": {"ufc-mcp": entrada}}


def _aplicar_config_cliente(cliente: str, perfil: str) -> Path:
    destino = _caminho_config_cliente(cliente)
    destino.parent.mkdir(parents=True, exist_ok=True)
    dados: dict[str, object] = {}
    if destino.exists():
        try:
            lido = json.loads(destino.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ErroUfc(
                CodigoErro.PARAMETRO_INVALIDO,
                f"Não foi possível ler {destino}: {exc}. Nada foi alterado.",
            ) from exc
        if isinstance(lido, dict):
            dados = lido
        destino.with_suffix(destino.suffix + ".bak").write_text(
            destino.read_text(encoding="utf-8"), encoding="utf-8"
        )

    chave = "servers" if cliente == "vscode" else "mcpServers"
    existentes = dados.get(chave)
    if not isinstance(existentes, dict):
        existentes = {}
    existentes["ufc-mcp"] = _entrada_servidor(perfil)
    dados[chave] = existentes
    destino.write_text(json.dumps(dados, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return destino


def main(argv: Sequence[str] | None = None) -> int:
    parser = construir_parser_cli()
    args = parser.parse_args(argv)
    try:
        cfg = Config.carregar()
    except (ErroUfc, ValueError, ValidationError) as exc:
        dica = (
            "Corrija o valor em UFC_MCP_RESTAURANTE ou em config.toml, "
            "ou rode: ufc-mcp configurar --restaurante <nome>"
        )
        curso_env = os.environ.get("UFC_MCP_ID_CURSO_PUBLICO", "")
        if not isinstance(exc, ErroUfc) and curso_env and not curso_env.strip().lstrip("-").isdigit():
            dica = "UFC_MCP_ID_CURSO_PUBLICO deve ser um número inteiro"
        detalhe = exc.mensagem if isinstance(exc, ErroUfc) else str(exc)
        sys.stderr.write(f"Configuração inválida: {detalhe}\n{dica}\n")
        return 1
    configurar_registro(cfg.nivel_log)

    try:
        if args.subcomando == "servir":
            if args.perfil:
                cfg.perfil = args.perfil
            app = AplicacaoServidorUfcMcp(ContextoApp(config=cfg))
            asyncio.run(app.servir_stdio())
            return 0

        if args.subcomando == "status":
            ctx = ContextoApp(config=cfg)
            res_str = asyncio.run(
                AplicacaoServidorUfcMcp(ctx).chamar_ferramenta("status", {})
            )
            sys.stdout.write(res_str + "\n")
            sys.stdout.flush()
            return 0

        if args.subcomando == "configurar":
            curso = args.curso
            restaurante = args.restaurante
            if curso is None and restaurante is None:
                curso = _perguntar_inteiro("Id numérico do seu curso: ")
                restaurante = input(
                    "Restaurante universitário (ex.: Fortaleza, Pici, Quixadá, Sobral): "
                ).strip()
            salvar_configuracao(cfg, curso=curso, restaurante=restaurante)
            sys.stderr.write(f"Configuração salva em {caminho_config_toml()}.\n")
            return 0

        if args.subcomando == "logout":
            ctx = ContextoApp(config=cfg)
            with contextlib.suppress(ErroUfc):
                ctx.cofre.limpar()
            ctx.cache_pessoal.limpar()
            ctx.cache_publico.limpar()
            ctx.sessao.limpar_suspensao()
            sys.stderr.write("Credenciais, sessão e caches apagados com sucesso.\n")
            return 0

        if args.subcomando == "login":
            usuario = args.usuario or input("Usuário SIGAA: ").strip()
            senha = getpass.getpass("Senha SIGAA: ")
            cofre_escolhido: Cofre
            if args.so_sessao:
                cofre_escolhido = CofreSessao(
                    arquivo_sessao_fallback=cfg.pasta_config / "sessao_efemera.json"
                )
                ctx = ContextoApp(config=cfg, cofre=cofre_escolhido)
                asyncio.run(ctx.sessao.autenticar_com_credencial_efemera(usuario, senha))
                sys.stderr.write("Sessão temporária iniciada (--so-sessao). Zero senha persistida.\n")
                return 0

            if args.cofre == "arquivo":
                frase = getpass.getpass("Frase-mestra do CofreArquivo: ")
                cofre_escolhido = CofreArquivo(cfg.pasta_config / "cofre.bin", frase)
            elif args.cofre == "sistema":
                cofre_escolhido = CofreSistema()
            else:
                cofre_escolhido = CofreSistema()

            credencial = Credencial(usuario=usuario, senha=senha)
            try:
                cofre_escolhido.salvar_credencial(credencial)
            except ErroUfc as exc:
                if args.cofre != "auto" or exc.codigo != CodigoErro.COFRE_INDISPONIVEL:
                    raise
                sys.stderr.write(
                    "Chaveiro do sistema indisponível; usando cofre em arquivo criptografado.\n"
                )
                frase = getpass.getpass("Frase-mestra do CofreArquivo: ")
                cofre_escolhido = CofreArquivo(cfg.pasta_config / "cofre.bin", frase)
                cofre_escolhido.salvar_credencial(credencial)
            sys.stderr.write(f"Credencial armazenada em {cofre_escolhido.descricao()}.\n")
            return 0

        if args.subcomando == "diagnostico":
            ctx = ContextoApp(config=cfg)
            app = AplicacaoServidorUfcMcp(ctx)
            res_str = asyncio.run(
                app.chamar_ferramenta("diagnostico", {"fontes": args.fontes})
            )
            sys.stdout.write(res_str + "\n")
            sys.stdout.flush()
            dados_env = json.loads(res_str)
            if not dados_env.get("ok") or not dados_env.get("dados", {}).get("todos_ok", False):
                return 1
            return 0

        if args.subcomando == "gravar":
            if args.sintetico:
                codigo = gerar_corpus_sintetico(args.destino, conjunto=args.conjunto)
                return codigo
            sys.stderr.write("Use `ufc-mcp gravar --sintetico` para gerar os conjuntos dev/validacao.\n")
            return 0

        if args.subcomando == "instalar":
            bloco = _bloco_cliente(args.cliente, args.perfil)
            if args.aplicar:
                destino = _aplicar_config_cliente(args.cliente, args.perfil)
                sys.stderr.write(f"Configuração aplicada em {destino}.\n")
            sys.stdout.write(json.dumps(bloco, indent=2, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            return 0

    except ErroUfc as exc:
        sys.stderr.write(f"Erro [{exc.codigo.value}]: {exc.mensagem}\n")
        return _codigo_saida_para_erro(exc)
    except Exception as exc:
        sys.stderr.write(f"Erro inesperado: {exc}\n")
        return 1

    return 0
