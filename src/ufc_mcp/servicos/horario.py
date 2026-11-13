"""
Decodificador unificado de horários do SIGAA (formato compacto `24M12`, `35T34`
e formato expandido `SEG 08:00-10:00`), detecção de choques e cálculo de janelas ociosas.
"""

from __future__ import annotations

from ufc_mcp.nucleo.modelos_base import BaseModel
from ufc_mcp.nucleo.paginas import REGEX_CODIGO_HORARIO_COMPACTO, REGEX_HORARIO_SIGAA

MAPA_DIAS_DIGITO: dict[str, str] = {
    "2": "SEG",
    "3": "TER",
    "4": "QUA",
    "5": "QUI",
    "6": "SEX",
    "7": "SAB",
}

ORDEM_DIAS: dict[str, int] = {
    "SEG": 0,
    "TER": 1,
    "QUA": 2,
    "QUI": 3,
    "SEX": 4,
    "SAB": 5,
    "DOM": 6,
}

MAPA_SLOTS_TURNO: dict[str, dict[str, tuple[str, str]]] = {
    "M": {
        "1": ("07:00", "08:00"),
        "2": ("08:00", "09:00"),
        "3": ("09:00", "10:00"),
        "4": ("10:00", "11:00"),
        "5": ("11:00", "12:00"),
        "6": ("12:00", "13:00"),
    },
    "T": {
        "1": ("13:00", "14:00"),
        "2": ("14:00", "15:00"),
        "3": ("15:00", "16:00"),
        "4": ("16:00", "17:00"),
        "5": ("17:00", "18:00"),
        "6": ("18:00", "19:00"),
    },
    "N": {
        "1": ("18:00", "19:00"),
        "2": ("19:00", "20:00"),
        "3": ("20:00", "21:00"),
        "4": ("21:00", "22:00"),
    },
}


class Horario(BaseModel):
    dia: str
    inicio: str
    fim: str


def _para_minutos(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _agrupar_slots_contiguos(turno: str, slots_str: str) -> list[tuple[str, str]]:
    mapa = MAPA_SLOTS_TURNO.get(turno.upper(), {})
    digitos = sorted({int(ch) for ch in slots_str if str(ch) in mapa})
    if not digitos:
        return []
    intervalos: list[tuple[str, str]] = []
    ini_atual, fim_atual = mapa[str(digitos[0])]
    prev_d = digitos[0]

    for d in digitos[1:]:
        ini_d, fim_d = mapa[str(d)]
        if d == prev_d + 1 and ini_d == fim_atual:
            fim_atual = fim_d
        else:
            intervalos.append((ini_atual, fim_atual))
            ini_atual, fim_atual = ini_d, fim_d
        prev_d = d

    intervalos.append((ini_atual, fim_atual))
    return intervalos


def decodificar_horario_sigaa(texto: str) -> list[Horario]:
    """
    Decodifica horários explícitos (`SEG 08:00-10:00`) e códigos compactos (`24M12`, `35T34`),
    removendo duplicatas e ordenando por dia da semana e hora de início.
    """
    encontrados: dict[tuple[str, str, str], Horario] = {}

    for m_exp in REGEX_HORARIO_SIGAA.finditer(texto.upper()):
        dia, ini, fim = m_exp.group(1), m_exp.group(2), m_exp.group(3)
        chave = (dia, ini, fim)
        encontrados[chave] = Horario(dia=dia, inicio=ini, fim=fim)

    for m_comp in REGEX_CODIGO_HORARIO_COMPACTO.finditer(texto.upper()):
        dias_str, turno, slots_str = m_comp.group(1), m_comp.group(2), m_comp.group(3)
        intervalos = _agrupar_slots_contiguos(turno, slots_str)
        for ch_dia in dias_str:
            dia_sigla = MAPA_DIAS_DIGITO.get(ch_dia)
            if not dia_sigla:
                continue
            for ini, fim in intervalos:
                chave = (dia_sigla, ini, fim)
                encontrados[chave] = Horario(dia=dia_sigla, inicio=ini, fim=fim)

    return sorted(
        encontrados.values(),
        key=lambda h: (ORDEM_DIAS.get(h.dia, 99), _para_minutos(h.inicio), _para_minutos(h.fim)),
    )


def horarios_conflitam(h1: list[Horario], h2: list[Horario]) -> list[str]:
    """
    Retorna a lista de choques de horário formatados (ex.: `['QUA 09:00-10:00']`)
    se e somente se max(a.inicio, b.inicio) < min(a.fim, b.fim) no mesmo dia.
    """
    choques: list[str] = []
    for a in h1:
        for b in h2:
            if a.dia != b.dia:
                continue
            ini_max = max(_para_minutos(a.inicio), _para_minutos(b.inicio))
            fim_min = min(_para_minutos(a.fim), _para_minutos(b.fim))
            if ini_max < fim_min:
                h_i, m_i = divmod(ini_max, 60)
                h_f, m_f = divmod(fim_min, 60)
                desc = f"{a.dia} {h_i:02d}:{m_i:02d}-{h_f:02d}:{m_f:02d}"
                if desc not in choques:
                    choques.append(desc)
    return choques


def calcular_horas_janela(horarios: list[Horario]) -> float:
    """
    Agrupa blocos por dia da semana, ordena por início e soma as diferenças positivas
    (b_{i+1}.inicio - b_i.fim) em horas para aulas no mesmo dia.
    """
    por_dia: dict[str, list[Horario]] = {}
    for h in horarios:
        por_dia.setdefault(h.dia, []).append(h)

    minutos_janela = 0
    for blocos in por_dia.values():
        ordenados = sorted(blocos, key=lambda x: (_para_minutos(x.inicio), _para_minutos(x.fim)))
        for idx in range(len(ordenados) - 1):
            fim_atual = _para_minutos(ordenados[idx].fim)
            ini_prox = _para_minutos(ordenados[idx + 1].inicio)
            if ini_prox > fim_atual:
                minutos_janela += ini_prox - fim_atual

    return round(minutos_janela / 60.0, 2)


def turno_predominante(horarios: list[Horario]) -> str:
    """Identifica se um conjunto de horários ocorre em manha, tarde, noite ou misto."""
    turnos: set[str] = set()
    for h in horarios:
        ini = _para_minutos(h.inicio)
        if ini < 13 * 60:
            turnos.add("manha")
        elif ini < 18 * 60:
            turnos.add("tarde")
        else:
            turnos.add("noite")
    if len(turnos) == 1:
        return next(iter(turnos))
    return "misto"
