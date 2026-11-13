"""Configuração tipada do ufc-mcp (TOML + variáveis de ambiente UFC_MCP_*)."""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import field_validator

from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.modelos_base import BaseModel, ConfigDict, Field


def _obter_dir_config() -> Path:
    try:
        from platformdirs import user_config_dir

        return Path(user_config_dir("ufc-mcp"))
    except ImportError:
        base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        return Path(base) / "ufc-mcp"


def _obter_dir_cache() -> Path:
    try:
        from platformdirs import user_cache_dir

        return Path(user_cache_dir("ufc-mcp"))
    except ImportError:
        base = os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
        return Path(base) / "ufc-mcp"


def _obter_dir_documentos() -> Path:
    try:
        from platformdirs import user_documents_dir

        return Path(user_documents_dir()) / "ufc-mcp"
    except ImportError:
        return Path.home() / "Documentos" / "ufc-mcp"


def caminho_config_toml() -> Path:
    """Arquivo config.toml do usuário (fora do repositório)."""
    return _obter_dir_config() / "config.toml"


def _valor_toml(valor: object) -> str:
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, int | float):
        return repr(valor)
    if isinstance(valor, str):
        return json.dumps(valor, ensure_ascii=False)
    if isinstance(valor, list):
        return "[" + ", ".join(_valor_toml(v) for v in valor) + "]"
    raise TypeError(f"Tipo não suportado no config.toml: {type(valor).__name__}")


def salvar_configuracao(
    config: Config, *, curso: int | None = None, restaurante: str | int | None = None
) -> dict[str, int | str]:
    """Grava curso e restaurante no config.toml e atualiza a configuração em uso."""
    caminho = caminho_config_toml()
    dados: dict[str, object] = {}
    if caminho.exists():
        with caminho.open("rb") as f:
            dados = tomllib.load(f)
    alterados: dict[str, int | str] = {}
    if curso is not None:
        alterados["curso"] = curso
    if restaurante is not None:
        from ufc_mcp.fontes.ru.resolucao import slug_restaurante

        slug = slug_restaurante(restaurante)
        if slug is not None:
            alterados["restaurante"] = slug
    dados.update(alterados)
    linhas: list[str] = []
    tabelas: list[tuple[str, dict[str, object]]] = []
    for chave, valor in dados.items():
        if isinstance(valor, dict):
            tabelas.append((chave, valor))
        else:
            linhas.append(f"{chave} = {_valor_toml(valor)}")
    for nome, sub in tabelas:
        linhas += ["", f"[{nome}]"]
        linhas += [f"{k} = {_valor_toml(v)}" for k, v in sub.items()]
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    for chave, valor in alterados.items():
        setattr(config, chave, valor)
    return alterados


class Limites(BaseModel):
    """Parâmetros de acesso educado (Perfil B Estrito — Decisão D6)."""

    model_config = ConfigDict(extra="forbid")

    pausa_minima_s: float = Field(default=2.0, ge=0.5, le=30.0)
    max_por_minuto: int = Field(default=30, ge=1, le=120)
    max_por_hora: int = Field(default=300, ge=10, le=1000)
    max_por_dia: int = Field(default=2000, ge=50, le=5000)
    timeout_s: float = Field(default=60.0, ge=2.0, le=120.0)


