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

from ufc_mcp.nucleo.modelos_base import BaseModel, Field

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
    media_parcial_atual: float | None  # arredondada, apenas para exibição
    media_parcial_exata: float | None = None  # sem arredondar; usada na classificação
    situacao_regimental: SituacaoRegimentalNotas
    nota_necessaria_por_unidade_para_media_7: float | None
    nota_necessaria_por_unidade_para_af_4: float | None
    nota_minima_avaliacao_final: float | None
    total_unidades_presumido: bool = False
    avisos: list[str] = Field(default_factory=list)
    regra_aplicada: str = (
        "Art. 114 do Regimento Geral da UFC "
        "(MP >= 7,0 aprova; 4,0 <= MP < 7,0 exige AF com AF >= 4,0 e (MP + AF)/2 >= 5,0; MP < 4,0 reprova)"
    )


LIMIAR_AVISO_BORDA = 0.05
AVISO_BORDA = "valor no limite — confirme no SIGAA"
AVISO_UNIDADES_PRESUMIDAS = (
    "número de unidades avaliativas não informado pelo SIGAA; presumido 3 — confirme no SIGAA"
)

ResultadoAposAF = Literal["APROVADO_APOS_AF", "REPROVADO_APOS_AF"]


def avaliar_resultado_apos_af(mp: float, af: float) -> ResultadoAposAF:
    """
    Resultado após a Avaliação Final (Regimento Geral da UFC, Art. 114 §2): aprovado se
    AF >= 4,0 e (MP + AF)/2 >= 5,0. Usa os valores sem arredondar (tolerância só de ponto flutuante).
    Aplica-se a quem fez AF (4,0 <= MP < 7,0).
    """
    if af >= 4.0 - 1e-9 and (mp + af) / 2.0 >= 5.0 - 1e-9:
        return "APROVADO_APOS_AF"
    return "REPROVADO_APOS_AF"


def _avisos_borda(mp: float, *, informada: bool) -> list[str]:
    """Avisa quando a MP está a menos de 0,05 de um limiar (4,0 ou 7,0)."""
    for limiar in (4.0, 7.0):
        dist = abs(mp - limiar)
        if dist < LIMIAR_AVISO_BORDA and (informada or dist > 1e-9):
            return [AVISO_BORDA]
    return []


def _arred1(x: float) -> float:
    return round(x + 1e-9, 1)


def _teto1(x: float) -> float:
    """Arredonda para cima a 1 casa (nota mínima exigida nunca fica aquém do necessário)."""
    return math.ceil(round(x, 6) * 10) / 10


def _diagnosticar_interno(
    notas_lancadas: list[float],
    *,
    total_unidades_previstas: int | None = None,
    media_parcial_informada: float | None = None,
) -> DiagnosticoNotasUfc:
    """
    Aplica as fórmulas do Art. 114 do Regimento Geral da UFC (média aritmética simples):
    - Aprovação direta: MP >= 7,0
    - Habilitação para AF: 4,0 <= MP < 7,0 com AF_min = max(4.0, 10.0 - MP)
    - Reprovação direta (sem AF): MP < 4,0
    Valores exibidos arredondados a 1 casa decimal; a classificação usa a MP SEM arredondar
    (6,95 exibe 7,0, mas NÃO é aprovação direta). Se a MP está a menos de 0,05 de 4,0 ou 7,0,
    inclui o aviso "valor no limite — confirme no SIGAA".
    `media_parcial_informada` (média calculada pelo SIGAA) tem precedência sobre a aritmética local.
    `total_unidades_previstas=None` presume 3 unidades e avisa.
    """
    presumido = total_unidades_previstas is None
    n = max(1, 3 if total_unidades_previstas is None else total_unidades_previstas)
    avisos_base = [AVISO_UNIDADES_PRESUMIDAS] if presumido else []
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
            total_unidades_presumido=presumido,
            avisos=avisos_base,
        )

    soma_k = sum(notas_lancadas)
    mp_exata = media_parcial_informada if media_parcial_informada is not None else soma_k / k
    mp_atual = _arred1(mp_exata)  # apenas exibição
    avisos = avisos_base + _avisos_borda(mp_exata, informada=media_parcial_informada is not None)

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
            total_unidades_presumido=presumido,
            avisos=avisos,
        )

    # Todas as unidades previstas já foram lançadas (k >= n)
    if mp_exata >= 7.0 - 1e-9:
        return DiagnosticoNotasUfc(
            notas_lancadas=notas_lancadas,
            total_unidades_previstas=n,
            media_parcial_atual=mp_atual,
            situacao_regimental="APROVADO_POR_MEDIA",
            nota_necessaria_por_unidade_para_media_7=0.0,
            nota_necessaria_por_unidade_para_af_4=0.0,
            nota_minima_avaliacao_final=None,
            total_unidades_presumido=presumido,
            avisos=avisos,
        )

    if mp_exata >= 4.0 - 1e-9:
        af_min = max(4.0, _teto1(10.0 - mp_exata))
        return DiagnosticoNotasUfc(
            notas_lancadas=notas_lancadas,
            total_unidades_previstas=n,
            media_parcial_atual=mp_atual,
            situacao_regimental="AGUARDANDO_AVALIACAO_FINAL",
            nota_necessaria_por_unidade_para_media_7=None,
            nota_necessaria_por_unidade_para_af_4=0.0,
            nota_minima_avaliacao_final=af_min,
            total_unidades_presumido=presumido,
            avisos=avisos,
        )

    return DiagnosticoNotasUfc(
        notas_lancadas=notas_lancadas,
        total_unidades_previstas=n,
        media_parcial_atual=mp_atual,
        situacao_regimental="REPROVADO_POR_NOTA",
        nota_necessaria_por_unidade_para_media_7=None,
        nota_necessaria_por_unidade_para_af_4=None,
        nota_minima_avaliacao_final=None,
        total_unidades_presumido=presumido,
        avisos=avisos,
    )


def diagnosticar_notas_ufc(
    notas_lancadas: list[float],
    *,
    total_unidades_previstas: int | None = None,
    media_parcial_informada: float | None = None,
) -> DiagnosticoNotasUfc:
    """Ver `_diagnosticar_interno`: classifica pela MP sem arredondar (arredonda só para exibir)."""
    diag = _diagnosticar_interno(
        notas_lancadas,
        total_unidades_previstas=total_unidades_previstas,
        media_parcial_informada=media_parcial_informada,
    )
    if media_parcial_informada is not None:
        diag.media_parcial_exata = media_parcial_informada
    elif notas_lancadas:
        diag.media_parcial_exata = sum(notas_lancadas) / len(notas_lancadas)
    return diag
