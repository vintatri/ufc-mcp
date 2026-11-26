"""Testes unitários do CachePublico (SQLite com auto-reparo) e CachePessoal (RAM) (T04)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ufc_mcp.nucleo.cache import CachePessoal, CachePublico


class TestCaches(unittest.TestCase):
    def test_cache_publico_ttl_e_autoreparo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "cache.sqlite3"
            agora = [1000.0]
            cp = CachePublico(db, relogio=lambda: agora[0])
            cp.guardar("ru:1:2026-11-13", "<html>cardapio</html>", ttl_s=60)

            item = cp.obter("ru:1:2026-11-13")
            self.assertIsNotNone(item)
            assert item is not None
            self.assertEqual(item.corpo, "<html>cardapio</html>")

            agora[0] += 120.0
            self.assertIsNone(cp.obter("ru:1:2026-11-13"))
            venc = cp.obter_vencido("ru:1:2026-11-13", max_idade_s=3600)
            self.assertIsNotNone(venc)

            # Corromper arquivo SQLite e verificar auto-reparo
            db.write_bytes(b"CORROMPIDO_NAO_SQLITE")
            self.assertIsNone(cp.obter("ru:1:2026-11-13"))
            cp.guardar("chave2", "valor2", ttl_s=60)
            self.assertIsNotNone(cp.obter("chave2"))

    def test_cache_pessoal_exclusivo_em_memoria(self) -> None:
        agora = [500.0]
        ram = CachePessoal(relogio=lambda: agora[0])
        ram.guardar("sigaa:portal", "<html>portal</html>", ttl_s=300)
        self.assertIsNotNone(ram.obter("sigaa:portal"))
        agora[0] += 301.0
        self.assertIsNone(ram.obter("sigaa:portal"))
