"""Serviços `dia` e `semana` com degradação graciosa entre fontes."""

from __future__ import annotations

from datetime import date, timedelta

from ufc_mcp.fontes.calendario.cliente import ClienteCalendario
from ufc_mcp.fontes.ru.cliente import ClienteRu
from ufc_mcp.fontes.sigaa.cliente import ClienteSigaa
from ufc_mcp.nucleo.erros import ErroUfc
from ufc_mcp.servicos.onde_aula import MAPA_WEEKDAY_SIGLA


async def construir_meu_dia(
    sigaa: ClienteSigaa,
    ru: ClienteRu,
    calendario: ClienteCalendario,
    *,
    data_iso: str,
    restaurante: int = 1,
    atualizar: bool = False,
) -> tuple[dict[str, object], list[str], bool]:
    dt = date.fromisoformat(data_iso)
    sigla_dia, _ = MAPA_WEEKDAY_SIGLA[dt.weekday()]
    avisos: list[str] = []
    contem_ext = False

    aulas_dia: list[dict[str, object]] = []
    atividades_proximas: list[dict[str, object]] = []
    try:
        portal, _, _ = await sigaa.obter_resumo_portal(atualizar=atualizar)
        for t in portal.turmas:
            hs = [h.model_dump() for h in t.horarios if h.dia == sigla_dia]
            if hs:
                aulas_dia.append(
                    {
                        "id_turma": t.id_turma,
                        "codigo": t.codigo,
                        "nome": t.nome,
                        "local": t.local,
                        "horarios": hs,
                    }
                )
        for at in portal.atividades_proximas:
            contem_ext = True
            atividades_proximas.append(at.model_dump())
    except ErroUfc as exc:
        avisos.append(f"Portal do Discente indisponível ou sem login: {exc.mensagem}")

    cardapio_dict: dict[str, object] | None = None
    try:
        card, _, _, avs_ru = await ru.consultar_dia(
            data_iso, restaurante=restaurante, atualizar=atualizar
        )
        cardapio_dict = card.model_dump()
        avisos.extend(avs_ru)
    except ErroUfc as exc:
        avisos.append(f"Cardápio do RU indisponível: {exc.mensagem}")

    eventos_cal: list[dict[str, object]] = []
    try:
        evs, _, _, _, avs_cal = await calendario.consultar_eventos(
            data_iso, data_iso, atualizar=atualizar
        )
        eventos_cal = [e.model_dump() for e in evs]
        avisos.extend(avs_cal)
    except ErroUfc as exc:
        avisos.append(f"Calendário Universitário indisponível: {exc.mensagem}")

    return (
        {
            "data": data_iso,
            "dia_semana": sigla_dia,
            "aulas_do_dia": aulas_dia,
            "cardapio_ru": cardapio_dict,
            "eventos_calendario": eventos_cal,
            "atividades_proximas": atividades_proximas,
        },
        avisos,
        contem_ext,
    )


async def construir_minha_semana(
    sigaa: ClienteSigaa,
    ru: ClienteRu,
    calendario: ClienteCalendario,
    *,
    inicio_iso: str,
    restaurante: int = 1,
    atualizar: bool = False,
) -> tuple[dict[str, object], list[str], bool]:
    dt_ini = date.fromisoformat(inicio_iso)
    dt_fim = dt_ini + timedelta(days=6)
    avisos: list[str] = []
    contem_ext = False

    turmas_semana: list[dict[str, object]] = []
    atividades: list[dict[str, object]] = []
    try:
        portal, _, _ = await sigaa.obter_resumo_portal(atualizar=atualizar)
        turmas_semana = [t.model_dump() for t in portal.turmas]
        for at in portal.atividades_proximas:
            contem_ext = True
            atividades.append(at.model_dump())
    except ErroUfc as exc:
        avisos.append(f"SIGAA indisponível: {exc.mensagem}")

    cardapios_semana: list[dict[str, object]] = []
    try:
        # `consultar_semana` devolve segunda a sexta da semana que contém a data pedida; a janela
        # de 7 dias pode cruzar duas semanas, então consulta cada semana tocada e filtra a janela.
        segundas: list[str] = []
        d_atual = dt_ini
        while d_atual <= dt_fim:
            segunda = (d_atual - timedelta(days=d_atual.weekday())).isoformat()
            if segunda not in segundas:
                segundas.append(segunda)
            d_atual += timedelta(days=1)
        vistos: set[str] = set()
        for segunda in segundas:
            cards, _, _, avs_ru = await ru.consultar_semana(
                segunda, restaurante=restaurante, atualizar=atualizar
            )
            avisos.extend(a for a in avs_ru if a not in avisos)
            for c in cards:
                data_c = str(c.data)
                if dt_ini.isoformat() <= data_c <= dt_fim.isoformat() and data_c not in vistos:
                    vistos.add(data_c)
                    cardapios_semana.append(c.model_dump())
    except ErroUfc as exc:
        avisos.append(f"RU indisponível: {exc.mensagem}")

    eventos_semana: list[dict[str, object]] = []
    try:
        evs, _, _, _, avs_cal = await calendario.consultar_eventos(
            dt_ini.isoformat(), dt_fim.isoformat(), atualizar=atualizar
        )
        eventos_semana = [e.model_dump() for e in evs]
        avisos.extend(avs_cal)
    except ErroUfc as exc:
        avisos.append(f"Calendário indisponível: {exc.mensagem}")

    return (
        {
            "inicio": dt_ini.isoformat(),
            "fim": dt_fim.isoformat(),
            "turmas": turmas_semana,
            "cardapios_uteis": cardapios_semana,
            "eventos_calendario": eventos_semana,
            "atividades_proximas": atividades,
        },
        avisos,
        contem_ext,
    )
