"""Testes de segurança da arquitetura tripla de Cofre (CofreSistema, CofreSessao, CofreArquivo) (T05)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ufc_mcp.nucleo.credenciais import (
    CofreArquivo,
    CofreSessao,
    CofreSistema,
    Credencial,
    SessaoGuardada,
)
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc


class KeyringInseguroFalso:
    __module__ = "keyrings.alt.file"


class KeyringSeguroMemoria:
    __module__ = "keyring.backends.SecretService"

    def __init__(self) -> None:
        self.dados: dict[tuple[str, str], str] = {}

    def set_password(self, s: str, k: str, v: str) -> None:
        self.dados[(s, k)] = v

    def get_password(self, s: str, k: str) -> str | None:
        return self.dados.get((s, k))

    def delete_password(self, s: str, k: str) -> None:
        self.dados.pop((s, k), None)


class TestCofres(unittest.TestCase):
    def test_rejeicao_keyrings_alt(self) -> None:
        cs = CofreSistema(backend_keyring=KeyringInseguroFalso())
        with self.assertRaises(ErroUfc) as ctx:
            cs.salvar_credencial(Credencial(usuario="aluno", senha="123"))
        self.assertEqual(ctx.exception.codigo, CodigoErro.COFRE_INDISPONIVEL)

    def test_cofre_sistema_seguro(self) -> None:
        kr = KeyringSeguroMemoria()
        cs = CofreSistema(backend_keyring=kr)
        cs.salvar_credencial(Credencial(usuario="aluno_ufc", senha="segredo"))
        self.assertEqual(cs.estado(), "guardada")
        lida = cs.obter_credencial()
        self.assertIsNotNone(lida)
        assert lida is not None
        self.assertEqual(lida.usuario, "aluno_ufc")

    def test_cofre_sessao_jamais_salva_senha(self) -> None:
        kr = KeyringSeguroMemoria()
        csess = CofreSessao(backend_keyring=kr)
        with self.assertRaises(ErroUfc) as ctx:
            csess.salvar_credencial(Credencial(usuario="a", senha="b"))
        self.assertEqual(ctx.exception.codigo, CodigoErro.ACAO_BLOQUEADA)

        csess.salvar_sessao(SessaoGuardada(cookies={"JSESSIONID": "S123"}))
        self.assertEqual(csess.estado(), "so_sessao")
        self.assertIsNone(csess.obter_credencial())
        s = csess.obter_sessao()
        self.assertIsNotNone(s)
        assert s is not None
        self.assertEqual(s.cookies["JSESSIONID"], "S123")

    def test_cofre_arquivo_aes_gcm_argon2id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            arq = Path(tmp) / "cofre.bin"
            ca = CofreArquivo(arq, "frase_forte_2026")
            ca.salvar_credencial(Credencial(usuario="u1", senha="s1"))
            self.assertTrue(arq.read_bytes().startswith(b"UFCMCP1"))
            self.assertEqual(ca.estado(), "guardada")

            ca_errado = CofreArquivo(arq, "frase_incorreta")
            with self.assertRaises(ErroUfc) as ctx:
                ca_errado.obter_credencial()
            self.assertEqual(ctx.exception.codigo, CodigoErro.CREDENCIAL_INVALIDA)


class TestFraseMestraMinima(unittest.TestCase):
    def test_frase_curta_recusada(self) -> None:
        import tempfile
        from pathlib import Path

        from ufc_mcp.nucleo.erros import ErroUfc

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ErroUfc):
                CofreArquivo(Path(tmp) / "cofre.bin", "curta123")
            CofreArquivo(Path(tmp) / "cofre.bin", "doze_chars_ok")

    def test_sem_argon2_gera_erro_claro(self) -> None:
        import sys
        from unittest import mock

        from ufc_mcp.nucleo.credenciais import _derivar_chave_argon2id
        from ufc_mcp.nucleo.erros import ErroUfc

        with (
            mock.patch.dict(sys.modules, {"argon2": None, "argon2.low_level": None}),
            self.assertRaises(ErroUfc) as ctx,
        ):
            _derivar_chave_argon2id("frase_mestra_longa", b"0" * 16)
        self.assertIn("argon2", ctx.exception.mensagem)
