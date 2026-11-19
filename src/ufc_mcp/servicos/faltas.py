"""
Calculadora Regulamentar de Frequência e Faltas da UFC
(Art. 113 do Regimento Geral da UFC — mínimo de 75% de presença obrigatória).
"""

from __future__ import annotations

import math
from typing import Literal

from ufc_mcp.fontes.sigaa.cliente import ClienteSigaa
from ufc_mcp.nucleo.erros import ErroUfc
from ufc_mcp.nucleo.modelos_base import BaseModel, Field

SeveridadeFaltas = Literal["OK", "ATENCAO", "CRITICO", "INDISPONIVEL"]
SituacaoFaltas = Literal[
    "REGULAR", "ALERTA_LIMITE", "REPROVADO_POR_FALTA", "DADOS_INDISPONIVEIS", "SEM_CARGA_HORARIA"
]


class DiagnosticoFaltasDisciplina(BaseModel):
    id_turma: str
    codigo: str
    nome: str
    carga_horaria_h: int | None
    faltas_registradas_h: int | None
    limite_faltas_h: int | None = Field(
        description="floor(25% da carga horária em horas); None se a carga horária não foi informada"
    )
    restantes_h: int | None
    encontros_2h_restantes: int | None = Field(
        description="ASSUME encontros de 2 h: floor(restantes_h / 2); não reflete aulas de outra duração"
    )
    percentual_presenca_atual: float | None
    percentual_limite_usado: float | None
    severidade: SeveridadeFaltas
    situacao: SituacaoFaltas
    avisos: list[str] = Field(default_factory=list)
    regra_aplicada: str = "Art. 113 do Regimento Geral da UFC (mínimo 75% de frequência; vedado abono de faltas)"


def calcular_faltas_disciplina(
    *,
    id_turma: str,
    codigo: str,
    nome: str,
    carga_horaria_h: int | None,
    faltas_registradas_h: int | None,
    avisos_extras: list[str] | None = None,
) -> DiagnosticoFaltasDisciplina:
    """
    Limite de faltas = floor(25% da carga horária em HORAS) (Art. 113).
    `encontros_2h_restantes` = floor(restantes_h / 2) e ASSUME encontros de 2 h.
    Carga horária ausente/0 -> sem limite (None), situação SEM_CARGA_HORARIA e aviso
    "carga horária não informada" (nunca presume um valor).
    `faltas_registradas_h=None` (leitura falhou) -> situação DADOS_INDISPONIVEIS, nunca "0 faltas".
    """
    avisos = list(avisos_extras or [])
    if faltas_registradas_h is None:
        avisos.append("faltas não puderam ser lidas do SIGAA; situação desconhecida — confirme no SIGAA")
        return DiagnosticoFaltasDisciplina(
            id_turma=id_turma,
            codigo=codigo,
            nome=nome,
            carga_horaria_h=carga_horaria_h or None,
            faltas_registradas_h=None,
            limite_faltas_h=math.floor(0.25 * carga_horaria_h) if carga_horaria_h else None,
            restantes_h=None,
            encontros_2h_restantes=None,
            percentual_presenca_atual=None,
            percentual_limite_usado=None,
            severidade="INDISPONIVEL",
            situacao="DADOS_INDISPONIVEIS",
            avisos=avisos,
        )
    faltas = max(0, faltas_registradas_h)
    if not carga_horaria_h or carga_horaria_h <= 0:
        avisos.append("carga horária não informada; limite de faltas não calculado")
        return DiagnosticoFaltasDisciplina(
            id_turma=id_turma,
            codigo=codigo,
            nome=nome,
            carga_horaria_h=None,
            faltas_registradas_h=faltas,
            limite_faltas_h=None,
            restantes_h=None,
            encontros_2h_restantes=None,
            percentual_presenca_atual=None,
            percentual_limite_usado=None,
            severidade="INDISPONIVEL",
            situacao="SEM_CARGA_HORARIA",
            avisos=avisos,
        )
    ch = carga_horaria_h
    limite = math.floor(0.25 * ch)
    restantes = limite - faltas
    encontros_2h = math.floor(restantes / 2)
    presenca_pct = round(max(0.0, (ch - faltas) / ch * 100.0), 2)
    uso_limite_pct = round((faltas / limite * 100.0) if limite > 0 else 100.0, 2)

    if faltas > limite:
        severidade: SeveridadeFaltas = "CRITICO"
        situacao: SituacaoFaltas = "REPROVADO_POR_FALTA"
    elif uso_limite_pct >= 75.0 or encontros_2h <= 2:
        severidade = "CRITICO"
        situacao = "ALERTA_LIMITE"
    elif uso_limite_pct >= 50.0:
        severidade = "ATENCAO"
        situacao = "ALERTA_LIMITE"
    else:
        severidade = "OK"
        situacao = "REGULAR"

    return DiagnosticoFaltasDisciplina(
        id_turma=id_turma,
        codigo=codigo,
        nome=nome,
        carga_horaria_h=ch,
        faltas_registradas_h=faltas,
        limite_faltas_h=limite,
        restantes_h=restantes,
        encontros_2h_restantes=encontros_2h,
        percentual_presenca_atual=presenca_pct,
        percentual_limite_usado=uso_limite_pct,
        severidade=severidade,
        situacao=situacao,
        avisos=avisos,
    )


async def ler_faltas_turma(
    sigaa: ClienteSigaa, id_turma: str, *, atualizar: bool = False
) -> tuple[int | None, list[str]]:
    """
    Lê as faltas (horas) de uma turma em Notas e Frequência. Devolve (faltas, avisos).
    `faltas` é None quando nenhuma leitura forneceu o dado (nunca 0 por falha).
    """
    faltas: int | None = None
    avisos: list[str] = []
    try:
        nt, _, _ = await sigaa.obter_turma_notas(id_turma, atualizar=atualizar)
        if nt.faltas is not None:
            faltas = nt.faltas
    except ErroUfc as exc:
        avisos.append(f"Turma {id_turma}: leitura de notas falhou ({exc.codigo}).")
    try:
        fr, _, _ = await sigaa.obter_turma_frequencia(id_turma, atualizar=atualizar)
        faltas = fr.total_faltas_horas if faltas is None else max(faltas, fr.total_faltas_horas)
    except ErroUfc as exc:
        avisos.append(f"Turma {id_turma}: leitura de frequência falhou ({exc.codigo}).")
    return faltas, avisos
