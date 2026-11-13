"""Cache Público (SQLite com auto-reparo) e Cache Pessoal (100% em memória RAM)."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple


class ItemCache(NamedTuple):
    corpo: str
    idade_s: int


class CachePublico:
    """Cache persistente em SQLite apenas para dados públicos (RU, Calendário, Notícias)."""

    def __init__(
        self,
        caminho_db: Path,
        *,
        relogio: Callable[[], float] = time.time,
    ) -> None:
        self.caminho_db = caminho_db
        self._relogio = relogio
        self.caminho_db.parent.mkdir(parents=True, exist_ok=True)
        self._inicializar()

    def _conectar(self) -> sqlite3.Connection:
        return sqlite3.connect(self.caminho_db)

    def _inicializar(self) -> None:
        try:
            with self._conectar() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cache (
                        chave TEXT PRIMARY KEY,
                        corpo TEXT NOT NULL,
                        criado_em REAL NOT NULL,
                        expira_em REAL NOT NULL
                    )
                    """
                )
                conn.execute("PRAGMA integrity_check")
        except sqlite3.DatabaseError:
            if self.caminho_db.exists():
                self.caminho_db.unlink()
            with self._conectar() as conn:
                conn.execute(
                    """
                    CREATE TABLE cache (
                        chave TEXT PRIMARY KEY,
                        corpo TEXT NOT NULL,
                        criado_em REAL NOT NULL,
                        expira_em REAL NOT NULL
                    )
                    """
                )

    def guardar(self, chave: str, corpo: str, ttl_s: int) -> None:
        agora = self._relogio()
        expira = agora + ttl_s
        try:
            with self._conectar() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cache (chave, corpo, criado_em, expira_em) VALUES (?, ?, ?, ?)",
                    (chave, corpo, agora, expira),
                )
        except sqlite3.DatabaseError:
            self._inicializar()
            with self._conectar() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cache (chave, corpo, criado_em, expira_em) VALUES (?, ?, ?, ?)",
                    (chave, corpo, agora, expira),
                )

    def obter(self, chave: str) -> ItemCache | None:
        agora = self._relogio()
        try:
            with self._conectar() as conn:
                cur = conn.execute(
                    "SELECT corpo, criado_em, expira_em FROM cache WHERE chave = ?",
                    (chave,),
                )
                row = cur.fetchone()
        except sqlite3.DatabaseError:
            self._inicializar()
            return None
        if not row:
            return None
        corpo, criado_em, expira_em = row
        if agora > expira_em:
            return None
        return ItemCache(corpo=str(corpo), idade_s=max(0, int(agora - float(criado_em))))

    def obter_vencido(self, chave: str, max_idade_s: int = 86400) -> ItemCache | None:
        agora = self._relogio()
        try:
            with self._conectar() as conn:
                cur = conn.execute(
                    "SELECT corpo, criado_em FROM cache WHERE chave = ?",
                    (chave,),
                )
                row = cur.fetchone()
        except sqlite3.DatabaseError:
            self._inicializar()
            return None
        if not row:
            return None
        corpo, criado_em = row
        idade = int(agora - float(criado_em))
        if idade > max_idade_s:
            return None
        return ItemCache(corpo=str(corpo), idade_s=max(0, idade))

    def limpar(self) -> None:
        try:
            with self._conectar() as conn:
                conn.execute("DELETE FROM cache")
        except sqlite3.DatabaseError:
            self._inicializar()


class CachePessoal:
    """
    Cache estritamente em memória RAM para páginas autenticadas do SIGAA.
    Jamais persiste dados pessoais do discente em disco (Mitigação A8 / LGPD).
    """

    def __init__(self, *, relogio: Callable[[], float] = time.time) -> None:
        self._relogio = relogio
        self._itens: dict[str, tuple[str, float, float]] = {}

    def guardar(self, chave: str, corpo: str, ttl_s: int = 300) -> None:
        agora = self._relogio()
        self._itens[chave] = (corpo, agora, agora + ttl_s)

    def obter(self, chave: str) -> ItemCache | None:
        item = self._itens.get(chave)
        if not item:
            return None
        corpo, criado_em, expira_em = item
        agora = self._relogio()
        if agora > expira_em:
            return None
        return ItemCache(corpo=corpo, idade_s=max(0, int(agora - criado_em)))

    def obter_vencido(self, chave: str, max_idade_s: int = 86400) -> ItemCache | None:
        item = self._itens.get(chave)
        if not item:
            return None
        corpo, criado_em, _ = item
        idade = int(self._relogio() - criado_em)
        if idade > max_idade_s:
            return None
        return ItemCache(corpo=corpo, idade_s=max(0, idade))

    def limpar(self) -> None:
        self._itens.clear()
