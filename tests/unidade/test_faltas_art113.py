import pytest

from ufc_mcp.servicos.faltas import calcular_faltas_disciplina


@pytest.mark.parametrize(
    "ch, faltas, limite, restantes, enc2h, presenca, uso, sev, sit",
    [
        pytest.param(64, 0, 16, 16, 8, 100.0, 0.0, "OK", "REGULAR", id="ch64_faltas0"),
        pytest.param(64, 8, 16, 8, 4, 87.5, 50.0, "ATENCAO", "ALERTA_LIMITE", id="ch64_faltas8"),
        pytest.param(64, 9, 16, 7, 3, 85.94, 56.25, "ATENCAO", "ALERTA_LIMITE", id="ch64_faltas9"),
        pytest.param(64, 12, 16, 4, 2, 81.25, 75.0, "CRITICO", "ALERTA_LIMITE", id="ch64_faltas12"),
        pytest.param(64, 16, 16, 0, 0, 75.0, 100.0, "CRITICO", "ALERTA_LIMITE", id="ch64_faltas16"),
        pytest.param(64, 17, 16, -1, -1, 73.44, 106.25, "CRITICO", "REPROVADO_POR_FALTA", id="ch64_faltas17"),
        pytest.param(32, 4, 8, 4, 2, 87.5, 50.0, "CRITICO", "ALERTA_LIMITE", id="ch32_faltas4"),
        pytest.param(32, 8, 8, 0, 0, 75.0, 100.0, "CRITICO", "ALERTA_LIMITE", id="ch32_faltas8"),
        pytest.param(32, 9, 8, -1, -1, 71.88, 112.5, "CRITICO", "REPROVADO_POR_FALTA", id="ch32_faltas9"),
        pytest.param(96, 24, 24, 0, 0, 75.0, 100.0, "CRITICO", "ALERTA_LIMITE", id="ch96_faltas24"),
        pytest.param(96, 25, 24, -1, -1, 73.96, 104.17, "CRITICO", "REPROVADO_POR_FALTA", id="ch96_faltas25"),
        pytest.param(60, 15, 15, 0, 0, 75.0, 100.0, "CRITICO", "ALERTA_LIMITE", id="ch60_faltas15"),
        pytest.param(64, None, 16, None, None, None, None, "INDISPONIVEL", "DADOS_INDISPONIVEIS", id="ch64_faltasNone"),
        pytest.param(0, 5, None, None, None, None, None, "INDISPONIVEL", "SEM_CARGA_HORARIA", id="ch0_faltas5"),
        pytest.param(None, 5, None, None, None, None, None, "INDISPONIVEL", "SEM_CARGA_HORARIA", id="chNone_faltas5"),
    ],
)
def test_faltas_art113(ch, faltas, limite, restantes, enc2h, presenca, uso, sev, sit):
    r = calcular_faltas_disciplina(
        id_turma="1", codigo="X", nome="N", carga_horaria_h=ch, faltas_registradas_h=faltas
    )
    assert r.limite_faltas_h == limite
    assert r.restantes_h == restantes
    assert r.encontros_2h_restantes == enc2h
    assert r.percentual_presenca_atual == presenca
    assert r.percentual_limite_usado == uso
    assert r.severidade == sev
    assert r.situacao == sit


def test_faltas_negativas_viram_zero():
    r = calcular_faltas_disciplina(
        id_turma="1", codigo="X", nome="N", carga_horaria_h=64, faltas_registradas_h=-3
    )
    assert r.faltas_registradas_h == 0
    assert r.situacao == "REGULAR"
