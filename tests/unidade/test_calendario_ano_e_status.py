"""Ano detectado no calendário e `status` sem chaveiro."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from ufc_mcp.ferramentas import ContextoApp
from ufc_mcp.fontes.calendario.parser import parse_calendario_ufc
from ufc_mcp.nucleo.config import Config
from ufc_mcp.nucleo.credenciais import CofreSistema
from ufc_mcp.servidor import AplicacaoServidorUfcMcp


def _mes(nome: str, ano: int, dia: int) -> str:
    return (
        f"<h3>{nome} de {ano}</h3>"
        f'<table class="category"><tr class="item"><td class="cell">{dia}</td>'
        f'<td class="cell">Evento de {nome}</td></tr></table>'
    )


def test_ano_detectado_ignora_janeiro_do_ano_seguinte() -> None:
    html = (
        "<html><body>"
        + _mes("Janeiro", 2026, 5)
        + _mes("Fevereiro", 2026, 3)
        + _mes("Dezembro", 2026, 10)
        + _mes("Janeiro", 2027, 4)
        + "</body></html>"
    )
    assert parse_calendario_ufc(html).ano == 2026


def test_ano_mais_frequente_sem_ano_padrao() -> None:
    html = (
        "<html><body>"
        + _mes("Janeiro", 2025, 5)
        + _mes("Fevereiro", 2025, 3)
        + _mes("Janeiro", 2026, 4)
        + "</body></html>"
    )
    assert parse_calendario_ufc(html, ano_padrao=2030).ano == 2025


class _KeyringSemBackend:
    def get_password(self, *_a: object) -> None:
        from keyring.errors import NoKeyringError

        raise NoKeyringError("sem backend")

    set_password = get_password


def test_ufc_status_sem_chaveiro() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(
            curso=657468,
            restaurante=1,
            pasta_config=Path(tmp) / "cfg",
            pasta_cache=Path(tmp) / "cache",
            pasta_documentos=Path(tmp) / "docs",
        )
        ctx = ContextoApp(config=cfg, cofre=CofreSistema(backend_keyring=_KeyringSemBackend()))
        app = AplicacaoServidorUfcMcp(ctx)
        env = json.loads(asyncio.run(app.chamar_ferramenta("status", {})))
    assert env["ok"] is True
    assert env["dados"]["cofre"]["estado"] == "chaveiro_indisponivel"
    assert "--so-sessao" in env["dados"]["cofre"]["sugestao"]
