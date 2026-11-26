"""Testes unitários de SessaoSigaa e renovação automática de ViewState no download binário (T07)."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from tests.apoio.sigaa_simulado import TransporteUfcSimulado
from tests.seguranca.test_cofre import KeyringSeguroMemoria
from ufc_mcp.nucleo.config import Limites
from ufc_mcp.nucleo.credenciais import CofreSistema, Credencial
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.http import ClienteEducado
from ufc_mcp.nucleo.sessao_sigaa import SessaoSigaa


class TestSessaoSigaa(unittest.TestCase):
    def test_navegacao_e_renovacao_viewstate_no_download(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kr = KeyringSeguroMemoria()
            cofre = CofreSistema(backend_keyring=kr)
            cofre.salvar_credencial(Credencial(usuario="aluno", senha="senha_correta_123"))

            transporte = TransporteUfcSimulado()
            http = ClienteEducado(
                Limites(pausa_minima_s=0.5),
                relogio=lambda: 10.0,
                dormir=lambda _s: asyncio.sleep(0),
                transporte=transporte,
            )
            sessao = SessaoSigaa(http, cofre, Path(tmp))

            async def rodar() -> None:
                # 1. Abre a turma 910001 (view Principal)
                await sessao.abrir_turma("910001")
                self.assertEqual(
                    sessao.ultima_view_ativa, ("/sigaa/ava/index.jsf:Principal", "910001")
                )

                # 2. Muda de tela (consulta Ver Notas -> corromperia o ViewState da página Principal!)
                await sessao.navegar_menu_turma("910001", "Ver Notas")
                self.assertEqual(
                    sessao.ultima_view_ativa, ("/sigaa/ava/index.jsf:Ver Notas", "910001")
                )

                # 3. Chama baixar_material_turma: deve detectar que a view ativa mudou,
                # reabrir Principal automaticamente e baixar o PDF com sucesso!
                resp_bin, nome = await sessao.baixar_material_turma("910001", "mat_01")
                self.assertEqual(resp_bin.content_type, "application/pdf")
                self.assertEqual(nome, "Slides_Navier_Stokes.pdf")
                self.assertTrue(len(resp_bin.conteudo) > 100)

            asyncio.run(rodar())


HTML_LINKS_PERIGOSOS = (
    "<html><body><div id='conteudo'><form name='formEnq' action='/sigaa/ava/index.jsf'>"
    "<a href='#' onclick=\"jsfcljs(document.forms['formEnq'],'formEnq:votar,formEnq:votar,opcao,1','');return false;\">Votar</a>"
    "<a href='#' onclick=\"jsfcljs(document.forms['formEnq'],'formEnq:env,formEnq:env,x,1','');return false;\">Enviar</a>"
    "<a href='#' onclick=\"jsfcljs(document.forms['formEnq'],'formEnq:rm,formEnq:rm,x,1','');return false;\">Remover</a>"
    "<a href='#' onclick=\"jsfcljs(document.forms['formEnq'],'formEnq:ver,formEnq:ver,x,1','');return false;\">Ver detalhes</a>"
    "<a href='#' onclick=\"jsfcljs(document.forms['formAvaMat'],'formAvaMat:download,formAvaMat:download,idMat,1','');return false;\">Remover_Aula.pdf</a>"
    "</form></div></body></html>"
)


class TestBaixarMaterialSomenteArquivos(unittest.TestCase):
    def test_links_de_escrita_ou_sem_padrao_de_download_sao_recusados(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            transporte = TransporteUfcSimulado()
            http = ClienteEducado(
                Limites(pausa_minima_s=0.5),
                relogio=lambda: 10.0,
                dormir=lambda _s: asyncio.sleep(0),
                transporte=transporte,
            )
            cofre = CofreSistema(backend_keyring=KeyringSeguroMemoria())
            sessao = SessaoSigaa(http, cofre, Path(tmp))
            sessao.ultima_view_ativa = ("/sigaa/ava/index.jsf:Principal", "910001")
            sessao.ultima_pagina_principal_turma["910001"] = HTML_LINKS_PERIGOSOS

            async def rodar() -> None:
                for mat in ("mat_01", "mat_02", "mat_03", "mat_04", "mat_05"):
                    with self.assertRaises(ErroUfc) as ctx:
                        await sessao.baixar_material_turma("910001", mat)
                    self.assertEqual(ctx.exception.codigo, CodigoErro.ACAO_BLOQUEADA, mat)
                self.assertEqual(transporte.contagem_logins, 0)

            asyncio.run(rodar())


class TestMateriaisSinteticosContinuamBaixaveis(unittest.TestCase):
    def test_todos_os_materiais_listados_pelo_parser_baixam(self) -> None:
        from ufc_mcp.fontes.sigaa.parsers.turma_virtual import parse_turma_visao_geral

        html = (
            Path(__file__).resolve().parents[1] / "paginas" / "dev" / "sigaa" / "ava_principal.html"
        ).read_text(encoding="utf-8")
        visao = parse_turma_visao_geral(html, id_turma="910001")
        ids = [m.id_material for t in visao.topicos for m in t.materiais]
        self.assertEqual(ids, ["mat_01", "mat_02"])  # antes e depois da correção: 2 materiais

        with tempfile.TemporaryDirectory() as tmp:
            http = ClienteEducado(
                Limites(pausa_minima_s=0.5),
                relogio=lambda: 10.0,
                dormir=lambda _s: asyncio.sleep(0),
                transporte=TransporteUfcSimulado(),
            )
            cofre = CofreSistema(backend_keyring=KeyringSeguroMemoria())
            cofre.salvar_credencial(Credencial(usuario="aluno", senha="senha_correta_123"))
            sessao = SessaoSigaa(http, cofre, Path(tmp))

            async def rodar() -> None:
                await sessao.abrir_turma("910001")
                for mat in ids:
                    resp, _nome = await sessao.baixar_material_turma("910001", mat)
                    self.assertEqual(resp.content_type, "application/pdf", mat)

            asyncio.run(rodar())
