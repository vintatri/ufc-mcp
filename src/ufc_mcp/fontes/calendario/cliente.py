"""Cliente assíncrono com cache para o Calendário Universitário da UFC."""

from __future__ import annotations

from datetime import date

from ufc_mcp.fontes.calendario.modelos import EventoCalendario, ResultadoCalendario
from ufc_mcp.fontes.calendario.parser import parse_calendario_ufc
from ufc_mcp.nucleo.cache import CachePublico
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.higiene import sem_acentos_minusculo
from ufc_mcp.nucleo.http import ClienteEducado

TTL_CALENDARIO_S = 43200  # 12h
URL_CALENDARIO_UFC = "https://ufc2012.ufc.br/calendario-universitario/2026"


class ClienteCalendario:
    def __init__(self, http: ClienteEducado, cache: CachePublico) -> None:
        self.http = http
        self.cache = cache

    async def consultar_eventos(
        self,
        inicio_iso: str,
        fim_iso: str,
        *,
        texto: str | None = None,
        limite: int = 50,
        atualizar: bool = False,
    ) -> tuple[list[EventoCalendario], int, bool, int, list[str]]:
        try:
            dt_ini = date.fromisoformat(inicio_iso)
            dt_fim = date.fromisoformat(fim_iso)
        except ValueError as exc:
            raise ErroUfc(
                CodigoErro.PARAMETRO_INVALIDO,
                "Datas de início e fim devem estar no formato AAAA-MM-DD.",
            ) from exc

        if dt_fim < dt_ini or (dt_fim - dt_ini).days > 400:
            raise ErroUfc(
                CodigoErro.PARAMETRO_INVALIDO,
                "Intervalo de datas inválido (máximo de 400 dias e fim >= início).",
            )

        chave = f"calendario:{dt_ini.year}"
        avisos: list[str] = []
        res_cal: ResultadoCalendario | None = None
        em_cache = False
        idade = 0

        if not atualizar:
            item = self.cache.obter(chave)
            if item is not None:
                res_cal = parse_calendario_ufc(item.corpo, ano_padrao=dt_ini.year)
                em_cache = True
                idade = item.idade_s

        if res_cal is None:
            try:
                resp = await self.http.get(URL_CALENDARIO_UFC)
                res_cal = parse_calendario_ufc(resp.texto, ano_padrao=dt_ini.year)
                self.cache.guardar(chave, resp.texto, TTL_CALENDARIO_S)
            except ErroUfc as exc:
                if exc.codigo in (CodigoErro.FONTE_INDISPONIVEL, CodigoErro.TEMPO_ESGOTADO):
                    venc = self.cache.obter_vencido(chave, max_idade_s=86400)
                    if venc is not None:
                        avisos.append("Portal do Calendário indisponível; usando cache recente.")
                        res_cal = parse_calendario_ufc(venc.corpo, ano_padrao=dt_ini.year)
                        em_cache = True
                        idade = venc.idade_s
                    else:
                        raise
                else:
                    raise

        termo_norm = sem_acentos_minusculo(texto) if texto else None
        filtrados: list[EventoCalendario] = []
        for ev in res_cal.eventos:
            if ev.fim < inicio_iso or ev.inicio > fim_iso:
                continue
            if termo_norm and termo_norm not in sem_acentos_minusculo(ev.descricao):
                continue
            filtrados.append(ev)
            if len(filtrados) >= max(1, min(limite, 200)):
                break

        return filtrados, res_cal.nao_interpretados, em_cache, idade, avisos
