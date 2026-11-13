"""Cliente assíncrono com cache SQLite para o Restaurante Universitário da UFC."""

from __future__ import annotations

from datetime import date, timedelta

from ufc_mcp.fontes.ru.modelos import CardapioDia
from ufc_mcp.fontes.ru.parser import pagina_confere_com_data, parse_cardapio_ru
from ufc_mcp.fontes.ru.resolucao import resolver_restaurante
from ufc_mcp.nucleo.cache import CachePublico
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.http import ClienteEducado

TTL_CARDAPIO_S = 3600  # 1h
AVISO_DATA_DIVERGENTE = (
    "A página do RU não devolveu o cardápio de {data} (exibiu outro dia); "
    "o cardápio dessa data não está disponível."
)


def url_cardapio_ru(data_iso: str, restaurante: int) -> str:
    # A data vai como segmento de caminho; o parâmetro `?data=` é ignorado pelo site
    # (a página devolve sempre o cardápio de hoje).
    return (
        f"https://ufc2012.ufc.br/restaurante/cardapio/{restaurante}-restaurante-universitario"
        f"/{data_iso}"
    )


class ClienteRu:
    def __init__(self, http: ClienteEducado, cache: CachePublico) -> None:
        self.http = http
        self.cache = cache

    async def consultar_dia(
        self,
        data_iso: str,
        restaurante: str | int = 1,
        *,
        atualizar: bool = False,
    ) -> tuple[CardapioDia, bool, int, list[str]]:
        restaurante = resolver_restaurante(restaurante) or 1
        try:
            dt = date.fromisoformat(data_iso)
        except ValueError as exc:
            raise ErroUfc(
                CodigoErro.PARAMETRO_INVALIDO,
                f"Data inválida '{data_iso}'. Use o formato AAAA-MM-DD.",
            ) from exc

        hoje = date.today()
        if dt < hoje - timedelta(days=30) or dt > hoje + timedelta(days=14):
            raise ErroUfc(
                CodigoErro.PARAMETRO_INVALIDO,
                f"Data '{data_iso}' fora da janela permitida (hoje - 30d até hoje + 14d).",
            )

        chave = f"ru:v2:{restaurante}:{data_iso}"  # v2: descarta páginas antigas buscadas com ?data=
        avisos: list[str] = []
        if not atualizar:
            em_cache = self.cache.obter(chave)
            if em_cache is not None:
                return (
                    parse_cardapio_ru(em_cache.corpo, data=data_iso, restaurante=restaurante),
                    True,
                    em_cache.idade_s,
                    avisos,
                )

        try:
            resp = await self.http.get(url_cardapio_ru(data_iso, restaurante))
            cardapio = parse_cardapio_ru(resp.texto, data=data_iso, restaurante=restaurante)
            if not pagina_confere_com_data(resp.texto, data_iso):
                avisos.append(AVISO_DATA_DIVERGENTE.format(data=data_iso))
                return cardapio, False, 0, avisos
            self.cache.guardar(chave, resp.texto, TTL_CARDAPIO_S)
            return cardapio, False, 0, avisos
        except ErroUfc as exc:
            if exc.codigo in (CodigoErro.FONTE_INDISPONIVEL, CodigoErro.TEMPO_ESGOTADO):
                vencido = self.cache.obter_vencido(chave, max_idade_s=86400)
                if vencido is not None:
                    avisos.append("Fonte do RU indisponível no momento; exibindo cópia em cache de até 24h.")
                    return (
                        parse_cardapio_ru(vencido.corpo, data=data_iso, restaurante=restaurante),
                        True,
                        vencido.idade_s,
                        avisos,
                    )
            raise

    async def consultar_semana(
        self,
        inicio_iso: str,
        restaurante: str | int = 1,
        *,
        atualizar: bool = False,
    ) -> tuple[list[CardapioDia], bool, int, list[str]]:
        try:
            dt_ini = date.fromisoformat(inicio_iso)
        except ValueError as exc:
            raise ErroUfc(
                CodigoErro.PARAMETRO_INVALIDO,
                f"Data inicial inválida '{inicio_iso}'. Use AAAA-MM-DD.",
            ) from exc

        # Fim de semana não tem RU: usa a segunda-feira seguinte.
        lunes = dt_ini - timedelta(days=dt_ini.weekday()) if dt_ini.weekday() < 5 else dt_ini + timedelta(days=7 - dt_ini.weekday())
        dias: list[CardapioDia] = []
        algum_cache = False
        maior_idade = 0
        avisos_totais: list[str] = []

        for offset in range(5):
            dia_alvo = (lunes + timedelta(days=offset)).isoformat()
            card, em_c, idade, avs = await self.consultar_dia(
                dia_alvo, restaurante=restaurante, atualizar=atualizar
            )
            dias.append(card)
            algum_cache = algum_cache or em_c
            maior_idade = max(maior_idade, idade)
            avisos_totais.extend(avs)

        return dias, algum_cache, maior_idade, list(dict.fromkeys(avisos_totais))
