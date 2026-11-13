"""Modelos de dados para páginas públicas de cursos de graduação no SIGAA (`si3.ufc.br/sigaa/public`)."""

from __future__ import annotations

from ufc_mcp.nucleo.modelos_base import BaseModel, Field


class PeriodoCalendarioCurso(BaseModel):
    semestre: str
    inicio: str
    fim: str
    evento: str


class CalendarioCursoPublico(BaseModel):
    id_curso: int
    curso: str
    periodos: list[PeriodoCalendarioCurso] = Field(default_factory=list)


class ComponenteCurriculoPublico(BaseModel):
    codigo: str
    nome: str
    carga_horaria_h: int
    periodo_sugerido: int
    obrigatoria: bool = True
    pre_requisitos: list[str] = Field(default_factory=list)
    co_requisitos: list[str] = Field(default_factory=list)
