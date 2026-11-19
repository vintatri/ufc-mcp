"""
Serviço `aula`: cruza grade horária fixa, avisos recentes com
Filtro de Relevância Temporal (janela de 7 dias ou menção explícita `dd/mm`),
cronograma do Plano de Curso, avaliações agendadas e feriados do Calendário Universitário.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from ufc_mcp.fontes.calendario.cliente import ClienteCalendario
from ufc_mcp.fontes.sigaa.cliente import ClienteSigaa
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.higiene import TextoExterno, externo
from ufc_mcp.nucleo.modelos_base import BaseModel, Field
from ufc_mcp.servicos.horario import Horario

MAPA_WEEKDAY_SIGLA: dict[int, tuple[str, tuple[str, ...]]] = {
    0: ("SEG", ("segunda", "segunda-feira")),
    1: ("TER", ("terça", "terca", "terça-feira", "terca-feira")),
    2: ("QUA", ("quarta", "quarta-feira")),
    3: ("QUI", ("quinta", "quinta-feira")),
    4: ("SEX", ("sexta", "sexta-feira")),
    5: ("SAB", ("sábado", "sabado")),
    6: ("DOM", ("domingo",)),
}

REGEX_MUDANCA_SALA = re.compile(
    r"(?i)\b(bloco\s*\d+|sala\s*[a-z0-9]+|laborat[oó]rio|lab\.|audit[oó]rio|remota|online|google\s*meet|teams)\b"
)
REGEX_CANCELAMENTO_AULA = re.compile(
    r"(?i)\b(n[aã]o\s+haver[aá]\s+aula|aula\s+cancelada|aula\s+suspensa|sem\s+aula|enferm|atestado)\b"
)
REGEX_DIA_AVALIACAO = re.compile(
    r"(?i)\b(prova|avalia[cç][aã]o|ap[123]|segunda\s+chamada|semin[aá]rio|apresenta[cç][aã]o)\b"
)
REGEX_DEITICO_RECENTE = re.compile(
    r"(?i)\b(hoje|amanh[aã]|esta\s+semana|pr[oó]xima\s+aula|nesta\s+aula)\b"
)

StatusInferidoAula = Literal[
    "NORMAL",
    "POSSIVEL_MUDANCA_SALA",
    "POSSIVEL_CANCELAMENTO",
    "DIA_DE_AVALIACAO",
    "FERIADO_CALENDARIO",
    "DADOS_INDISPONIVEIS",
]

TipoSinalAula = Literal[
    "FERIADO", "AVALIACAO_AGENDADA", "CANCELAMENTO", "MUDANCA_SALA", "MENCAO_AVALIACAO"
]


class SinalDetectado(BaseModel):
    """Sinal inferido: `descricao` é texto do sistema; o trecho de terceiros vai em TextoExterno."""

    tipo: TipoSinalAula
    fonte: str
    descricao: str
    trecho: TextoExterno | None = None


class AvisoAnalisadoAula(BaseModel):
    titulo: TextoExterno
    corpo: TextoExterno
    publicada_em: str | None = None
    relevante_para_data: bool = False
    motivo_relevancia: str | None = None


class DiagnosticoOndeAulaItem(BaseModel):
    id_turma: str
    codigo: str
    nome: str
    horario_padrao: list[Horario] = Field(default_factory=list)
    local_padrao: str
    centro_ou_campus: str
    bloco: str
    sala: str
    status_inferido: StatusInferidoAula
    sinais_detectados: list[SinalDetectado] = Field(default_factory=list)
    leituras_indisponiveis: list[str] = Field(default_factory=list)
    topico_plano_aula: TextoExterno | None = None
    ultimos_avisos: list[AvisoAnalisadoAula] = Field(default_factory=list)


def decompor_local_ufc(local_bruto: str) -> tuple[str, str, str]:
    """Decompõe 'CT - Bloco 710 - Sala B' em (centro, bloco, sala)."""
    partes = [p.strip() for p in local_bruto.split("-") if p.strip()]
    centro = partes[0] if len(partes) >= 1 else "Campus do Pici"
    bloco = "Não especificado"
    sala = "Não especificada"
    for p in partes:
        if re.search(r"bloco|did[aá]tico|dep", p, re.I):
            bloco = p
        elif re.search(r"sala|lab|audit", p, re.I):
            sala = p
    if bloco == "Não especificado" and len(partes) >= 2:
        bloco = partes[1]
    if sala == "Não especificada" and len(partes) >= 3:
        sala = partes[2]
    return centro, bloco, sala


def aviso_eh_relevante_para_data(
    *,
    texto_aviso: str,
    publicada_em_iso: str | None,
    data_alvo: date,
    eh_mais_recente_do_topo: bool = False,
) -> tuple[bool, str | None]:
    """
    Filtro de Relevância Temporal de Avisos (Parte 05, Ferramenta 27):
    Impede que avisos antigos do início do semestre gerem falsos alertas.
    """
    dd_mm = f"{data_alvo.day:02d}/{data_alvo.month:02d}"
    dd_mm_curto = f"{data_alvo.day}/{data_alvo.month:02d}"
    dd_mm_aaaa = f"{data_alvo.day:02d}/{data_alvo.month:02d}/{data_alvo.year:04d}"

    if dd_mm_aaaa in texto_aviso or re.search(rf"\b{re.escape(dd_mm)}\b", texto_aviso) or re.search(rf"\b{re.escape(dd_mm_curto)}\b", texto_aviso):
        return True, f"menciona_data_explicita:{dd_mm}"

    # Se o aviso menciona explicitamente outra data dd/mm diferente de data_alvo, descarta!
    outras_datas = re.findall(r"\b(\d{1,2}/\d{2})(?:/\d{4})?\b", texto_aviso)
    if outras_datas:
        return False, "menciona_outra_data"

    dentro_janela_7d = False
    if publicada_em_iso:
        try:
            dt_pub = date.fromisoformat(publicada_em_iso[:10])
            delta_dias = (data_alvo - dt_pub).days
            if 0 <= delta_dias <= 7:
                dentro_janela_7d = True
        except ValueError:
            pass
    elif eh_mais_recente_do_topo:
        dentro_janela_7d = True

    if not dentro_janela_7d:
        return False, "fora_da_janela_temporal_7d"

    _, nomes_dia = MAPA_WEEKDAY_SIGLA.get(data_alvo.weekday(), ("SEG", ()))
    texto_lower = texto_aviso.lower()
    if REGEX_DEITICO_RECENTE.search(texto_aviso) or any(nd in texto_lower for nd in nomes_dia):
        return True, "janela_7d_com_deitico_temporal"

    return False, "sem_marcador_temporal_para_data"


async def consultar_onde_e_minha_aula(
    sigaa: ClienteSigaa,
    calendario: ClienteCalendario,
    *,
    data_iso: str,
    id_turma: str | None = None,
    atualizar: bool = False,
) -> dict[str, object]:
    try:
        dt_alvo = date.fromisoformat(data_iso)
    except ValueError as exc:
        raise ErroUfc(
            CodigoErro.PARAMETRO_INVALIDO,
            f"Data inválida '{data_iso}'. Use AAAA-MM-DD.",
        ) from exc

    sigla_dia, _ = MAPA_WEEKDAY_SIGLA[dt_alvo.weekday()]
    portal, _, _ = await sigaa.obter_resumo_portal(atualizar=atualizar)

    eventos_dia, _, _, _, _ = await calendario.consultar_eventos(
        data_iso, data_iso, atualizar=atualizar
    )
    feriados_dia = [ev.descricao for ev in eventos_dia if ev.eh_feriado_ou_recesso]
    avisos_gerais: list[str] = []

    aulas_resultado: list[DiagnosticoOndeAulaItem] = []

    for turma in portal.turmas:
        if id_turma and turma.id_turma != id_turma:
            continue
        horarios_hoje = [h for h in turma.horarios if h.dia == sigla_dia]
        if not horarios_hoje and not id_turma:
            continue

        centro, bloco, sala = decompor_local_ufc(turma.local)
        sinais: list[SinalDetectado] = []
        indisponiveis: list[str] = []
        status: StatusInferidoAula = "NORMAL"

        if feriados_dia:
            status = "FERIADO_CALENDARIO"
            sinais.append(
                SinalDetectado(
                    tipo="FERIADO",
                    fonte="Calendário Universitário",
                    descricao="O Calendário Universitário registra feriado/recesso nesta data.",
                    trecho=externo(feriados_dia[0], origem="calendario:feriado", max_chars=300),
                )
            )

        # 1. Plano de Curso (tópico exato da data)
        topico_plano: TextoExterno | None = None
        try:
            plano, _, _ = await sigaa.obter_turma_plano_curso(turma.id_turma, atualizar=atualizar)
            for item_c in plano.cronograma_aulas:
                if item_c.data == data_iso:
                    topico_plano = item_c.topico
                    break
        except ErroUfc as exc:
            indisponiveis.append("plano de curso")
            avisos_gerais.append(
                f"Turma {turma.id_turma}: leitura do plano de curso falhou ({exc.codigo})."
            )

        # 2. Avaliações agendadas na data
        try:
            avals, _, _ = await sigaa.obter_turma_avaliacoes(turma.id_turma, atualizar=atualizar)
            for av in avals.avaliacoes:
                if av.data == data_iso:
                    status = "DIA_DE_AVALIACAO"
                    sinais.append(
                        SinalDetectado(
                            tipo="AVALIACAO_AGENDADA",
                            fonte="Avaliações da Turma Virtual",
                            descricao="Avaliação agendada na data.",
                            trecho=av.descricao,
                        )
                    )
        except ErroUfc as exc:
            indisponiveis.append("avaliações agendadas")
            avisos_gerais.append(
                f"Turma {turma.id_turma}: leitura das avaliações falhou ({exc.codigo})."
            )

        # 3. Avisos da Turma Virtual com Filtro de Relevância Temporal
        avisos_analisados: list[AvisoAnalisadoAula] = []
        try:
            not_turma, _, _ = await sigaa.obter_turma_noticias(turma.id_turma, atualizar=atualizar)
            for idx, n in enumerate(not_turma.noticias[:5]):
                texto_comb = f"{n.titulo.texto_externo} — {n.corpo.texto_externo}"
                relevante, motivo = aviso_eh_relevante_para_data(
                    texto_aviso=texto_comb,
                    publicada_em_iso=n.publicada_em,
                    data_alvo=dt_alvo,
                    eh_mais_recente_do_topo=(idx == 0),
                )
                avisos_analisados.append(
                    AvisoAnalisadoAula(
                        titulo=n.titulo,
                        corpo=n.corpo,
                        publicada_em=n.publicada_em,
                        relevante_para_data=relevante,
                        motivo_relevancia=motivo,
                    )
                )
        except ErroUfc as exc:
            indisponiveis.append("avisos do professor")
            avisos_gerais.append(
                f"Turma {turma.id_turma}: leitura dos avisos falhou ({exc.codigo})."
            )

        # 4. Aplicar detectores semânticos apenas nos textos relevantes para a data
        textos_para_inspecionar: list[tuple[str, str]] = []
        if topico_plano is not None:
            textos_para_inspecionar.append(("Plano de Curso", topico_plano.texto_externo))
        for av_rel in avisos_analisados:
            if av_rel.relevante_para_data:
                textos_para_inspecionar.append(
                    ("Aviso Recente do Professor", f"{av_rel.titulo.texto_externo}: {av_rel.corpo.texto_externo}")
                )

        for fonte_sinal, txt_sinal in textos_para_inspecionar:
            trecho = externo(txt_sinal, origem=f"turma:{turma.id_turma}:sinal", max_chars=600)
            if REGEX_CANCELAMENTO_AULA.search(txt_sinal):
                status = "POSSIVEL_CANCELAMENTO"
                sinais.append(
                    SinalDetectado(
                        tipo="CANCELAMENTO",
                        fonte=fonte_sinal,
                        descricao="Indício de cancelamento/suspensão.",
                        trecho=trecho,
                    )
                )
            elif REGEX_MUDANCA_SALA.search(txt_sinal) and status != "POSSIVEL_CANCELAMENTO":
                status = "POSSIVEL_MUDANCA_SALA"
                sinais.append(
                    SinalDetectado(
                        tipo="MUDANCA_SALA",
                        fonte=fonte_sinal,
                        descricao="Indício de mudança de sala/laboratório.",
                        trecho=trecho,
                    )
                )
            elif REGEX_DIA_AVALIACAO.search(txt_sinal) and status == "NORMAL":
                status = "DIA_DE_AVALIACAO"
                sinais.append(
                    SinalDetectado(
                        tipo="MENCAO_AVALIACAO",
                        fonte=fonte_sinal,
                        descricao="Menção a avaliação/prova.",
                        trecho=trecho,
                    )
                )

        if indisponiveis and status == "NORMAL":
            # nunca apresentar "NORMAL" como dado real quando faltou ler fontes
            status = "DADOS_INDISPONIVEIS"

        aulas_resultado.append(
            DiagnosticoOndeAulaItem(
                id_turma=turma.id_turma,
                codigo=turma.codigo,
                nome=turma.nome,
                horario_padrao=horarios_hoje,
                local_padrao=turma.local,
                centro_ou_campus=centro,
                bloco=bloco,
                sala=sala,
                status_inferido=status,
                sinais_detectados=sinais,
                leituras_indisponiveis=indisponiveis,
                topico_plano_aula=topico_plano,
                ultimos_avisos=avisos_analisados,
            )
        )

    return {
        "data": data_iso,
        "dia_semana": sigla_dia,
        "eh_feriado_ou_recesso": len(feriados_dia) > 0,
        "eventos_calendario_dia": [
            externo(f, origem="calendario:evento", max_chars=300).model_dump() for f in feriados_dia
        ],
        "aulas": [a.model_dump() for a in aulas_resultado],
        "avisos": avisos_gerais,
    }
