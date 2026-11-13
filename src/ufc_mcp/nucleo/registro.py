"""Registro (logging) estruturado com filtro ativo de segredos e proibição de stdout."""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

REGEX_MATRICULA_OU_CPF = re.compile(r"\b\d{6,}\b")
REGEX_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
REGEX_JSESSIONID = re.compile(r'(?i)JSESSIONID=[^;\s"\']+')
REGEX_SENHA_PARAM = re.compile(r'(?i)(senha|password|secret|token)\s*[=:]\s*[^&\s"\']+')


def sanitizar_mensagem_log(texto: str) -> str:
    """Remove matrículas, CPFs, e-mails, JSESSIONID e senhas de qualquer string de log."""
    limpo = REGEX_JSESSIONID.sub("JSESSIONID=[SESSAO]", texto)
    limpo = REGEX_SENHA_PARAM.sub(r"\1=[OCULTO]", limpo)
    limpo = REGEX_EMAIL.sub("[EMAIL]", limpo)
    limpo = REGEX_MATRICULA_OU_CPF.sub("[NUM]", limpo)
    return limpo


class FiltroSegredos(logging.Filter):
    """Filtro que sanitiza mensagens e argumentos de LogRecord antes da emissão."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = sanitizar_mensagem_log(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: sanitizar_mensagem_log(str(v)) for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(sanitizar_mensagem_log(str(a)) for a in record.args)
        return True


def configurar_registro(nivel: str = "INFO", arquivo_log: Path | None = None) -> logging.Logger:
    """Configura o logger `ufc_mcp` escrevendo exclusivamente em stderr ou arquivo (nunca stdout)."""
    logger = logging.getLogger("ufc_mcp")
    logger.setLevel(getattr(logging, nivel.upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    filtro = FiltroSegredos()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    handler_stderr = logging.StreamHandler(sys.stderr)
    handler_stderr.addFilter(filtro)
    handler_stderr.setFormatter(formatter)
    logger.addHandler(handler_stderr)

    if arquivo_log is not None:
        arquivo_log.parent.mkdir(parents=True, exist_ok=True)
        handler_file = logging.FileHandler(arquivo_log, encoding="utf-8")
        handler_file.addFilter(filtro)
        handler_file.setFormatter(formatter)
        logger.addHandler(handler_file)

    return logger
