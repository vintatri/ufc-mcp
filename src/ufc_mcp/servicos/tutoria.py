"""
Serviço `estudo` (Eixo III — IA e Inovação Pedagógica):
Cruza o desempenho atual do estudante segundo o Art. 114 do Regimento Geral da UFC,
o cronograma e a bibliografia do Plano de Curso, a data da próxima avaliação e os materiais/slides
postados pelo professor na Turma Virtual para estruturar um roteiro de estudo ativo (active recall)
com citação verificável de página.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from ufc_mcp.fontes.sigaa.cliente import ClienteSigaa
from ufc_mcp.nucleo.erros import ErroUfc
from ufc_mcp.nucleo.higiene import TextoExterno, sem_acentos_minusculo
from ufc_mcp.nucleo.modelos_base import BaseModel, Field
from ufc_mcp.servicos.notas_ufc import DiagnosticoNotasUfc, diagnosticar_notas_ufc

FocoEstudo = Literal["proxima_prova", "revisao_geral", "recuperacao_nota", "topico_especifico"]
FUSO_FORTALEZA = ZoneInfo("America/Fortaleza")


def _parse_data_avaliacao(valor: str) -> date | None:
    s = valor.strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    try:
        return datetime.strptime(s[:10], "%d/%m/%Y").date()
    except ValueError:
        return None


def _hoje_fortaleza(agora: Callable[[], datetime] | None) -> date:
    if agora is None:
        return datetime.now(FUSO_FORTALEZA).date()
    dt = agora()
    if dt.tzinfo is not None:
        return dt.astimezone(FUSO_FORTALEZA).date()
    return dt.date()


class TopicoAlinhadoEstudo(BaseModel):
    data_aula: str | None = None
    topico_cronograma: TextoExterno
    materiais_associados: list[dict[str, object]] = Field(default_factory=list)


class RoteiroPedagogicoAtivo(BaseModel):
    foco_selecionado: FocoEstudo
    objetivo_aprendizagem: str
    passos_execucao_agente: list[str]
    perguntas_orientadoras_recuperacao_ativa: list[str]
    formato_citacao_obrigatorio: str = "[Material: <titulo_material>, Página <N>]"


async def construir_plano_estudo_orientado(
    sigaa: ClienteSigaa,
    *,
    id_turma: str,
    foco: FocoEstudo = "proxima_prova",
    termo_topico: str | None = None,
    atualizar: bool = False,
    agora: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    avisos: list[str] = []
    nome_turma: str | None = None

    # 1. Diagnóstico regimental de notas (Art. 114 da UFC)
    diag_notas: DiagnosticoNotasUfc | None = None
    try:
        notas_t, _, _ = await sigaa.obter_turma_notas(id_turma, atualizar=atualizar)
        nome_turma = notas_t.turma
        valores_notas = [av.nota for av in notas_t.avaliacoes if av.nota is not None]
        # Total real = avaliações listadas; sem lista, o diagnóstico presume 3 e avisa.
        total_unidades = len(notas_t.avaliacoes) if notas_t.avaliacoes else None
        diag_notas = diagnosticar_notas_ufc(
            valores_notas,
            total_unidades_previstas=total_unidades,
            media_parcial_informada=notas_t.media_parcial,
        )
        avisos.extend(diag_notas.avisos)
    except ErroUfc as exc:
        avisos.append(f"Leitura das notas falhou ({exc.codigo}); diagnóstico de notas indisponível.")

    # 2. Horizonte de avaliação e tarefas
    proxima_avaliacao: dict[str, object] | None = None
    try:
        avals_t, _, _ = await sigaa.obter_turma_avaliacoes(id_turma, atualizar=atualizar)
        hoje = _hoje_fortaleza(agora)
        futuras: list[tuple[date, int, object]] = []
        for idx, av in enumerate(avals_t.avaliacoes):
            dt_av = _parse_data_avaliacao(av.data)
            if dt_av is not None and dt_av >= hoje:
                futuras.append((dt_av, idx, av))
        if futuras:
            _, _, escolhida = min(futuras, key=lambda item: (item[0], item[1]))
            proxima_avaliacao = {
                "data": escolhida.data,  # type: ignore[attr-defined]
                "hora": escolhida.hora,  # type: ignore[attr-defined]
                "descricao": escolhida.descricao.model_dump(),  # type: ignore[attr-defined]
            }
        else:
            avisos.append("Nenhuma avaliação futura encontrada para esta turma.")
    except ErroUfc as exc:
        avisos.append(f"Leitura das avaliações agendadas falhou ({exc.codigo}); próxima prova indisponível.")

    tarefas_pendentes: list[dict[str, object]] = []
    try:
        tar_t, _, _ = await sigaa.obter_turma_tarefas(id_turma, atualizar=atualizar)
        for t in tar_t.tarefas:
            if t.enviada is not True:
                tarefas_pendentes.append(
                    {
                        "titulo": t.titulo.model_dump(),
                        "fim_entrega": t.fim_entrega,
                        "enviada": t.enviada,
                    }
                )
    except ErroUfc as exc:
        avisos.append(f"Leitura das tarefas falhou ({exc.codigo}); tarefas pendentes indisponíveis.")

    # 3. Alinhamento Construtivo: Plano de Curso x Visão Geral (Materiais)
    plano_t, _, _ = await sigaa.obter_turma_plano_curso(id_turma, atualizar=atualizar)
    visao_t, _, _ = await sigaa.obter_turma_visao_geral(id_turma, atualizar=atualizar)

    todos_materiais: list[dict[str, object]] = []
    textos_busca: list[str] = []  # texto normalizado só para casar tópicos; não vai para a saída
    for top in visao_t.topicos:
        for mat in top.materiais:
            # títulos de terceiros permanecem como TextoExterno (nunca str solta)
            todos_materiais.append(
                {
                    "id_material": mat.id_material,
                    "titulo_material": mat.titulo.model_dump(),
                    "data_topico": top.data,
                    "titulo_topico": top.titulo.model_dump(),
                }
            )
            textos_busca.append(
                sem_acentos_minusculo(f"{mat.titulo.texto_externo} {top.titulo.texto_externo}")
            )

    termo_norm = sem_acentos_minusculo(termo_topico) if termo_topico else None
    topicos_alinhados: list[TopicoAlinhadoEstudo] = []

    for item_cron in plano_t.cronograma_aulas:
        txt_cron = item_cron.topico.texto_externo
        if (
            foco == "topico_especifico"
            and termo_norm
            and termo_norm not in sem_acentos_minusculo(txt_cron)
        ):
            continue

        palavras_cron = {
            p
            for p in sem_acentos_minusculo(txt_cron).split()
            if len(p) >= 4 and p not in {"aula", "introducao", "parte", "capitulo"}
        }
        associados: list[dict[str, object]] = []
        for m_info, txt_mat_norm in zip(todos_materiais, textos_busca, strict=True):
            mesma_data = item_cron.data is not None and m_info["data_topico"] == item_cron.data
            tem_palavra = any(pal in txt_mat_norm for pal in palavras_cron)
            if mesma_data or tem_palavra:
                associados.append(m_info)

        topicos_alinhados.append(
            TopicoAlinhadoEstudo(
                data_aula=item_cron.data,
                topico_cronograma=item_cron.topico,
                materiais_associados=associados,
            )
        )

    if foco == "topico_especifico" and termo_norm and not topicos_alinhados:
        avisos.append(
            f"O tópico pedido ('{termo_topico}') não foi encontrado no cronograma do Plano de Curso."
        )

    turma_final = nome_turma or plano_t.turma or visao_t.turma
    mat_recomendado: object | None = (
        topicos_alinhados[0].materiais_associados[0]["id_material"]
        if (topicos_alinhados and topicos_alinhados[0].materiais_associados)
        else None
    )
    if diag_notas is not None and diag_notas.nota_necessaria_por_unidade_para_media_7 is not None:
        meta_str = (
            f"atingir nota >= {diag_notas.nota_necessaria_por_unidade_para_media_7:.2f} "
            "na próxima avaliação parcial (média 7,0)"
        )
    elif diag_notas is not None and diag_notas.nota_minima_avaliacao_final is not None:
        meta_str = (
            f"atingir nota >= {diag_notas.nota_minima_avaliacao_final:.2f} "
            "na Avaliação Final (Art. 114 UFC)"
        )
    else:
        meta_str = "consolidar domínio dos tópicos previstos no Plano de Curso"

    if mat_recomendado is not None:
        passo_1 = (
            f"Passo 1: Chamar `baixar(id_turma='{id_turma}', id_material='{mat_recomendado}', "
            "extrair_texto=True, pagina_inicial=1, pagina_final=10)` para ler os slides/exercícios reais do professor."
        )
    else:
        passo_1 = (
            "Passo 1: Informar ao estudante que a turma não tem material associado ao tema "
            "e pedir outro material para continuar o estudo."
        )

    roteiro = RoteiroPedagogicoAtivo(
        foco_selecionado=foco,
        objetivo_aprendizagem=(
            f"Estudo dirigido na disciplina {turma_final} para {meta_str}, "
            "ancorado nos slides/listas do docente e nas referências do Plano de Curso."
        ),
        passos_execucao_agente=[
            passo_1,
            "Passo 2: Explicar a estrutura conceitual seguindo a sequência e a notação adotada pelo docente no cronograma do Plano de Curso.",
            "Passo 3: Formular de 3 a 5 questões graduadas de recuperação ativa (active recall) e exercícios práticos extraídos do material lido.",
            "Passo 4: Avaliar e corrigir as respostas do estudante apontando a fundamentação exata com `[Material: <titulo_material>, Página <N>]` e a bibliografia oficial.",
        ],
        perguntas_orientadoras_recuperacao_ativa=[
            "Quais são as hipóteses simplificadoras e equações governantes apresentadas pelo professor nos slides deste tópico?",
            "Como os conceitos deste tópico se conectam com os exercícios da lista pendente e com os critérios de avaliação da próxima prova?",
            "Em qual etapa de resolução ocorre a maior chance de erro conceitual ou de unidades segundo o material da aula?",
        ],
    )

    return {
        "id_turma": id_turma,
        "turma": turma_final,
        "diagnostico_notas_ufc": diag_notas.model_dump() if diag_notas is not None else None,
        "proxima_avaliacao": proxima_avaliacao,
        "tarefas_pendentes": tarefas_pendentes,
        "metodologia_docente": plano_t.metodologia.model_dump(),
        "procedimentos_avaliacao_docente": plano_t.procedimentos_avaliacao.model_dump(),
        "referencias_bibliograficas": [r.model_dump() for r in plano_t.referencias],
        "materiais_disponiveis_para_download": todos_materiais,
        "alinhamento_cronograma_materiais": [t.model_dump() for t in topicos_alinhados],
        "roteiro_pedagogico": roteiro.model_dump(),
        "avisos": avisos,
    }
