"""Chama cada ferramenta pelo servidor com o transporte simulado (mesmas chamadas do experimento E2).

Exercita as camadas de ferramentas, serviços e extratores de ponta a ponta, sem rede. Cada chamada tem
de devolver um envelope JSON com `ok` verdadeiro; o limitador de taxa usa o relógio simulado.
"""

import json
from pathlib import Path

import pytest

from tests.apoio.sigaa_simulado import TransporteUfcSimulado
from tests.seguranca.test_cofre import KeyringSeguroMemoria
from ufc_mcp.ferramentas import ContextoApp
from ufc_mcp.nucleo.config import Config
from ufc_mcp.nucleo.credenciais import CofreSistema, Credencial
from ufc_mcp.nucleo.http import ClienteEducado
from ufc_mcp.servidor import AplicacaoServidorUfcMcp

CHAMADAS = [
    pytest.param("cardapio", {"data": "2026-11-13", "refeicao": "almoco", "restaurante": "Pici"}, id="C1_01_cardapio"),
    pytest.param("cardapio", {"data": "2026-11-13", "refeicao": "almoco", "restaurante": "Fortaleza"}, id="C1_02_cardapio"),
    pytest.param("cardapio", {"data": "2026-11-13", "refeicao": "jantar", "restaurante": "Fortaleza"}, id="C1_03_cardapio"),
    pytest.param("cardapio", {"data": "2026-11-16", "refeicao": "desjejum", "restaurante": "Pici"}, id="C1_04_cardapio"),
    pytest.param("cardapio", {"data": "2026-11-13", "refeicao": "desjejum", "restaurante": "Fortaleza"}, id="C1_05_cardapio"),
    pytest.param("dia", {"data": "2026-11-13", "restaurante": "Fortaleza"}, id="C1_07_dia"),
    pytest.param("cardapio_semana", {"inicio": "2026-11-16", "restaurante": "Fortaleza"}, id="C1_08_cardapio_semana"),
    pytest.param("restaurantes", {}, id="C1_09_restaurantes"),
    pytest.param("calendario", {"fim": "2026-12-13", "inicio": "2026-11-13"}, id="C1_10_calendario"),
    pytest.param("aula", {"data": "2026-11-13"}, id="C2_01_aula"),
    pytest.param("aula", {"data": "2026-11-16"}, id="C2_03_aula"),
    pytest.param("aula", {"data": "2026-11-19"}, id="C2_04_aula"),
    pytest.param("horario", {}, id="C2_05_horario"),
    pytest.param("turmas", {}, id="C2_06_turmas"),
    pytest.param("aula", {"data": "2026-11-17"}, id="C2_10_aula"),
    pytest.param("faltas", {"id_turma": "910001"}, id="C3_01_faltas"),
    pytest.param("alertas", {}, id="C3_02_alertas"),
    pytest.param("notas", {"id_turma": "910001"}, id="C3_03_notas"),
    pytest.param("faltas", {"id_turma": "910003"}, id="C3_06_faltas"),
    pytest.param("avaliacoes", {"id_turma": "910001"}, id="C3_08_avaliacoes"),
    pytest.param("frequencia", {"id_turma": "910001"}, id="C3_10_frequencia"),
    pytest.param("matricula", {}, id="C4_01_matricula"),
    pytest.param("grade", {}, id="C4_03_grade"),
    pytest.param("ofertas", {"ano": 2026, "codigo_componente": "EQ0085", "id_curso": 657468, "periodo": 2}, id="C4_04_ofertas"),
    pytest.param("ofertas", {"ano": 2026, "codigo_componente": "EQ0072", "id_curso": 657468, "periodo": 2}, id="C4_05_ofertas"),
    pytest.param("pendencias", {}, id="C4_06_pendencias"),
    pytest.param("ira", {}, id="C4_07_ira"),
    pytest.param("portal", {}, id="C4_08_portal"),
    pytest.param("calendario_curso", {"id_curso": 657468}, id="C4_09_calendario_curso"),
    pytest.param("estudo", {"id_turma": "910001"}, id="C5_01_estudo"),
    pytest.param("turma", {"id_turma": "910001"}, id="C5_02_turma"),
    pytest.param("plano", {"id_turma": "910001"}, id="C5_04_plano"),
    pytest.param("tarefas", {"id_turma": "910001"}, id="C5_08_tarefas"),
    pytest.param("baixar", {"id_material": "mat_01", "id_turma": "910001"}, id="C5_09_baixar"),
]


@pytest.mark.parametrize(("ferramenta", "argumentos"), CHAMADAS)
async def test_ferramenta_responde_ok_no_simulador(tmp_path: Path, ferramenta: str, argumentos: dict) -> None:
    tempo = [1000.0]

    async def dormir(seg: float) -> None:
        tempo[0] += seg

    cfg = Config(
        perfil="completo",
        curso=657468,
        restaurante="Fortaleza",
        pasta_config=tmp_path / "cfg",
        pasta_cache=tmp_path / "cache",
        pasta_documentos=tmp_path / "docs",
    )
    cofre = CofreSistema(backend_keyring=KeyringSeguroMemoria())
    cofre.salvar_credencial(Credencial(usuario="aluno", senha="senha_correta_123"))
    http = ClienteEducado(
        cfg.limites, relogio=lambda: tempo[0], dormir=dormir, transporte=TransporteUfcSimulado()
    )
    app = AplicacaoServidorUfcMcp(ContextoApp(config=cfg, http=http, cofre=cofre))
    resposta = await app.chamar_ferramenta(ferramenta, dict(argumentos))
    assert '"ok":true' in resposta.replace(" ", "") or json.loads(resposta).get("ok") is True, resposta[:300]


async def test_alertas_termina_completo_mesmo_com_30_requisicoes(tmp_path: Path) -> None:
    """`alertas` lê várias telas por turma; o limitador espera a janela do minuto em vez de falhar."""
    tempo = [1000.0]

    async def dormir(seg: float) -> None:
        tempo[0] += seg

    cfg = Config(
        perfil="completo",
        curso=657468,
        restaurante="Fortaleza",
        pasta_config=tmp_path / "cfg",
        pasta_cache=tmp_path / "cache",
        pasta_documentos=tmp_path / "docs",
    )
    cofre = CofreSistema(backend_keyring=KeyringSeguroMemoria())
    cofre.salvar_credencial(Credencial(usuario="aluno", senha="senha_correta_123"))
    http = ClienteEducado(
        cfg.limites, relogio=lambda: tempo[0], dormir=dormir, transporte=TransporteUfcSimulado()
    )
    app = AplicacaoServidorUfcMcp(ContextoApp(config=cfg, http=http, cofre=cofre))
    texto = await app.chamar_ferramenta("alertas", {})
    assert "LIMITE_DE_REQUISICOES" not in texto
    # a primeira linha é o aviso de texto de terceiros; o envelope JSON vem em seguida
    envelope = json.loads(texto.split("\n", 1)[1])
    dados = envelope.get("dados", envelope)
    assert dados["resultado_completo"] is True
    assert dados["leituras_indisponiveis"] == []
    assert http.total_requisicoes >= 30  # a chamada passa do teto de um minuto, e mesmo assim termina
    assert http.contadores_atuais()["usadas_no_minuto"] <= cfg.limites.max_por_minuto
