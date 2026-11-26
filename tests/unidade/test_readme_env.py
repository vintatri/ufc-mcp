"""Testes que garantem consistência entre a tabela de variáveis no README.md e Config.carregar."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

from ufc_mcp.nucleo.config import Config

RAIZ_REPO = Path(__file__).resolve().parents[2]


def test_readme_variaveis_ambiente_batem_com_config() -> None:
    readme = (RAIZ_REPO / "README.md").read_text(encoding="utf-8")
    assert "`UFC_MCP_ID_CURSO_PUBLICO`" in readme
    assert "`UFC_MCP_INCLUIR_IDENTIFICADORES`" in readme
    assert "`UFC_MCP_PERFIL_FERRAMENTAS`" in readme
    assert "`UFC_MCP_CURSO`" not in readme
    assert "`UFC_MCP_IDENTIFICADORES`" not in readme
    assert "`UFC_MCP_PERFIL`" not in readme

    # Garante que todas as variáveis UFC_MCP_* da tabela de configuração são lidas em Config.carregar
    secao_cfg = readme.split("## Configuração", 1)[1].split("\n## ", 1)[0]
    vars_tabela = set(re.findall(r"`(UFC_MCP_[A-Z0-9_]+)`", secao_cfg))
    assert vars_tabela >= {
        "UFC_MCP_ID_CURSO_PUBLICO",
        "UFC_MCP_RESTAURANTE",
        "UFC_MCP_INCLUIR_IDENTIFICADORES",
        "UFC_MCP_PERFIL_FERRAMENTAS",
        "UFC_MCP_NIVEL_LOG",
    }

    with tempfile.TemporaryDirectory() as tmp:
        env = {
            "UFC_MCP_ID_CURSO_PUBLICO": "657468",
            "UFC_MCP_RESTAURANTE": "fortaleza",
            "UFC_MCP_INCLUIR_IDENTIFICADORES": "true",
            "UFC_MCP_PERFIL_FERRAMENTAS": "essencial",
            "UFC_MCP_NIVEL_LOG": "DEBUG",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = Config.carregar(Path(tmp) / "nao_existe.toml")
        assert cfg.curso == 657468
        assert cfg.restaurante == "fortaleza"
        assert cfg.identificadores is True
        assert cfg.perfil == "essencial"
        assert cfg.nivel_log == "DEBUG"
