"""
Auditoria estática AST (T07): comprova que nenhum arquivo fora de `sessao_sigaa.py`
e `http.py` invoca `post_form` ou `post_form_binario`, e que nenhum módulo em
`ferramentas/` ou `servicos/` importa `httpx` ou `bs4`.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

RAIZ_SRC = Path(__file__).resolve().parents[2] / "src" / "ufc_mcp"


class TestIsolamentoArquiteturalAst(unittest.TestCase):
    def test_post_form_restrito_a_sessao_sigaa(self) -> None:
        for arq in RAIZ_SRC.rglob("*.py"):
            if arq.name in ("http.py", "sessao_sigaa.py"):
                continue
            arvore = ast.parse(arq.read_text(encoding="utf-8"))
            for node in ast.walk(arvore):
                if isinstance(node, ast.Attribute) and node.attr in (
                    "post_form",
                    "post_form_binario",
                ):
                    self.fail(
                        f"Chamada proibida a `{node.attr}` encontrada fora de sessao_sigaa.py: {arq}"
                    )

    def test_ferramentas_nao_importam_httpx_nem_bs4(self) -> None:
        for sub in ("ferramentas",):
            for arq in (RAIZ_SRC / sub).rglob("*.py"):
                arvore = ast.parse(arq.read_text(encoding="utf-8"))
                for node in ast.walk(arvore):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self.assertNotIn(alias.name.split(".")[0], ("httpx", "bs4"))
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        self.assertNotIn(node.module.split(".")[0], ("httpx", "bs4"))
