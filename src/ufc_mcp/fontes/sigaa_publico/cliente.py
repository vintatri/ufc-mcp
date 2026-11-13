"""Cliente assíncrono para o portal público de cursos do SIGAA."""

from __future__ import annotations

from ufc_mcp.fontes.sigaa_publico.modelos import CalendarioCursoPublico
from ufc_mcp.fontes.sigaa_publico.parser import parse_calendario_curso_publico
from ufc_mcp.nucleo.cache import CachePublico
from ufc_mcp.nucleo.http import ClienteEducado

TTL_CURSO_PUBLICO_S = 43200  # 12h


def url_calendario_curso_publico(id_curso: int) -> str:
    return f"https://si3.ufc.br/sigaa/public/curso/calendario.jsf?lc=pt_BR&id={id_curso}"


class ClienteSigaaPublico:
    def __init__(self, http: ClienteEducado, cache: CachePublico) -> None:
        self.http = http
        self.cache = cache

    async def consultar_calendario_curso(
        self, id_curso: int, *, atualizar: bool = False
    ) -> tuple[CalendarioCursoPublico, bool, int]:
        chave = f"sigaa_pub:cal_curso:{id_curso}"
        if not atualizar:
            item = self.cache.obter(chave)
            if item is not None:
                return (
                    parse_calendario_curso_publico(item.corpo, id_curso=id_curso),
                    True,
                    item.idade_s,
                )
        resp = await self.http.get(url_calendario_curso_publico(id_curso))
        cal = parse_calendario_curso_publico(resp.texto, id_curso=id_curso)
        self.cache.guardar(chave, resp.texto, TTL_CURSO_PUBLICO_S)
        return cal, False, 0
