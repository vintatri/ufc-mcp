"""
Exportador de Agenda Acadêmica para iCalendar RFC 5545 (`.ics`).
Respeita dobras de linha em 75 octetos UTF-8, `RRULE:FREQ=WEEKLY;UNTIL=...` e confinamento local.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from ufc_mcp.fontes.calendario.modelos import EventoCalendario
from ufc_mcp.fontes.sigaa.modelos import TurmaPortal

MAPA_DIA_RRULE: dict[str, tuple[str, int]] = {
    "SEG": ("MO", 0),
    "TER": ("TU", 1),
    "QUA": ("WE", 2),
    "QUI": ("TH", 3),
    "SEX": ("FR", 4),
    "SAB": ("SA", 5),
    "DOM": ("SU", 6),
}


def dobrar_linha_ics(linha: str) -> str:
    """Dobra linhas com mais de 75 octetos UTF-8 segundo a RFC 5545 (CRLF + espaço)."""
    raw = linha.encode("utf-8")
    if len(raw) <= 75:
        return linha
    partes: list[str] = []
    atual = bytearray()
    limite = 75
    for ch in linha:
        ch_bytes = ch.encode("utf-8")
        if len(atual) + len(ch_bytes) > limite:
            partes.append(atual.decode("utf-8"))
            atual = bytearray(b" " + ch_bytes)
            limite = 75
        else:
            atual.extend(ch_bytes)
    if atual:
        partes.append(atual.decode("utf-8"))
    return "\r\n".join(partes)


def _escapar_ics(texto: str) -> str:
    return (
        texto.replace("\\", "\\\\")
        .replace(";", r"\;")
        .replace(",", r"\,")
        .replace("\n", "\\n")
    )


def gerar_conteudo_ics(
    turmas: list[TurmaPortal],
    eventos_calendario: list[EventoCalendario],
    *,
    data_referencia: date | None = None,
) -> str:
    hoje = data_referencia or date.today()
    dtstamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    linhas: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//UFC-MCP//Copiloto Academico UFC v0.9.0//PT",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for t in turmas:
        dt_base = date.fromisoformat(t.inicio_vigencia) if t.inicio_vigencia else hoje
        fim_vig = date.fromisoformat(t.fim_vigencia) if t.fim_vigencia else (hoje + timedelta(days=120))
        until_str = fim_vig.strftime("%Y%m%dT235959Z")

        for idx, h in enumerate(t.horarios):
            byday, wd_alvo = MAPA_DIA_RRULE.get(h.dia, ("MO", 0))
            diff = (wd_alvo - dt_base.weekday()) % 7
            primeiro_dia = dt_base + timedelta(days=diff)
            h_ini = h.inicio.replace(":", "") + "00"
            h_fim = h.fim.replace(":", "") + "00"
            dia_str = primeiro_dia.strftime("%Y%m%d")

            linhas.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:turma-{t.id_turma}-{idx}@ufc-mcp.local",
                    f"DTSTAMP:{dtstamp}",
                    f"DTSTART;TZID=America/Fortaleza:{dia_str}T{h_ini}",
                    f"DTEND;TZID=America/Fortaleza:{dia_str}T{h_fim}",
                    f"RRULE:FREQ=WEEKLY;BYDAY={byday};UNTIL={until_str}",
                    f"SUMMARY:{_escapar_ics(f'{t.codigo} - {t.nome}')}",
                    f"LOCATION:{_escapar_ics(t.local)}",
                    "END:VEVENT",
                ]
            )

    for idx_ev, ev in enumerate(eventos_calendario):
        ini_s = ev.inicio.replace("-", "")
        fim_dt = date.fromisoformat(ev.fim) + timedelta(days=1)
        fim_s = fim_dt.strftime("%Y%m%d")
        linhas.extend(
            [
                "BEGIN:VEVENT",
                f"UID:cal-ufc-{ini_s}-{idx_ev}@ufc-mcp.local",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART;VALUE=DATE:{ini_s}",
                f"DTEND;VALUE=DATE:{fim_s}",
                f"SUMMARY:{_escapar_ics(ev.descricao)}",
                "END:VEVENT",
            ]
        )

    linhas.append("END:VCALENDAR")
    dobradas = [dobrar_linha_ics(ln) for ln in linhas]
    return "\r\n".join(dobradas) + "\r\n"


def exportar_arquivo_ics(
    pasta_documentos: Path,
    turmas: list[TurmaPortal],
    eventos_calendario: list[EventoCalendario],
    *,
    data_referencia: date | None = None,
) -> Path:
    hoje = data_referencia or date.today()
    pasta_documentos.mkdir(parents=True, exist_ok=True)
    caminho = (pasta_documentos / f"agenda-ufc-{hoje.isoformat()}.ics").resolve()
    conteudo = gerar_conteudo_ics(turmas, eventos_calendario, data_referencia=hoje)
    caminho.write_bytes(conteudo.encode("utf-8"))
    return caminho
