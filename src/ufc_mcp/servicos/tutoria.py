"""
Serviço `estudo` (Eixo III — IA e Inovação Pedagógica):
Cruza o desempenho atual do estudante segundo o Art. 114 do Regimento Geral da UFC,
o cronograma e a bibliografia do Plano de Curso, a data da próxima avaliação e os materiais/slides
postados pelo professor na Turma Virtual para estruturar um roteiro de estudo ativo (active recall)
com citação verificável de página.
"""

from __future__ import annotations

from typing import Literal

from ufc_mcp.fontes.sigaa.cliente import ClienteSigaa
from ufc_mcp.nucleo.erros import ErroUfc
from ufc_mcp.nucleo.higiene import TextoExterno, sem_acentos_minusculo
from ufc_mcp.nucleo.modelos_base import BaseModel, Field
from ufc_mcp.servicos.notas_ufc import DiagnosticoNotasUfc, diagnosticar_notas_ufc

FocoEstudo = Literal["proxima_prova", "revisao_geral", "recuperacao_nota", "topico_especifico"]


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
) -> dict[str, object]:
    # 1. Diagnóstico regimental de notas (Art. 114 da UFC)
    notas_t, _, _ = await sigaa.obter_turma_notas(id_turma, atualizar=atualizar)
    valores_notas = [av.nota for av in notas_t.avaliacoes if av.nota is not None]
    total_unidades = max(3, len(notas_t.avaliacoes)) if notas_t.avaliacoes else 3
    diag_notas: DiagnosticoNotasUfc = diagnosticar_notas_ufc(
        valores_notas,
        total_unidades_previstas=total_unidades,
        media_parcial_informada=notas_t.media_parcial,
    )

    # 2. Horizonte de avaliação e tarefas
    proxima_avaliacao: dict[str, object] | None = None
    try:
        avals_t, _, _ = await sigaa.obter_turma_avaliacoes(id_turma, atualizar=atualizar)
        if avals_t.avaliacoes:
            av0 = avals_t.avaliacoes[0]
            proxima_avaliacao = {
                "data": av0.data,
                "hora": av0.hora,
                "descricao": av0.descricao.model_dump(),
            }
    except ErroUfc:
        pass

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
    except ErroUfc:
        pass

    # 3. Alinhamento Construtivo: Plano de Curso x Visão Geral (Materiais)
    plano_t, _, _ = await sigaa.obter_turma_plano_curso(id_turma, atualizar=atualizar)
    visao_t, _, _ = await sigaa.obter_turma_visao_geral(id_turma, atualizar=atualizar)

    todos_materiais: list[dict[str, object]] = []
    for top in visao_t.topicos:
        for mat in top.materiais:
            todos_materiais.append(
                {
                    "id_material": mat.id_material,
                    "titulo_material": mat.titulo.texto_externo,
                    "data_topico": top.data,
                    "titulo_topico": top.titulo.texto_externo,
                }
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
        for m_info in todos_materiais:
            mesma_data = item_cron.data is not None and m_info["data_topico"] == item_cron.data
            txt_mat_norm = sem_acentos_minusculo(
                f"{m_info['titulo_material']} {m_info['titulo_topico']}"
            )
            tem_palavra = any(pal in txt_mat_norm for pal in palavras_cron)
            if mesma_data or tem_palavra:
                associados.append(m_info)

        if not associados and todos_materiais:
            associados = [todos_materiais[0]]

        topicos_alinhados.append(
            TopicoAlinhadoEstudo(
                data_aula=item_cron.data,
                topico_cronograma=item_cron.topico,
                materiais_associados=associados,
            )
        )

    if not topicos_alinhados and plano_t.cronograma_aulas:
        for item_cron in plano_t.cronograma_aulas:
            topicos_alinhados.append(
                TopicoAlinhadoEstudo(
                    data_aula=item_cron.data,
                    topico_cronograma=item_cron.topico,
                    materiais_associados=todos_materiais[:2],
                )
            )

    mat_recomendado = (
        todos_materiais[0]["id_material"] if todos_materiais else "mat_01"
    )
    meta_str = (
        f"atingir nota >= {diag_notas.nota_necessaria_por_unidade_para_media_7:.2f} na próxima avaliação parcial (média 7,0)"
        if diag_notas.nota_necessaria_por_unidade_para_media_7 is not None
        else (
            f"atingir nota >= {diag_notas.nota_minima_avaliacao_final:.2f} na Avaliação Final (Art. 114 UFC)"
            if diag_notas.nota_minima_avaliacao_final is not None
            else "consolidar domínio dos tópicos previstos no Plano de Curso"
        )
    )

    roteiro = RoteiroPedagogicoAtivo(
        foco_selecionado=foco,
        objetivo_aprendizagem=(
            f"Estudo dirigido na disciplina {notas_t.turma} para {meta_str}, "
            "ancorado nos slides/listas do docente e nas referências do Plano de Curso."
        ),
        passos_execucao_agente=[
            f"Passo 1: Chamar `baixar(id_turma='{id_turma}', id_material='{mat_recomendado}', extrair_texto=True, pagina_inicial=1, pagina_final=10)` para ler os slides/exercícios reais do professor.",
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
        "turma": notas_t.turma,
        "diagnostico_notas_ufc": diag_notas.model_dump(),
        "proxima_avaliacao": proxima_avaliacao,
        "tarefas_pendentes": tarefas_pendentes,
        "metodologia_docente": plano_t.metodologia.model_dump(),
        "procedimentos_avaliacao_docente": plano_t.procedimentos_avaliacao.model_dump(),
        "referencias_bibliograficas": [r.model_dump() for r in plano_t.referencias],
        "materiais_disponiveis_para_download": todos_materiais,
        "alinhamento_cronograma_materiais": [t.model_dump() for t in topicos_alinhados],
        "roteiro_pedagogico": roteiro.model_dump(),
    }
