"""
Testes de Contrato (T10 a T16 + Experimento E1):
Valida todos os parsers contra 100% dos arquivos em `tests/paginas/dev/`
e contra o conjunto hold-out independente `tests/paginas/validacao/` (incluindo os 3 cursos da UFC).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ufc_mcp.fontes.calendario.parser import parse_calendario_ufc
from ufc_mcp.fontes.noticias.parser import parse_rss_noticias
from ufc_mcp.fontes.ru.parser import parse_cardapio_ru
from ufc_mcp.fontes.sigaa.parsers.agenda import parse_agenda_turmas
from ufc_mcp.fontes.sigaa.parsers.ira import parse_historico_ira
from ufc_mcp.fontes.sigaa.parsers.listagem import (
    MAPA_ACAO_MENU_LISTAGEM,
    parse_listagem_generica,
)
from ufc_mcp.fontes.sigaa.parsers.ofertas import parse_ofertas_turmas
from ufc_mcp.fontes.sigaa.parsers.pendencias import parse_pendencias_ou_biblioteca
from ufc_mcp.fontes.sigaa.parsers.portal import parse_portal_discente
from ufc_mcp.fontes.sigaa.parsers.progresso import parse_progresso_curso
from ufc_mcp.fontes.sigaa.parsers.turma_virtual import (
    parse_turma_avaliacoes,
    parse_turma_frequencia,
    parse_turma_notas,
    parse_turma_noticias,
    parse_turma_plano_curso,
    parse_turma_tarefas,
    parse_turma_visao_geral,
)
from ufc_mcp.fontes.sigaa_publico.parser import (
    parse_calendario_curso_publico,
    parse_curriculo_publico,
)

RAIZ_TESTS = Path(__file__).resolve().parents[1]


class TestContratosDevEHoldout(unittest.TestCase):
    def _verificar_conjunto(self, conjunto: str) -> None:
        p_pag = RAIZ_TESTS / "paginas" / conjunto
        p_gab = RAIZ_TESTS / "gabaritos" / conjunto

        # 1. RU
        for arq in sorted((p_pag / "ru").glob("*.html")):
            partes = arq.stem.split("_")
            rest_id = int(partes[1])
            dt_iso = partes[2]
            obtido = parse_cardapio_ru(
                arq.read_text(encoding="utf-8"), data=dt_iso, restaurante=rest_id
            ).model_dump()
            esperado = json.loads((p_gab / "ru" / f"{arq.stem}.json").read_text(encoding="utf-8"))
            self.assertEqual(obtido, esperado)

        # 2. Calendário
        h_cal = (p_pag / "calendario" / "calendario_2026.html").read_text(encoding="utf-8")
        self.assertEqual(
            parse_calendario_ufc(h_cal, ano_padrao=2026).model_dump(),
            json.loads((p_gab / "calendario" / "calendario_2026.json").read_text(encoding="utf-8")),
        )

        # 3. RSS
        for f_rss in ("ufc", "prograd", "prae"):
            x_rss = (p_pag / "noticias" / f"feed_{f_rss}.xml").read_text(encoding="utf-8")
            obt_rss = [i.model_dump() for i in parse_rss_noticias(x_rss, fonte=f_rss)]
            esp_rss = json.loads((p_gab / "noticias" / f"feed_{f_rss}.json").read_text(encoding="utf-8"))
            self.assertEqual(obt_rss, esp_rss)

        # 4. SIGAA Público (3 cursos)
        for arq_of in sorted((p_pag / "sigaa_publico").glob("ofertas_*.html")):
            obt_of = [o.model_dump() for o in parse_ofertas_turmas(arq_of.read_text(encoding="utf-8"))]
            esp_of = json.loads((p_gab / "sigaa_publico" / f"{arq_of.stem}.json").read_text(encoding="utf-8"))
            self.assertEqual(obt_of, esp_of)

        for arq_cu in sorted((p_pag / "sigaa_publico").glob("curriculo_*.html")):
            obt_cu = [c.model_dump() for c in parse_curriculo_publico(arq_cu.read_text(encoding="utf-8"))]
            esp_cu = json.loads((p_gab / "sigaa_publico" / f"{arq_cu.stem}.json").read_text(encoding="utf-8"))
            self.assertEqual(obt_cu, esp_cu)

        for arq_cc in sorted((p_pag / "sigaa_publico").glob("calendario_curso_*.html")):
            cid = int(arq_cc.stem.split("_")[-1])
            obt_cc = parse_calendario_curso_publico(
                arq_cc.read_text(encoding="utf-8"), id_curso=cid
            ).model_dump()
            esp_cc = json.loads((p_gab / "sigaa_publico" / f"{arq_cc.stem}.json").read_text(encoding="utf-8"))
            self.assertEqual(obt_cc, esp_cc)

        # 5. SIGAA Autenticado
        h_port = (p_pag / "sigaa" / "portal_discente.html").read_text(encoding="utf-8")
        self.assertEqual(
            parse_portal_discente(h_port, identificadores=False).model_dump(),
            json.loads((p_gab / "sigaa" / "portal_discente.json").read_text(encoding="utf-8")),
        )

        for arq_pr in sorted((p_pag / "sigaa").glob("progresso_*.html")):
            self.assertEqual(
                parse_progresso_curso(arq_pr.read_text(encoding="utf-8")).model_dump(),
                json.loads((p_gab / "sigaa" / f"{arq_pr.stem}.json").read_text(encoding="utf-8")),
            )

        self.assertEqual(
            parse_historico_ira((p_pag / "sigaa" / "historico_ira.html").read_text(encoding="utf-8")).model_dump(),
            json.loads((p_gab / "sigaa" / "historico_ira.json").read_text(encoding="utf-8")),
        )
        self.assertEqual(
            parse_pendencias_ou_biblioteca(
                (p_pag / "sigaa" / "pendencias.html").read_text(encoding="utf-8"),
                assinatura_esperada="Pendências",
            ).model_dump(),
            json.loads((p_gab / "sigaa" / "pendencias.json").read_text(encoding="utf-8")),
        )
        self.assertEqual(
            parse_pendencias_ou_biblioteca(
                (p_pag / "sigaa" / "biblioteca.html").read_text(encoding="utf-8"),
                assinatura_esperada="Biblioteca",
            ).model_dump(),
            json.loads((p_gab / "sigaa" / "biblioteca.json").read_text(encoding="utf-8")),
        )
        self.assertEqual(
            parse_agenda_turmas((p_pag / "sigaa" / "agenda_turmas.html").read_text(encoding="utf-8")),
            json.loads((p_gab / "sigaa" / "agenda_turmas.json").read_text(encoding="utf-8")),
        )

        for t_list in MAPA_ACAO_MENU_LISTAGEM:
            h_l = (p_pag / "sigaa" / f"listagem_{t_list}.html").read_text(encoding="utf-8")
            obt_l = parse_listagem_generica(h_l, tipo=t_list).model_dump()
            esp_l = json.loads((p_gab / "sigaa" / f"listagem_{t_list}.json").read_text(encoding="utf-8"))
            # Garantir que botões de ação JSF (como "Dar Aceite na Indicação") jamais aparecem nos dados
            self.assertNotIn("Dar Aceite na Indicação", json.dumps(obt_l, ensure_ascii=False))
            self.assertEqual(obt_l, esp_l)

        mapa_ava = {
            "principal": lambda h: parse_turma_visao_geral(h, id_turma="910001").model_dump(),
            "notas": lambda h: parse_turma_notas(h, id_turma="910001").model_dump(),
            "frequencia": lambda h: parse_turma_frequencia(h, id_turma="910001").model_dump(),
            "avaliacoes": lambda h: parse_turma_avaliacoes(h, id_turma="910001").model_dump(),
            "tarefas": lambda h: parse_turma_tarefas(h, id_turma="910001").model_dump(),
            "noticias": lambda h: parse_turma_noticias(h, id_turma="910001").model_dump(),
            "plano_curso": lambda h: parse_turma_plano_curso(h, id_turma="910001").model_dump(),
        }
        for sec, fn in mapa_ava.items():
            h_s = (p_pag / "sigaa" / f"ava_{sec}.html").read_text(encoding="utf-8")
            self.assertEqual(
                fn(h_s),
                json.loads((p_gab / "sigaa" / f"ava_{sec}.json").read_text(encoding="utf-8")),
            )

    def test_conjunto_desenvolvimento(self) -> None:
        self._verificar_conjunto("dev")

    def test_conjunto_holdout_validacao(self) -> None:
        self._verificar_conjunto("validacao")
