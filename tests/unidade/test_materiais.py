"""Testes unitários do serviço de materiais e caminho relativo em `ics` (C4)."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from tests.apoio.sigaa_simulado import TransporteUfcSimulado, gerar_pdf_aula_bytes
from tests.seguranca.test_cofre import KeyringSeguroMemoria
from ufc_mcp.ferramentas import ContextoApp
from ufc_mcp.nucleo.config import Config, Limites
from ufc_mcp.nucleo.credenciais import CofreSistema, Credencial
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.http import ClienteEducado, RespostaBinaria
from ufc_mcp.servicos.materiais import ServicoMateriais, extrair_texto_paginado
from ufc_mcp.servidor import AplicacaoServidorUfcMcp


class _SessaoFalsaMateriais:
    def __init__(self, mapa: dict[str, tuple[bytes, str, str]]) -> None:
        self._mapa = mapa

    async def baixar_material_turma(
        self, id_turma: str, id_material: str
    ) -> tuple[RespostaBinaria, str]:
        conteudo, ct, nome = self._mapa[id_material]
        resp = RespostaBinaria(
            url_final=f"https://si3.ufc.br/sigaa/ava/{id_material}",
            status=200,
            conteudo=conteudo,
            content_type=ct,
        )
        return resp, nome


def test_dois_materiais_mesmo_titulo_nao_se_sobrescrevem() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(
            curso=657468,
            restaurante=1,
            pasta_config=Path(tmp) / "cfg",
            pasta_cache=Path(tmp) / "cache",
            pasta_documentos=Path(tmp) / "docs",
        )
        sessao: Any = _SessaoFalsaMateriais(
            {
                "mat_01": (b"Conteudo exclusivo do primeiro arquivo", "text/plain", "aula.txt"),
                "mat_02": (b"Conteudo exclusivo do segundo arquivo", "text/plain", "aula.txt"),
            }
        )
        serv = ServicoMateriais(sessao, cfg)

        async def rodar() -> None:
            r1 = await serv.baixar_e_ler_material("910001", "mat_01")
            r2 = await serv.baixar_e_ler_material("910001", "mat_02")

            assert r1.arquivo_local != r2.arquivo_local
            assert r1.arquivo_local == "materiais/910001/mat_01_aula.txt"
            assert r2.arquivo_local == "materiais/910001/mat_02_aula.txt"
            assert str(Path.home()) not in r1.arquivo_local
            assert str(Path.home()) not in r2.arquivo_local

            # Reabrir o primeiro devolve o texto dele (não foi sobrescrito pelo segundo)
            r1_reaberto = await serv.baixar_e_ler_material("910001", "mat_01")
            assert r1_reaberto.previa_texto is not None
            assert "primeiro arquivo" in r1_reaberto.previa_texto.texto_externo
            assert "segundo arquivo" not in r1_reaberto.previa_texto.texto_externo

            assert r2.previa_texto is not None
            assert "segundo arquivo" in r2.previa_texto.texto_externo

        asyncio.run(rodar())


def test_pagina_inicial_alem_do_fim_levanta_erro_parametro_invalido() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        arq = Path(tmp) / "curto.txt"
        arq.write_text("Linha 1\nLinha 2\n", encoding="utf-8")

        with pytest.raises(ErroUfc) as exc:
            extrair_texto_paginado(arq, pagina_inicial=2, pagina_final=3)
        assert exc.value.codigo == CodigoErro.PARAMETRO_INVALIDO
        assert "1" in str(exc.value)


def test_metadados_paginas_sem_texto_e_texto_cortado() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        # Página 1 com texto longo (> max_chars), página 2 só linhas vazias
        linhas = ["A" * 40 for _ in range(50)] + ["" for _ in range(10)]
        arq = Path(tmp) / "multi.txt"
        arq.write_text("\n".join(linhas), encoding="utf-8")

        previa, total, lidas, sem_texto = extrair_texto_paginado(
            arq, pagina_inicial=1, pagina_final=2, max_chars=200
        )
        assert total == 2
        assert lidas == [1, 2]
        assert sem_texto == [2]
        assert previa is not None
        assert previa.cortado is True


def test_ics_devolve_caminho_relativo_sem_home() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(
            curso=657468,
            restaurante=1,
            pasta_config=Path(tmp) / "cfg",
            pasta_cache=Path(tmp) / "cache",
            pasta_documentos=Path(tmp) / "docs",
            limites=Limites(pausa_minima_s=0.5),
        )
        kr = KeyringSeguroMemoria()
        cofre = CofreSistema(backend_keyring=kr)
        cofre.salvar_credencial(Credencial(usuario="aluno", senha="senha_correta_123"))
        http = ClienteEducado(
            cfg.limites,
            relogio=lambda: 10.0,
            dormir=lambda _s: asyncio.sleep(0),
            transporte=TransporteUfcSimulado(),
        )
        app = AplicacaoServidorUfcMcp(ContextoApp(config=cfg, http=http, cofre=cofre))

        resp = asyncio.run(app.chamar_ferramenta("ics", {}))
        dados = json.loads(resp)["dados"]
        arq_ics = dados["arquivo_ics"]
        assert str(Path.home()) not in arq_ics
        assert not Path(arq_ics).is_absolute()
        assert (cfg.pasta_documentos / arq_ics).exists()


def test_pdf_simulado_extrai_texto_por_pagina() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        arq = Path(tmp) / "aula.pdf"
        arq.write_bytes(gerar_pdf_aula_bytes())

        p1, total1, lidas1, vazias1 = extrair_texto_paginado(arq, pagina_inicial=1, pagina_final=1)
        assert total1 == 3
        assert lidas1 == [1]
        assert vazias1 == []
        assert p1 is not None
        assert "Balanco de massa" in p1.texto_externo
        assert "Exemplo:" not in p1.texto_externo

        p2, total2, lidas2, vazias2 = extrair_texto_paginado(arq, pagina_inicial=2, pagina_final=2)
        assert total2 == 3
        assert lidas2 == [2]
        assert vazias2 == []
        assert p2 is not None
        assert "5%" in p2.texto_externo
        assert "Exercicio" not in p2.texto_externo

        p3, total3, lidas3, vazias3 = extrair_texto_paginado(arq, pagina_inicial=3, pagina_final=3)
        assert total3 == 3
        assert lidas3 == [3]
        assert vazias3 == []
        assert p3 is not None
        assert "Exercicio:" in p3.texto_externo
        assert "60 kg/h" in p3.texto_externo

        with pytest.raises(ErroUfc) as exc:
            extrair_texto_paginado(arq, pagina_inicial=4, pagina_final=4)
        assert exc.value.codigo == CodigoErro.PARAMETRO_INVALIDO
        assert "3" in str(exc.value)
