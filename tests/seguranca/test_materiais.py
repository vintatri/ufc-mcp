"""Testes de segurança da sandbox de materiais: Path Traversal, extensões, paginação e TextoExterno (T16)."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from tests.apoio.sigaa_simulado import TransporteUfcSimulado
from tests.seguranca.test_cofre import KeyringSeguroMemoria
from ufc_mcp.nucleo.config import Config, Limites
from ufc_mcp.nucleo.credenciais import CofreSistema, Credencial
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.http import ClienteEducado
from ufc_mcp.nucleo.sessao_sigaa import SessaoSigaa
from ufc_mcp.servicos.materiais import ServicoMateriais, sanitizar_nome_arquivo


class TestSegurancaMateriais(unittest.TestCase):
    def test_bloqueio_path_traversal_e_executaveis(self) -> None:
        nome_limpo = sanitizar_nome_arquivo("../../etc/passwd.pdf")
        self.assertEqual(nome_limpo, "passwd.pdf")

        for malicioso in ("malware.exe", "script.sh", "payload.bat", "trojan.js", "lib.so"):
            with self.assertRaises(ErroUfc) as ctx:
                sanitizar_nome_arquivo(malicioso)
            self.assertEqual(ctx.exception.codigo, CodigoErro.ACAO_BLOQUEADA)

    def test_download_paginado_e_reuso_local(self) -> None:
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

            transporte = TransporteUfcSimulado()
            http = ClienteEducado(
                cfg.limites,
                relogio=lambda: 10.0,
                dormir=lambda _s: asyncio.sleep(0),
                transporte=transporte,
            )
            sessao = SessaoSigaa(http, cofre, cfg.pasta_config)
            serv = ServicoMateriais(sessao, cfg)

            async def rodar() -> None:
                res1 = await serv.baixar_e_ler_material(
                    "910001", "mat_01", extrair_texto=True, pagina_inicial=1, pagina_final=2
                )
                self.assertEqual(res1.paginas_lidas, [1, 2])
                self.assertEqual(res1.total_paginas_pdf, 3)
                self.assertIsNotNone(res1.previa_texto)
                reqs_apos_1 = http.total_requisicoes

                # Segunda leitura de outra página do mesmo arquivo deve reutilizar o PDF local sem fazer rede!
                res2 = await serv.baixar_e_ler_material(
                    "910001", "mat_01", extrair_texto=True, pagina_inicial=3, pagina_final=3
                )
                self.assertEqual(res2.paginas_lidas, [3])
                self.assertEqual(http.total_requisicoes, reqs_apos_1)

            asyncio.run(rodar())
