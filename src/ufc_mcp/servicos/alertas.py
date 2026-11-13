"""
Serviço `alertas`: Painel proativo de riscos acadêmicos do estudante.
Combina:
1. Semáforo de faltas segundo o Art. 113 do Regimento Geral da UFC;
2. Matriz conjunta (enviada x delta_h) para tarefas da Turma Virtual;
3. Diagnóstico regimental de notas e Avaliação Final (Art. 114);
4. Provas próximas e regularidade na biblioteca.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from ufc_mcp.fontes.sigaa.cliente import ClienteSigaa
from ufc_mcp.nucleo.erros import ErroUfc
from ufc_mcp.nucleo.higiene import TextoExterno
from ufc_mcp.nucleo.modelos_base import BaseModel
from ufc_mcp.servicos.faltas import DiagnosticoFaltasDisciplina, calcular_faltas_disciplina
from ufc_mcp.servicos.notas_ufc import DiagnosticoNotasUfc, diagnosticar_notas_ufc

SeveridadeAlerta = Literal["CRITICO", "ATENCAO", "INFORMATIVO", "CONCLUIDA", "OK"]
CorSemaforo = Literal["VERMELHO", "AMARELO", "VERDE"]


class AlertaTarefaItem(BaseModel):
    id_turma: str
    turma: str
    titulo: TextoExterno
    fim_entrega: str
    horas_restantes: float
    enviada: bool | None
    severidade: SeveridadeAlerta
    semaforo: CorSemaforo
    verificacao_envio: Literal["confirmada_no_ava", "indisponivel_confirmar_no_ava"]
    motivo: str | None = None


class AlertaAvaliacaoItem(BaseModel):
    id_turma: str
    turma: str
    data: str
    hora: str | None = None
    descricao: TextoExterno
    horas_restantes: float
    severidade: SeveridadeAlerta
    semaforo: CorSemaforo


class AlertaNotaDisciplina(BaseModel):
    id_turma: str
    turma: str
    diagnostico: DiagnosticoNotasUfc
    severidade: SeveridadeAlerta
    semaforo: CorSemaforo
    motivo: str | None = None


def horizonte_informativo_h(dias_antecedencia: int) -> float:
    """Horizonte máximo (em horas) da faixa INFORMATIVO: 24 x max(dias_antecedencia, 14)."""
    return 24.0 * max(dias_antecedencia, 14)


def classificar_faixa_prazo(delta_h: float) -> tuple[SeveridadeAlerta, CorSemaforo]:
    """CRITICO até 48h, ATENCAO até 168h, INFORMATIVO além disso (delta_h já dentro do horizonte)."""
    if delta_h <= 48.0:
        return "CRITICO", "VERMELHO"
    if delta_h <= 168.0:
        return "ATENCAO", "AMARELO"
    return "INFORMATIVO", "VERDE"


def classificar_alerta_nota(diag: DiagnosticoNotasUfc) -> tuple[SeveridadeAlerta, CorSemaforo, str | None]:
    """
    Faixas de nota (Art. 114 do Regimento Geral):
    - CRITICO: REPROVADO_POR_NOTA; AGUARDANDO_AVALIACAO_FINAL com AF_min > 8,5; ou média
      necessária nas avaliações restantes (para MP 7,0) > 8,5.
    - ATENCAO: AGUARDANDO_AVALIACAO_FINAL com AF_min <= 8,5; ou média parcial atual entre
      4,0 e 6,9 com avaliações ainda pendentes.
    - OK: demais casos (sem alerta de nota).
    """
    sit = diag.situacao_regimental
    af_min = diag.nota_minima_avaliacao_final
    req_7 = diag.nota_necessaria_por_unidade_para_media_7
    if sit == "REPROVADO_POR_NOTA":
        return "CRITICO", "VERMELHO", "reprovado por nota (média < 4,0, sem direito a AF)"
    if sit == "AGUARDANDO_AVALIACAO_FINAL" and af_min is not None and af_min > 8.5:
        return "CRITICO", "VERMELHO", f"AF exige nota mínima {af_min:.1f} (> 8,5)"
    if sit == "EM_CURSO_EXIGE_AF" or (req_7 is not None and sit != "SEM_NOTAS_LANCADAS" and req_7 > 8.5):
        return "CRITICO", "VERMELHO", "média necessária nas avaliações restantes > 8,5"
    if sit == "AGUARDANDO_AVALIACAO_FINAL":
        return "ATENCAO", "AMARELO", "aguardando Avaliação Final"
    mp = diag.media_parcial_atual
    if mp is not None and 4.0 <= mp < 7.0 and sit in ("EM_CURSO_APROVAVEL_POR_MEDIA", "EM_CURSO_EXIGE_AF"):
        return "ATENCAO", "AMARELO", "média parcial entre 4,0 e 6,9 com avaliações pendentes"
    return "OK", "VERDE", None


def classificar_tarefa_prazo_envio(
    *,
    id_turma: str,
    turma: str,
    titulo: TextoExterno,
    fim_entrega_iso: str,
    enviada: bool | None,
    agora: datetime,
    dias_antecedencia: int = 7,
) -> AlertaTarefaItem | None:
    """
    Matriz Conjunta (enviada x delta_h) especificada na Parte 05, Ferramenta 28:
    - enviada is True -> CONCLUIDA (VERDE)
    - enviada is False -> CRITICO (-24h <= delta_h <= 48h), ATENCAO (48h < delta_h <= 168h),
      INFORMATIVO (168h < delta_h <= horizonte), com horizonte = 24 x max(dias_antecedencia, 14) h
      (assim a faixa INFORMATIVO nunca é vazia: prazo em 10 dias aparece com o padrão).
      Vencida há mais de 24h sem envio (delta_h < -24h) -> CRITICO, motivo
      "prazo vencido sem envio registrado".
    - enviada is None -> ATENCAO (<= 48h) ou INFORMATIVO (> 48h) com
      verificacao_envio="indisponivel_confirmar_no_ava" (sem acusar falsamente ausência de envio).
    """
    try:
        dt_prazo = datetime.fromisoformat(fim_entrega_iso[:19])
    except ValueError:
        return None

    delta_h = round((dt_prazo - agora).total_seconds() / 3600.0, 2)
    max_h = horizonte_informativo_h(dias_antecedencia)

    if delta_h > max_h:
        return None
    if delta_h < -24.0 and enviada is not False:
        return None

    if enviada is True:
        return AlertaTarefaItem(
            id_turma=id_turma,
            turma=turma,
            titulo=titulo,
            fim_entrega=fim_entrega_iso,
            horas_restantes=delta_h,
            enviada=True,
            severidade="CONCLUIDA",
            semaforo="VERDE",
            verificacao_envio="confirmada_no_ava",
        )

    if enviada is False:
        sev, cor = classificar_faixa_prazo(delta_h)
        motivo_f = "prazo vencido sem envio registrado" if delta_h < -24.0 else None
        return AlertaTarefaItem(
            id_turma=id_turma,
            turma=turma,
            titulo=titulo,
            fim_entrega=fim_entrega_iso,
            horas_restantes=delta_h,
            enviada=False,
            severidade=sev,
            semaforo=cor,
            verificacao_envio="confirmada_no_ava",
            motivo=motivo_f,
        )

    # enviada is None
    if 0.0 <= delta_h <= 48.0:
        sev_none: SeveridadeAlerta = "ATENCAO"
        cor_none: CorSemaforo = "AMARELO"
    else:
        sev_none = "INFORMATIVO"
        cor_none = "VERDE"

    return AlertaTarefaItem(
        id_turma=id_turma,
        turma=turma,
        titulo=titulo,
        fim_entrega=fim_entrega_iso,
        horas_restantes=delta_h,
        enviada=None,
        severidade=sev_none,
        semaforo=cor_none,
        verificacao_envio="indisponivel_confirmar_no_ava",
    )


async def gerar_radar_alertas(
    sigaa: ClienteSigaa,
    *,
    dias_antecedencia: int = 7,
    agora: datetime | None = None,
    atualizar: bool = False,
) -> dict[str, object]:
    ref_agora = agora or datetime.now()
    portal, _, _ = await sigaa.obter_resumo_portal(atualizar=atualizar)

    alertas_faltas: list[DiagnosticoFaltasDisciplina] = []
    alertas_tarefas: list[AlertaTarefaItem] = []
    tarefas_concluidas: list[AlertaTarefaItem] = []
    alertas_avaliacoes: list[AlertaAvaliacaoItem] = []
    alertas_notas: list[AlertaNotaDisciplina] = []

    for turma in portal.turmas:
        faltas_h = 0
        notas_lancadas: list[float] = []
        mp_inf: float | None = None

        try:
            notas_t, _, _ = await sigaa.obter_turma_notas(turma.id_turma, atualizar=atualizar)
            if notas_t.faltas is not None:
                faltas_h = notas_t.faltas
            notas_lancadas = [av.nota for av in notas_t.avaliacoes if av.nota is not None]
            mp_inf = notas_t.media_parcial
            total_unid = max(3, len(notas_t.avaliacoes)) if notas_t.avaliacoes else 3
            diag_n = diagnosticar_notas_ufc(
                notas_lancadas,
                total_unidades_previstas=total_unid,
                media_parcial_informada=mp_inf,
            )
            sev_n, cor_n, motivo_n = classificar_alerta_nota(diag_n)

            alertas_notas.append(
                AlertaNotaDisciplina(
                    id_turma=turma.id_turma,
                    turma=f"{turma.codigo} - {turma.nome}",
                    diagnostico=diag_n,
                    severidade=sev_n,
                    semaforo=cor_n,
                    motivo=motivo_n,
                )
            )
        except ErroUfc:
            pass

        try:
            freq_t, _, _ = await sigaa.obter_turma_frequencia(turma.id_turma, atualizar=atualizar)
            faltas_h = max(faltas_h, freq_t.total_faltas_horas)
        except ErroUfc:
            pass

        diag_f = calcular_faltas_disciplina(
            id_turma=turma.id_turma,
            codigo=turma.codigo,
            nome=turma.nome,
            carga_horaria_h=turma.carga_horaria_h,
            faltas_registradas_h=faltas_h,
        )
        alertas_faltas.append(diag_f)

        try:
            tar_t, _, _ = await sigaa.obter_turma_tarefas(turma.id_turma, atualizar=atualizar)
            for item_tar in tar_t.tarefas:
                if not item_tar.fim_entrega:
                    continue
                al_t = classificar_tarefa_prazo_envio(
                    id_turma=turma.id_turma,
                    turma=f"{turma.codigo} - {turma.nome}",
                    titulo=item_tar.titulo,
                    fim_entrega_iso=item_tar.fim_entrega,
                    enviada=item_tar.enviada,
                    agora=ref_agora,
                    dias_antecedencia=dias_antecedencia,
                )
                if al_t is not None:
                    if al_t.severidade == "CONCLUIDA":
                        tarefas_concluidas.append(al_t)
                    else:
                        alertas_tarefas.append(al_t)
        except ErroUfc:
            pass

        try:
            aval_t, _, _ = await sigaa.obter_turma_avaliacoes(turma.id_turma, atualizar=atualizar)
            for av in aval_t.avaliacoes:
                hora_str = av.hora or "08:00"
                try:
                    dt_av = datetime.fromisoformat(f"{av.data[:10]}T{hora_str[:5]}:00")
                except ValueError:
                    continue
                delta_h_av = round((dt_av - ref_agora).total_seconds() / 3600.0, 2)
                if 0.0 <= delta_h_av <= horizonte_informativo_h(dias_antecedencia):
                    sev_av, cor_av = classificar_faixa_prazo(delta_h_av)
                    alertas_avaliacoes.append(
                        AlertaAvaliacaoItem(
                            id_turma=turma.id_turma,
                            turma=f"{turma.codigo} - {turma.nome}",
                            data=av.data,
                            hora=av.hora,
                            descricao=av.descricao,
                            horas_restantes=delta_h_av,
                            severidade=sev_av,
                            semaforo=cor_av,
                        )
                    )
        except ErroUfc:
            pass

    situacao_bib: list[dict[str, str]] = []
    try:
        bib, _, _ = await sigaa.obter_situacao_biblioteca(atualizar=atualizar)
        for sec in bib.secoes:
            situacao_bib.extend(sec.itens)
    except ErroUfc:
        pass

    resumo_criticos = (
        sum(1 for f in alertas_faltas if f.severidade == "CRITICO")
        + sum(1 for t in alertas_tarefas if t.severidade == "CRITICO")
        + sum(1 for a in alertas_avaliacoes if a.severidade == "CRITICO")
        + sum(1 for n in alertas_notas if n.severidade == "CRITICO")
    )

    return {
        "referencia_temporal": ref_agora.isoformat(),
        "dias_antecedencia": dias_antecedencia,
        "total_alertas_criticos": resumo_criticos,
        "faltas_art_113": [f.model_dump() for f in alertas_faltas],
        "notas_art_114": [n.model_dump() for n in alertas_notas],
        "tarefas_pendentes": [t.model_dump() for t in alertas_tarefas],
        "tarefas_concluidas": [t.model_dump() for t in tarefas_concluidas],
        "avaliacoes_proximas": [a.model_dump() for a in alertas_avaliacoes],
        "biblioteca": situacao_bib,
    }