class Config(BaseModel):
    """Configuração global imutável do servidor ufc-mcp."""

    model_config = ConfigDict(extra="forbid")

    limites: Limites = Field(default_factory=Limites)
    restaurante: str | None = Field(default=None)
    curso: int | None = Field(default=None)
    identificadores: bool = Field(default=False)
    perfil: Literal["completo", "essencial"] = Field(default="completo")
    pasta_config: Path = Field(default_factory=_obter_dir_config)
    pasta_cache: Path = Field(default_factory=_obter_dir_cache)
    pasta_documentos: Path = Field(default_factory=_obter_dir_documentos)
    nivel_log: str = Field(default="INFO")
    desativadas: list[str] = Field(default_factory=list)
    grupos_desativados: list[str] = Field(default_factory=list)
    user_agent: str = Field(
        default="ufc-mcp/0.9 (cliente pessoal de estudante da UFC; leitura da propria conta; projeto academico de codigo aberto)",
        description="User-Agent enviado nas requisições HTTP ao SIGAA e outras fontes.",
    )

    @field_validator("restaurante", mode="before")
    @classmethod
    def _normalizar_restaurante(cls, valor: object) -> object:
        if valor is None:
            return None
        from ufc_mcp.fontes.ru.resolucao import slug_restaurante

        if isinstance(valor, str | int):
            return slug_restaurante(valor)
        return valor

    def pendentes(self) -> list[str]:
        """Campos obrigatórios que o estudante ainda não informou."""
        faltam: list[str] = []
        if self.curso is None:
            faltam.append("curso")
        if self.restaurante is None:
            faltam.append("restaurante")
        return faltam

    def exigir(self, campo: str) -> int:
        """Devolve o valor do campo ou levanta erro orientando o primeiro uso."""
        valor = getattr(self, campo)
        if valor is None:
            raise ErroUfc(
                CodigoErro.CONFIGURACAO_PENDENTE,
                f"Falta informar `{campo}`. Pergunte ao estudante e chame a ferramenta `configurar`.",
                detalhes={"pendentes": self.pendentes()},
            )
        if campo == "restaurante":
            from ufc_mcp.fontes.ru.resolucao import resolver_restaurante

            id_rest = resolver_restaurante(valor)
            assert id_rest is not None
            return id_rest
        return int(valor)

    @classmethod
    def carregar(cls, arquivo_toml: Path | None = None) -> Config:
        """Carrega configuração do arquivo config.toml (se existir) e sobrescreve com UFC_MCP_*."""
        dir_cfg = _obter_dir_config()
        caminho = arquivo_toml or (dir_cfg / "config.toml")
        dados: dict[str, object] = {}
        if caminho.exists():
            with caminho.open("rb") as f:
                dados = tomllib.load(f)

        if "UFC_MCP_RESTAURANTE" in os.environ:
            dados["restaurante"] = os.environ["UFC_MCP_RESTAURANTE"]
        if "UFC_MCP_ID_CURSO_PUBLICO" in os.environ:
            dados["curso"] = int(os.environ["UFC_MCP_ID_CURSO_PUBLICO"])
        if "UFC_MCP_INCLUIR_IDENTIFICADORES" in os.environ:
            val = os.environ["UFC_MCP_INCLUIR_IDENTIFICADORES"].strip().lower()
            dados["identificadores"] = val in {"1", "true", "sim", "yes"}
        if "UFC_MCP_PERFIL_FERRAMENTAS" in os.environ:
            perfil = os.environ["UFC_MCP_PERFIL_FERRAMENTAS"].strip().lower()
            if perfil in {"completo", "essencial"}:
                dados["perfil"] = perfil
        if "UFC_MCP_PASTA_CONFIG" in os.environ:
            dados["pasta_config"] = Path(os.environ["UFC_MCP_PASTA_CONFIG"])
        if "UFC_MCP_PASTA_CACHE" in os.environ:
            dados["pasta_cache"] = Path(os.environ["UFC_MCP_PASTA_CACHE"])
        if "UFC_MCP_PASTA_DOCUMENTOS" in os.environ:
            dados["pasta_documentos"] = Path(os.environ["UFC_MCP_PASTA_DOCUMENTOS"])
        if "UFC_MCP_NIVEL_LOG" in os.environ:
            dados["nivel_log"] = os.environ["UFC_MCP_NIVEL_LOG"].strip().upper()
        if "UFC_MCP_USER_AGENT" in os.environ:
            dados["user_agent"] = os.environ["UFC_MCP_USER_AGENT"].strip()

        return cls.model_validate(dados)
