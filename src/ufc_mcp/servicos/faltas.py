"""
Calculadora Regulamentar de Frequência e Faltas da UFC
(Art. 113 do Regimento Geral da UFC — mínimo de 75% de presença obrigatória).
"""

from __future__ import annotations

import math
from typing import Literal

from ufc_mcp.nucleo.modelos_base import BaseModel

SeveridadeFaltas = Literal["OK", "ATENCAO", "CRITICO"]
SituacaoFaltas = Literal["REGULAR", "ALERTA_LIMITE", "REPROVADO_POR_FALTA"]


class DiagnosticoFaltasDisciplina(BaseModel):
    id_turma: str
    codigo: str
    nome: str
    carga_horaria_h: int
    faltas_registradas_h: int
    limite_faltas_h: int
    restantes_h: int
    encontros_2h_restantes: int
    percentual_presenca_atual: float
    percentual_limite_usado: float
    severidade: SeveridadeFaltas
    situacao: SituacaoFaltas
    regra_aplicada: str = "Art. 113 do Regimento Geral da UFC (mínimo 75% de frequência; vedado abono de faltas)"


def calcular_faltas_disciplina(
    *,
    id_turma: str,
    codigo: str,
    nome: str,
    carga_horaria_h: int,
    faltas_registradas_h: int,
) -> DiagnosticoFaltasDisciplina:
    ch = max(16, carga_horaria_h)
    faltas = max(0, faltas_registradas_h)
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
    )
