"""Integração: servidor `ufc-mcp servir` consumido pelo cliente oficial do SDK `mcp` via stdio."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

pytest.importorskip("mcp.client.stdio")

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_cliente_oficial_conecta_e_lista_catalogo() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": tmp,
            "XDG_CONFIG_HOME": f"{tmp}/config",
            "XDG_CACHE_HOME": f"{tmp}/cache",
            "XDG_DATA_HOME": f"{tmp}/data",
            "XDG_STATE_HOME": f"{tmp}/state",
        }
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "ufc_mcp", "servir"], env=env
        )
        async with (
            stdio_client(params) as (leitura, escrita),
            ClientSession(leitura, escrita) as sessao,
        ):
            await sessao.initialize()
            ferramentas = await sessao.list_tools()
            assert len(ferramentas.tools) == 36
            recursos = await sessao.list_resources()
            assert {str(r.uri) for r in recursos.resources} >= {
                "ufc://ajuda/ferramentas",
                "ufc://ajuda/privacidade",
            }
            prompts = await sessao.list_prompts()
            assert "meu-dia" in {p.name for p in prompts.prompts}
            status = await sessao.call_tool("status", {})
            assert not status.is_error
