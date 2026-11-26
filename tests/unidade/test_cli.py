"""Testes unitários da Interface de Linha de Comando (`cli.py` — T08)."""

from __future__ import annotations

import unittest

from ufc_mcp.cli import construir_parser_cli, main


class TestCliUfcMcp(unittest.TestCase):
    def test_subcomandos_parser(self) -> None:
        parser = construir_parser_cli()
        args1 = parser.parse_args(["login", "--so-sessao", "--cofre", "sistema"])
        self.assertEqual(args1.subcomando, "login")
        self.assertTrue(args1.so_sessao)

        args2 = parser.parse_args(["servir", "--perfil", "essencial"])
        self.assertEqual(args2.perfil, "essencial")

        args3 = parser.parse_args(["instalar", "--cliente", "claude-desktop"])
        self.assertEqual(args3.cliente, "claude-desktop")

    def test_execucao_status_e_instalar(self) -> None:
        self.assertEqual(main(["status", "--json"]), 0)
        self.assertEqual(main(["instalar", "--cliente", "cursor"]), 0)

    def test_logout_apaga_arquivos_do_cofre_sem_frase_mestra(self) -> None:
        import io
        import tempfile
        from pathlib import Path

        from ufc_mcp.cli import executar_logout
        from ufc_mcp.nucleo.credenciais import CofreComposto, CofreSessao

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "cofre.bin").write_bytes(b"UFCMCP1xxxx")
            (pasta / "sessao_efemera.json").write_text("{}", encoding="utf-8")
            # cofre composto sem CofreArquivo (sem UFC_MCP_FRASE_MESTRA)
            cofre = CofreComposto([CofreSessao()])
            saida = io.StringIO()
            codigo = executar_logout(cofre, pasta, saida)
            self.assertEqual(codigo, 0)
            self.assertFalse((pasta / "cofre.bin").exists())
            self.assertFalse((pasta / "sessao_efemera.json").exists())
            self.assertIn("cofre.bin", saida.getvalue())
            self.assertIn("sessao_efemera.json", saida.getvalue())

    def test_logout_reporta_falha(self) -> None:
        import io
        import tempfile
        from pathlib import Path

        from ufc_mcp.cli import executar_logout
        from ufc_mcp.nucleo.credenciais import CofreComposto, CofreSessao

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "cofre.bin").mkdir()  # unlink de diretório falha
            saida = io.StringIO()
            codigo = executar_logout(CofreComposto([CofreSessao()]), pasta, saida)
            self.assertEqual(codigo, 1)
            self.assertIn("FALHOU", saida.getvalue())
