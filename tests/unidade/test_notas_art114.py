import pytest

from ufc_mcp.servicos.notas_ufc import (
    AVISO_BORDA,
    AVISO_UNIDADES_PRESUMIDAS,
    avaliar_resultado_apos_af,
    diagnosticar_notas_ufc,
)


@pytest.mark.parametrize(
    "notas, kwargs, mp, sit, req7, req4, afmin, presumido, avisos",
    [
        pytest.param(
            [], {}, None, "SEM_NOTAS_LANCADAS", 7.0, 4.0, None, True,
            [AVISO_UNIDADES_PRESUMIDAS], id="sem_notas",
        ),
        pytest.param(
            [7.0, 7.0, 7.0], {"total_unidades_previstas": 3}, 7.0,
            "APROVADO_POR_MEDIA", 0.0, 0.0, None, False, [], id="mp_7_0",
        ),
        pytest.param(
            [6.95, 6.95, 6.95], {"total_unidades_previstas": 3}, 7.0,
            "AGUARDANDO_AVALIACAO_FINAL", None, 0.0, 4.0, False, [AVISO_BORDA],
            id="mp_6_95_borda",
        ),
        pytest.param(
            [4.0, 4.0, 4.0], {"total_unidades_previstas": 3}, 4.0,
            "AGUARDANDO_AVALIACAO_FINAL", None, 0.0, 6.0, False, [], id="mp_4_0",
        ),
        pytest.param(
            [5.0, 5.0, 5.0], {"total_unidades_previstas": 3}, 5.0,
            "AGUARDANDO_AVALIACAO_FINAL", None, 0.0, 5.0, False, [], id="mp_5_0",
        ),
        pytest.param(
            [3.9, 3.9, 3.9], {"total_unidades_previstas": 3}, 3.9,
            "REPROVADO_POR_NOTA", None, None, None, False, [], id="mp_3_9",
        ),
        pytest.param(
            [8.0], {"total_unidades_previstas": 3}, 8.0,
            "EM_CURSO_APROVAVEL_POR_MEDIA", 6.5, 2.0, None, False, [],
            id="uma_nota_8",
        ),
        pytest.param(
            [2.0], {"total_unidades_previstas": 3}, 2.0,
            "EM_CURSO_APROVAVEL_POR_MEDIA", 9.5, 5.0, None, False, [],
            id="uma_nota_2",
        ),
        pytest.param(
            [0.0], {"total_unidades_previstas": 3}, 0.0,
            "EM_CURSO_EXIGE_AF", 10.5, 6.0, None, False, [], id="uma_nota_0",
        ),
        pytest.param(
            [6.0, 6.0], {}, 6.0, "EM_CURSO_APROVAVEL_POR_MEDIA", 9.0, 0.0, None,
            True, [AVISO_UNIDADES_PRESUMIDAS], id="duas_notas_unidades_presumidas",
        ),
        pytest.param(
            [], {"media_parcial_informada": 7.2, "total_unidades_previstas": 3},
            7.2, "EM_CURSO_APROVAVEL_POR_MEDIA", 7.0, 4.0, None, False, [],
            id="mp_informada_7_2",
        ),
    ],
)
def test_diagnostico_notas(notas, kwargs, mp, sit, req7, req4, afmin, presumido, avisos):
    r = diagnosticar_notas_ufc(notas, **kwargs)
    assert r.media_parcial_atual == mp
    assert r.situacao_regimental == sit
    assert r.nota_necessaria_por_unidade_para_media_7 == req7
    assert r.nota_necessaria_por_unidade_para_af_4 == req4
    assert r.nota_minima_avaliacao_final == afmin
    assert r.total_unidades_presumido == presumido
    assert r.avisos == avisos


@pytest.mark.parametrize(
    "mp, af, esperado",
    [
        (5.0, 5.0, "APROVADO_APOS_AF"),
        (6.0, 4.0, "APROVADO_APOS_AF"),
        (6.0, 3.9, "REPROVADO_APOS_AF"),
        (4.0, 6.0, "APROVADO_APOS_AF"),
        (4.0, 5.9, "REPROVADO_APOS_AF"),
        (6.9, 4.0, "APROVADO_APOS_AF"),
        (5.0, 4.9, "REPROVADO_APOS_AF"),
    ],
)
def test_resultado_apos_af(mp, af, esperado):
    assert avaliar_resultado_apos_af(mp, af) == esperado


def test_media_exata_nao_arredondada():
    r = diagnosticar_notas_ufc([6.95, 6.95, 6.95], total_unidades_previstas=3)
    assert r.media_parcial_exata == pytest.approx(6.95)
    assert r.media_parcial_atual == 7.0
