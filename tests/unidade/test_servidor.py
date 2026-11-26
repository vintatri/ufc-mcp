"""Testes unitários do Servidor MCP: todas as ferramentas no perfil completo, o subconjunto no essencial e JSON-RPC (T17)."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Literal

from tests.apoio.sigaa_simulado import TransporteUfcSimulado
from tests.seguranca.test_cofre import KeyringSeguroMemoria
from ufc_mcp.ferramentas import ContextoApp
from ufc_mcp.nucleo.config import Config, Limites
from ufc_mcp.nucleo.credenciais import CofreSistema, Credencial
from ufc_mcp.nucleo.http import ClienteEducado
from ufc_mcp.servidor import AplicacaoServidorUfcMcp


class TestServidorMcp(unittest.TestCase):
    def test_catalogo_36_completo_e_16_essencial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_comp = Config(
                curso=657468,
                restaurante=1,
                perfil="completo",
                pasta_config=Path(tmp) / "cfg",
                pasta_cache=Path(tmp) / "cache",
                pasta_documentos=Path(tmp) / "docs",
            )
            app_comp = AplicacaoServidorUfcMcp(ContextoApp(config=cfg_comp))
            self.assertEqual(len(app_comp.listar_ferramentas_esquema()), 36)

            cfg_ess = Config(
                curso=657468,
                restaurante=1,
                perfil="essencial",
                pasta_config=Path(tmp) / "cfg2",
                pasta_cache=Path(tmp) / "cache2",
                pasta_documentos=Path(tmp) / "docs2",
            )
            app_ess = AplicacaoServidorUfcMcp(ContextoApp(config=cfg_ess))
            self.assertEqual(len(app_ess.listar_ferramentas_esquema()), 16)

    def test_execucao_fim_a_fim_copiloto_e_tutoria(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(
                curso=657468,
                restaurante=1,
                perfil="completo",
                pasta_config=Path(tmp) / "cfg",
                pasta_cache=Path(tmp) / "cache",
                pasta_documentos=Path(tmp) / "docs",
                limites=Limites(pausa_minima_s=0.5),
            )
            kr = KeyringSeguroMemoria()
            cofre = CofreSistema(backend_keyring=kr)
            cofre.salvar_credencial(Credencial(usuario="aluno", senha="senha_correta_123"))

            tempo_sim = [100.0]
            def relogio_sim() -> float:
                return tempo_sim[0]
            async def dormir_sim(s: float) -> None:
                tempo_sim[0] += max(s, 3.0)
            http = ClienteEducado(
                cfg.limites,
                relogio=relogio_sim,
                dormir=dormir_sim,
                transporte=TransporteUfcSimulado(),
            )
            ctx = ContextoApp(config=cfg, http=http, cofre=cofre)
            app = AplicacaoServidorUfcMcp(ctx)

            async def rodar() -> None:
                # 1. initialize JSON-RPC
                r_init = await app.processar_mensagem_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
                assert r_init is not None
                self.assertEqual(r_init["result"]["protocolVersion"], "2025-11-25")

                # 2. aula (em 2026-11-13 -> detecta mudança de sala para Bloco 709!)
                resp_onde = await app.chamar_ferramenta("aula", {"data": "2026-11-13"})
                linhas = resp_onde.split("\n", 1)
                dados_onde = json.loads(linhas[1])["dados"]
                self.assertEqual(dados_onde["aulas"][0]["status_inferido"], "POSSIVEL_MUDANCA_SALA")

                # 3. alertas
                resp_radar = await app.chamar_ferramenta("alertas", {"dias_antecedencia": 7})
                dados_radar = json.loads(resp_radar.split("\n", 1)[1])["dados"]
                self.assertTrue(dados_radar["total_alertas_criticos"] >= 1)

                # 4. grade
                resp_sim = await app.chamar_ferramenta("grade", {"estrategia": "diversificada"})
                dados_sim = json.loads(resp_sim)["dados"]
                self.assertTrue(dados_sim["validacao_grafo"]["eh_dag"])
                self.assertTrue(len(dados_sim["grades_sugeridas"]) >= 2)

                # 5. estudo + baixar
                resp_tut = await app.chamar_ferramenta("estudo", {"id_turma": "910001"})
                dados_tut = json.loads(resp_tut.split("\n", 1)[1])["dados"]
                self.assertEqual(
                    dados_tut["diagnostico_notas_ufc"]["nota_necessaria_por_unidade_para_media_7"],
                    9.0,
                )
                resp_mat = await app.chamar_ferramenta(
                    "baixar",
                    {"id_turma": "910001", "id_material": "mat_01", "pagina_inicial": 1, "pagina_final": 2},
                )
                dados_mat = json.loads(resp_mat.split("\n", 1)[1])["dados"]
                self.assertEqual(dados_mat["paginas_lidas"], [1, 2])

            asyncio.run(rodar())


class TestServidorSchemaEPrompts(unittest.TestCase):
    def _app(self, tmp: str) -> AplicacaoServidorUfcMcp:
        cfg = Config(
            curso=657468,
            restaurante=1,
            pasta_config=Path(tmp) / "cfg",
            pasta_cache=Path(tmp) / "cache",
            pasta_documentos=Path(tmp) / "docs",
        )
        return AplicacaoServidorUfcMcp(ContextoApp(config=cfg))

    def test_schema_literal_gera_enum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lista = self._app(tmp).listar_ferramentas_esquema()
            esquemas = {t["name"]: t["inputSchema"] for t in lista}
        props = esquemas["grade"]["properties"]
        self.assertEqual(
            props["estrategia"]["enum"], ["diversificada", "desbloqueio", "compacta", "equilibrada"]
        )
        self.assertEqual(props["turno_preferido"]["enum"], ["manha", "tarde", "noite", "qualquer"])
        self.assertEqual(props["max_disciplinas"]["type"], "integer")

    def test_schema_literal_ou_none(self) -> None:
        from ufc_mcp.servidor import _gerar_json_schema_funcao

        def fn(modo: Literal["a", "b"] | None = None) -> str:
            return ""

        self.assertEqual(
            _gerar_json_schema_funcao(fn)["properties"]["modo"],
            {"type": "string", "enum": ["a", "b"]},
        )

    def test_prompts_especificos_e_citacao(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)

            def txt(nome: str, args: dict[str, str] | None = None) -> str:
                return str(app.obter_prompt(nome, args)["messages"][0]["content"]["text"])

            self.assertIn("dia", txt("meu-dia"))
            sem = txt("planejar-semana")
            self.assertIn("semana", sem)
            self.assertIn("alertas", sem)
            pend = txt("conferir-pendencias")
            self.assertIn("pendencias", pend)
            self.assertIn("alertas", pend)
            sem_turma = txt("estudar-disciplina")
            self.assertNotIn("910001", sem_turma)
            self.assertIn("turmas", sem_turma)
            com = txt("estudar-disciplina", {"id_turma": "42", "topico": "limites"})
            self.assertIn("42", com)
            self.assertIn("limites", com)
            self.assertIn("[Material:", com)
            self.assertNotIn("[Fonte:", com)

    def test_prompt_simulado_nao_revela_resposta_e_cita_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)

            def txt(args: dict[str, str] | None = None) -> str:
                return str(app.obter_prompt("simulado", args)["messages"][0]["content"]["text"])

            sem_turma = txt()
            self.assertIn("turmas", sem_turma)
            self.assertIn("5 questões", sem_turma)
            com = txt({"id_turma": "42", "topico": "limites", "n_questoes": "3"})
            self.assertIn("estudo(id_turma='42', foco='topico_especifico', termo_topico='limites')", com)
            self.assertIn("3 questões", com)
            self.assertIn("SEM resposta", com)
            self.assertIn("PARE", com)
            self.assertIn("[Material:", com)
            self.assertIn("texto_externo", com)
            # n_questoes fora de 1..10 ou não numérico volta ao padrão de 5
            self.assertIn("5 questões", txt({"n_questoes": "99"}))
            self.assertIn("5 questões", txt({"n_questoes": "abc"}))

    def test_prompts_estudar_e_simulado_foco_topico_especifico(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)

            def txt(nome: str, args: dict[str, str] | None = None) -> str:
                return str(app.obter_prompt(nome, args)["messages"][0]["content"]["text"])

            # Com tópico: inclui foco='topico_especifico' e termo_topico
            est_com = txt("estudar-disciplina", {"id_turma": "42", "topico": "destilacao"})
            self.assertIn("estudo(id_turma='42', foco='topico_especifico', termo_topico='destilacao')", est_com)
            est_sem_id = txt("estudar-disciplina", {"topico": "destilacao"})
            self.assertIn("estudo(id_turma=<id_turma>, foco='topico_especifico', termo_topico='destilacao')", est_sem_id)

            sim_com = txt("simulado", {"id_turma": "42", "topico": "destilacao"})
            self.assertIn("estudo(id_turma='42', foco='topico_especifico', termo_topico='destilacao')", sim_com)
            sim_sem_id = txt("simulado", {"topico": "destilacao"})
            self.assertIn("estudo(id_turma=<id_turma>, foco='topico_especifico', termo_topico='destilacao')", sim_sem_id)

            # Sem tópico: não inclui foco nem termo_topico
            est_sem = txt("estudar-disciplina", {"id_turma": "42"})
            self.assertIn("estudo(id_turma='42')", est_sem)
            self.assertNotIn("topico_especifico", est_sem)
            sim_sem = txt("simulado", {"id_turma": "42"})
            self.assertIn("estudo(id_turma='42')", sim_sem)
            self.assertNotIn("topico_especifico", sim_sem)

    def test_fallback_embutido_initialize_e_notificacoes(self) -> None:
        from ufc_mcp.servidor import ServidorMcpEmbutido

        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            app.mcp = ServidorMcpEmbutido("x")

            async def rodar() -> tuple[object, object, object, object]:
                a = await app.processar_mensagem_jsonrpc(
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2025-06-18"}}
                )
                b = await app.processar_mensagem_jsonrpc(
                    {"jsonrpc": "2.0", "id": 2, "method": "initialize",
                     "params": {"protocolVersion": "1999-01-01"}}
                )
                c = await app.processar_mensagem_jsonrpc(
                    {"jsonrpc": "2.0", "id": 3, "method": "ping"}
                )
                d = await app.processar_mensagem_jsonrpc(
                    {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {}}
                )
                return a, b, c, d

            a, b, c, d = asyncio.run(rodar())
        self.assertEqual(a["result"]["protocolVersion"], "2025-06-18")  # type: ignore[index]
        self.assertEqual(b["result"]["protocolVersion"], "2025-11-25")  # type: ignore[index]
        self.assertEqual(c["result"], {})  # type: ignore[index]
        self.assertIsNone(d)
