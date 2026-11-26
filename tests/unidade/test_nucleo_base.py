"""Testes unitários de Config, CodigoErro, Envelope e FiltroSegredos (T01)."""

from __future__ import annotations

import json
import unittest

from ufc_mcp.nucleo.config import Config
from ufc_mcp.nucleo.envelope import AVISO_TEXTO_EXTERNO, Envelope, texto_do_envelope
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.registro import sanitizar_mensagem_log


class TestNucleoBase(unittest.TestCase):
    def test_17_codigos_erro(self) -> None:
        self.assertEqual(len(list(CodigoErro)), 17)
        self.assertIn(CodigoErro.LAYOUT_MUDOU, list(CodigoErro))
        self.assertIn(CodigoErro.ACAO_BLOQUEADA, list(CodigoErro))

    def test_config_padrao(self) -> None:
        cfg = Config()
        self.assertFalse(cfg.identificadores)
        self.assertIsNone(cfg.restaurante)
        self.assertIsNone(cfg.curso)
        self.assertEqual(cfg.perfil, "completo")
        self.assertEqual(cfg.limites.pausa_minima_s, 2.0)
        self.assertEqual(cfg.limites.max_por_minuto, 30)

    def test_envelope_com_e_sem_texto_externo(self) -> None:
        env1 = Envelope.sucesso(fonte="teste", dados={"ok": 1}, contem_texto_externo=False)
        txt1 = texto_do_envelope(env1)
        self.assertFalse(txt1.startswith(AVISO_TEXTO_EXTERNO))
        self.assertTrue(json.loads(txt1)["ok"])

        env2 = Envelope.sucesso(fonte="teste", dados={"msg": "ext"}, contem_texto_externo=True)
        txt2 = texto_do_envelope(env2)
        self.assertTrue(txt2.startswith(AVISO_TEXTO_EXTERNO))
        corpo_json = txt2.split("\n", 1)[1]
        self.assertTrue(json.loads(corpo_json)["contem_texto_externo"])

    def test_envelope_falha(self) -> None:
        erro = ErroUfc(CodigoErro.ACAO_BLOQUEADA, "Operacao proibida")
        env = Envelope.falha(fonte="teste", erro=erro)
        dados = json.loads(texto_do_envelope(env))
        self.assertFalse(dados["ok"])
        self.assertEqual(dados["erro"]["codigo"], "ACAO_BLOQUEADA")

    def test_sanitizacao_log(self) -> None:
        msg = "Aluno 000123 email aluno.exemplo@alu.ufc.br cookie JSESSIONID=ABC123XYZ senha=minhasenha"
        limpo = sanitizar_mensagem_log(msg)
        self.assertNotIn("000123", limpo)
        self.assertNotIn("aluno.exemplo@alu.ufc.br", limpo)
        self.assertNotIn("ABC123XYZ", limpo)
        self.assertNotIn("minhasenha", limpo)
        self.assertIn("[NUM]", limpo)
        self.assertIn("[EMAIL]", limpo)
        self.assertIn("JSESSIONID=[SESSAO]", limpo)

    def test_sanitizacao_log_cpf_cookie_e_senha_com_aspas(self) -> None:
        msg = (
            'CPF 123.456.789-00 | Cookie: JSESSIONID=AAA; outro=BBB | Set-Cookie: x=CCC; Path=/\n'
            'user.senha: "minha senha longa" e {"senha": "outra com espacos"} senha=\'tres palavras\''
        )
        limpo = sanitizar_mensagem_log(msg)
        for vazado in ("123.456.789-00", "AAA", "BBB", "CCC", "minha senha longa", "outra com espacos", "tres palavras"):
            self.assertNotIn(vazado, limpo)
        self.assertIn("[CPF]", limpo)
