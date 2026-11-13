"""
Calculadora Regimental de Notas e Avaliação Final da UFC
(Arts. 111, 112 e 114 do Regimento Geral da UFC).

A média parcial (MP) é a média ARITMÉTICA simples das avaliações progressivas; o Regimento
não prevê pesos, portanto não há suporte a média ponderada. Notas e médias são expressas
com 1 casa decimal (Art. 111).
"""

from __future__ import annotations

import math
from typing import Literal

from ufc_mcp.nucleo.modelos_base import BaseModel

SituacaoRegimentalNotas = Literal[
    "APROVADO_POR_MEDIA",
    "EM_CURSO_APROVAVEL_POR_MEDIA",
    "EM_CURSO_EXIGE_AF",
    "AGUARDANDO_AVALIACAO_FINAL",
    "REPROVADO_POR_NOTA",
    "SEM_NOTAS_LANCADAS",
]


class DiagnosticoNotasUfc(BaseModel):
    notas_lancadas: list[float]
    total_unidades_previstas: int
    media_parcial_atual: float | None
    situacao_regimental: SituacaoRegimentalNotas
    nota_necessaria_por_unidade_para_media_7: float | None
    nota_necessaria_por_unidade_para_af_4: float | None
    nota_minima_avaliacao_final: float | None
    regra_aplicada: str = (
        "Art. 114 do Regimento Geral da UFC "
        "(MP >= 7,0 aprova; 4,0 <= MP < 7,0 exige AF com AF >= 4,0 e (MP + AF)/2 >= 5,0; MP < 4,0 reprova)"
    )


def _arred1(x: float) -> float:
    return round(x + 1e-9, 1)


def _teto1(x: float) -> float:
    """Arredonda para cima a 1 casa (nota mínima exigida nunca fica aquém do necessário)."""
    return math.ceil(round(x, 6) * 10) / 10


def diagnosticar_notas_ufc(
    notas_lancadas: list[float],
    *,
    total_unidades_previstas: int = 3,
    media_parcial_informada: float | None = None,
) -> DiagnosticoNotasUfc:
    """
    Aplica as fórmulas do Art. 114 do Regimento Geral da UFC (média aritmética simples):
    - Aprovação direta: MP >= 7,0
    - Habilitação para AF: 4,0 <= MP < 7,0 com AF_min = max(4.0, 10.0 - MP)
    - Reprovação direta (sem AF): MP < 4,0
    Valores exibidos arredondados a 1 casa decimal; a classificação usa a MP já arredondada.
    `media_parcial_informada` (média calculada pelo SIGAA) tem precedência sobre a aritmética local.
    """
    n = max(1, total_unidades_previstas)
    k = len(notas_lancadas)

    if k == 0 and media_parcial_informada is None:
        return DiagnosticoNotasUfc(
            notas_lancadas=[],
            total_unidades_previstas=n,
            media_parcial_atual=None,
            situacao_regimental="SEM_NOTAS_LANCADAS",
            nota_necessaria_por_unidade_para_media_7=7.0,
            nota_necessaria_por_unidade_para_af_4=4.0,
            nota_minima_avaliacao_final=None,
        )

    soma_k = sum(notas_lancadas)
    mp_atual = (
        _arred1(media_parcial_informada)
        if media_parcial_informada is not None
        else _arred1(soma_k / k)
    )

    if k < n:
        restantes = n - k
        req_7 = max(0.0, _teto1((7.0 * n - soma_k) / restantes))
        req_4 = max(0.0, _teto1((4.0 * n - soma_k) / restantes))
        if req_7 <= 10.0:
            sit: SituacaoRegimentalNotas = "EM_CURSO_APROVAVEL_POR_MEDIA"
        elif req_4 <= 10.0:
            sit = "EM_CURSO_EXIGE_AF"
        else:
            sit = "REPROVADO_POR_NOTA"

        return DiagnosticoNotasUfc(
            notas_lancadas=notas_lancadas,
            total_unidades_previstas=n,
            media_parcial_atual=mp_atual,
            situacao_regimental=sit,
            nota_necessaria_por_unidade_para_media_7=req_7,
            nota_necessaria_por_unidade_para_af_4=req_4,
            nota_minima_avaliacao_final=None,
        )

    # Todas as unidades previstas já foram lançadas (k >= n)
    if mp_atual >= 7.0:
        return DiagnosticoNotasUfc(
            notas_lancadas=notas_lancadas,
            total_unidades_previstas=n,
            media_parcial_atual=mp_atual,
            situacao_regimental="APROVADO_POR_MEDIA",
            nota_necessaria_por_unidade_para_media_7=0.0,
            nota_necessaria_por_unidade_para_af_4=0.0,
            nota_minima_avaliacao_final=None,
        )

    if mp_atual >= 4.0:
        af_min = max(4.0, _arred1(10.0 - mp_atual))
        return DiagnosticoNotasUfc(
            notas_lancadas=notas_lancadas,
            total_unidades_previstas=n,
            media_parcial_atual=mp_atual,
            situacao_regimental="AGUARDANDO_AVALIACAO_FINAL",
            nota_necessaria_por_unidade_para_media_7=None,
            nota_necessaria_por_unidade_para_af_4=0.0,
            nota_minima_avaliacao_final=af_min,
        )

    return DiagnosticoNotasUfc(
        notas_lancadas=notas_lancadas,
        total_unidades_previstas=n,
        media_parcial_atual=mp_atual,
        situacao_regimental="REPROVADO_POR_NOTA",
        nota_necessaria_por_unidade_para_media_7=None,
        nota_necessaria_por_unidade_para_af_4=None,
        nota_minima_avaliacao_final=None,
    )
