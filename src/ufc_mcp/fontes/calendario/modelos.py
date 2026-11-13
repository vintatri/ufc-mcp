"""Modelos de dados do Calendário Universitário oficial da UFC."""

from __future__ import annotations

from ufc_mcp.nucleo.modelos_base import BaseModel, Field


class EventoCalendario(BaseModel):
    inicio: str  # AAAA-MM-DD
    fim: str     # AAAA-MM-DD
    descricao: str
    marcadores: list[str] = Field(default_factory=list)
    eh_feriado_ou_recesso: bool = False


class ResultadoCalendario(BaseModel):
    ano: int
    eventos: list[EventoCalendario] = Field(default_factory=list)
    nao_interpretados: int = 0
