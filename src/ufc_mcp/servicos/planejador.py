"""
Serviços `matricula` e `grade`:
1. Constrói e valida formalmente o Grafo Acíclico Direcionado (DAG) curricular;
2. Calcula o fecho transitivo `|descendentes_transitivos(c)|` de desbloqueio;
3. Impõe satisfação estrita de pré-requisitos e co-requisitos (`co_requisitos`);
4. Resolve o Problema de Satisfação de Restrições (Branch-and-Bound) sem choque de horário
   sob 3 perfis explícitos de decisão: `desbloqueio`, `compacta` e `equilibrada`.
"""

from __future__ import annotations

from collections import deque
from typing import Literal, get_args

from ufc_mcp.fontes.sigaa.modelos import ComponenteProgresso, TurmaOfertada
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.modelos_base import BaseModel, Field
from ufc_mcp.servicos.horario import (
    Horario,
    _para_minutos,
    calcular_horas_janela,
    horarios_conflitam,
    turno_predominante,
)

PerfilOtimizacaoGrade = Literal["desbloqueio", "compacta", "equilibrada"]
EstrategiaSimulacao = Literal["diversificada", "desbloqueio", "compacta", "equilibrada"]


class ValidacaoGrafoCurricular(BaseModel):
    eh_dag: bool
    total_vertices: int
    total_arestas_pre: int
    total_arestas_co: int
    ordem_topologica: list[str] = Field(default_factory=list)
    descendentes_transitivos_por_codigo: dict[str, list[str]] = Field(default_factory=dict)


class MetricasGradeSugerida(BaseModel):
    perfil: PerfilOtimizacaoGrade
    escore_total: float
    total_disciplinas: int
    carga_horaria_total_h: int
    obrigatorias_incluidas: int
    total_disciplinas_destravadas_no_curso: int
    horas_janela_semanal: float
    dias_com_aula: int
    horas_acima_de_4h_por_dia: float


class GradeSugerida(BaseModel):
    perfil: PerfilOtimizacaoGrade
    justificativa_perfil: str
    turmas: list[TurmaOfertada]
    codigos_selecionados: list[str]
    metricas: MetricasGradeSugerida


def validar_dag_e_fecho_transitivo(
    componentes: list[ComponenteProgresso],
) -> ValidacaoGrafoCurricular:
    """
    Valida que o grafo de pré-requisitos G_curr = (V, E) é um DAG livre de ciclos
    (algoritmo de Kahn) e calcula o fecho transitivo de desbloqueio para cada disciplina.
    """
    vertices = {c.codigo: c for c in componentes}
    adj_dependentes: dict[str, set[str]] = {cod: set() for cod in vertices}
    grau_entrada: dict[str, int] = {cod: 0 for cod in vertices}
    total_pre = 0
    total_co = 0

    for comp in componentes:
        for pre in comp.pre_requisitos:
            if pre in vertices and comp.codigo not in adj_dependentes[pre]:
                adj_dependentes[pre].add(comp.codigo)
                grau_entrada[comp.codigo] += 1
                total_pre += 1
        for co in comp.co_requisitos:
            if co in vertices:
                total_co += 1

    fila: deque[str] = deque(sorted(cod for cod, g in grau_entrada.items() if g == 0))
    ordem_topo: list[str] = []

    while fila:
        u = fila.popleft()
        ordem_topo.append(u)
        for v in sorted(adj_dependentes[u]):
            grau_entrada[v] -= 1
            if grau_entrada[v] == 0:
                fila.append(v)

    if len(ordem_topo) != len(vertices):
        ciclo = sorted(set(vertices.keys()) - set(ordem_topo))
        raise ErroUfc(
            CodigoErro.PARAMETRO_INVALIDO,
            f"Ciclo detectado no grafo curricular de pré-requisitos: {ciclo}",
            detalhes={"vertices_em_ciclo": ciclo},
        )

    # Cálculo do fecho transitivo em ordem topológica reversa
    fecho: dict[str, set[str]] = {cod: set() for cod in vertices}
    for u in reversed(ordem_topo):
        for v in adj_dependentes[u]:
            fecho[u].add(v)
            fecho[u].update(fecho[v])

    return ValidacaoGrafoCurricular(
        eh_dag=True,
        total_vertices=len(vertices),
        total_arestas_pre=total_pre,
        total_arestas_co=total_co,
        ordem_topologica=ordem_topo,
        descendentes_transitivos_por_codigo={
            cod: sorted(desc) for cod, desc in fecho.items()
        },
    )


def analisar_elegibilidade_curricular(
    componentes: list[ComponenteProgresso],
) -> dict[str, object]:
    """Implementa a análise determinística de `matricula` (Ferramenta 34)."""
    grafo = validar_dag_e_fecho_transitivo(componentes)
    cursados = {c.codigo for c in componentes if c.situacao == "cursado"}
    cursando = {c.codigo for c in componentes if c.situacao == "cursando"}
    cumpridos_ou_em_curso = cursados | cursando

    elegiveis: list[dict[str, object]] = []
    bloqueados: list[dict[str, object]] = []

    for c in componentes:
        if c.situacao != "a_cursar":
            continue
        faltam = [p for p in c.pre_requisitos if p not in cumpridos_ou_em_curso]
        dependem_em_curso = [p for p in c.pre_requisitos if p in cursando]
        destrava = grafo.descendentes_transitivos_por_codigo.get(c.codigo, [])

        if not faltam:
            elegiveis.append(
                {
                    "codigo": c.codigo,
                    "nome": c.nome,
                    "periodo_sugerido": c.periodo_sugerido,
                    "obrigatoria": c.obrigatoria,
                    "carga_horaria_h": c.carga_horaria_h,
                    "co_requisitos": c.co_requisitos,
                    "depende_de_aprovacao_atual": dependem_em_curso,
                    "total_destrava_no_curso": len(destrava),
                    "disciplinas_destravadas": destrava,
                }
            )
        else:
            bloqueados.append(
                {
                    "codigo": c.codigo,
                    "nome": c.nome,
                    "periodo_sugerido": c.periodo_sugerido,
                    "obrigatoria": c.obrigatoria,
                    "faltam_cumprir": faltam,
                    "total_destrava_no_curso": len(destrava),
                }
            )

    return {
        "validacao_grafo": grafo.model_dump(),
        "elegiveis": elegiveis,
        "bloqueados": bloqueados,
        "indeterminados": [],
    }


def _horas_acima_de_4h_por_dia(horarios: list[Horario]) -> float:
    por_dia: dict[str, int] = {}
    for h in horarios:
        dur_min = max(0, _para_minutos(h.fim) - _para_minutos(h.inicio))
        por_dia[h.dia] = por_dia.get(h.dia, 0) + dur_min
    excesso_min = sum(max(0, mins - 240) for mins in por_dia.values())
    return round(excesso_min / 60.0, 2)


def _avaliar_grade_perfil(
    turmas_grade: list[TurmaOfertada],
    *,
    perfil: PerfilOtimizacaoGrade,
    mapa_comp: dict[str, ComponenteProgresso],
    fecho: dict[str, list[str]],
    turno_preferido: str,
    codigos_desejados_set: set[str],
) -> MetricasGradeSugerida:
    todos_horarios = [h for t in turmas_grade for h in t.horarios]
    horas_janela = calcular_horas_janela(todos_horarios)
    dias_com_aula = len({h.dia for h in todos_horarios})
    horas_excesso_4h = _horas_acima_de_4h_por_dia(todos_horarios)

    soma_termos = 0.0
    obrig_count = 0
    destravadas_unicas: set[str] = set()
    gargalos_count = 0

    for t in turmas_grade:
        comp = mapa_comp.get(t.codigo_componente)
        # Turma fora do currículo do estudante (optativa/outro curso) não conta como obrigatória.
        eh_obrig = comp.obrigatoria if comp is not None else False
        periodo = comp.periodo_sugerido if comp is not None else 1
        desc = fecho.get(t.codigo_componente, [])
        n_desc = len(desc)
        destravadas_unicas.update(desc)
        if eh_obrig:
            obrig_count += 1
        if n_desc >= 2:
            gargalos_count += 1

        bonus_desejado = 150.0 if t.codigo_componente in codigos_desejados_set else 0.0

        if perfil == "desbloqueio":
            soma_termos += (
                bonus_desejado
                + (100.0 if eh_obrig else 0.0)
                + 25.0 * n_desc
                + (15.0 / max(1, periodo))
            )
        elif perfil == "compacta":
            t_pred = turno_predominante(t.horarios)
            match_turno = (
                1.0
                if (turno_preferido != "qualquer" and t_pred == turno_preferido)
                or (turno_preferido == "qualquer" and t_pred == "manha")
                else 0.0
            )
            soma_termos += bonus_desejado + (60.0 if eh_obrig else 0.0) + 30.0 * match_turno
        else:  # equilibrada
            soma_termos += bonus_desejado + (80.0 if eh_obrig else 0.0) + 15.0 * n_desc

    if perfil == "desbloqueio":
        escore = soma_termos - 3.0 * horas_janela
    elif perfil == "compacta":
        escore = soma_termos - 25.0 * horas_janela - 15.0 * dias_com_aula
    else:  # equilibrada
        penalidade_gargalo = max(0, gargalos_count - 2) * 25.0
        escore = (
            soma_termos
            - 30.0 * horas_excesso_4h
            - 10.0 * horas_janela
            - penalidade_gargalo
        )

    return MetricasGradeSugerida(
        perfil=perfil,
        escore_total=round(escore, 2),
        total_disciplinas=len(turmas_grade),
        carga_horaria_total_h=sum(t.carga_horaria_h for t in turmas_grade),
        obrigatorias_incluidas=obrig_count,
        total_disciplinas_destravadas_no_curso=len(destravadas_unicas),
        horas_janela_semanal=horas_janela,
        dias_com_aula=dias_com_aula,
        horas_acima_de_4h_por_dia=horas_excesso_4h,
    )


DESCRICOES_PERFIS: dict[PerfilOtimizacaoGrade, str] = {
    "desbloqueio": (
        "Prioriza disciplinas obrigatórias e gargalos curriculares com maior fecho transitivo "
        "|descendentes_transitivos(c)| para acelerar a integralização do curso."
    ),
    "compacta": (
        "Prioriza concentração no turno preferido, zero janelas ociosas entre aulas (-25/h) "
        "e menor número de dias de deslocamento ao campus (-15/dia)."
    ),
    "equilibrada": (
        "Equilibra avanço curricular e carga cognitiva diária, penalizando dias com mais de 4h "
        "de aula e evitando excesso simultâneo de disciplinas gargalo."
    ),
}


def simular_grades_otimizadas(
    componentes: list[ComponenteProgresso],
    ofertas: list[TurmaOfertada],
    *,
    max_disciplinas: int = 5,
    estrategia: EstrategiaSimulacao = "diversificada",
    turno_preferido: Literal["manha", "tarde", "noite", "qualquer"] = "qualquer",
    codigos_desejados: list[str] | None = None,
    codigos_ignorar: list[str] | None = None,
) -> dict[str, object]:
    """
    Resolve o CSP de matrícula via Branch-and-Bound garantindo:
    1. Pré-requisitos cumpridos (em cursados U cursando);
    2. Co-requisitos cumpridos (em cursados U cursando OU presentes na própria grade G);
    3. Zero choque de horário entre quaisquer duas turmas da grade;
    4. Avaliação exata sob os 3 perfis (`desbloqueio`, `compacta`, `equilibrada`).
    """
    estrategias_validas = get_args(EstrategiaSimulacao)
    if estrategia not in estrategias_validas:
        raise ErroUfc(
            CodigoErro.PARAMETRO_INVALIDO,
            f"Estratégia inválida: {estrategia!r}. "
            f"Valores aceitos: {', '.join(estrategias_validas)}.",
            detalhes={"estrategia": estrategia, "validas": list(estrategias_validas)},
        )
    max_disc = max(1, min(max_disciplinas, 8))
    avisos: list[str] = []
    codigos_curriculo = {c.codigo for c in componentes}
    for c in componentes:
        for tipo, lista in (("pré-requisito", c.pre_requisitos), ("co-requisito", c.co_requisitos)):
            for ref in lista:
                if ref not in codigos_curriculo:
                    avisos.append(
                        f"{tipo} {ref} de {c.codigo} não existe no currículo (ignorado na validação)."
                    )
    grafo = validar_dag_e_fecho_transitivo(componentes)
    mapa_comp = {c.codigo: c for c in componentes}
    cursados = {c.codigo for c in componentes if c.situacao == "cursado"}
    cursando = {c.codigo for c in componentes if c.situacao == "cursando"}
    cumpridos = cursados | cursando

    ignorar_set = {c.strip().upper() for c in (codigos_ignorar or []) if c.strip()}
    desejados_set = {c.strip().upper() for c in (codigos_desejados or []) if c.strip()}

    # Filtrar turmas elegíveis em pré-requisitos
    turmas_candidatas: list[TurmaOfertada] = []
    for of in ofertas:
        cod = of.codigo_componente.upper()
        if cod in ignorar_set or cod in cumpridos:
            continue
        comp = mapa_comp.get(cod)
        if comp is not None:
            faltam_pre = [p for p in comp.pre_requisitos if p not in cumpridos]
            if faltam_pre:
                continue
        turmas_candidatas.append(of)

    # Registrar choques evitados entre turmas candidatas para explicabilidade
    choques_evitados: list[dict[str, object]] = []
    for i in range(len(turmas_candidatas)):
        for j in range(i + 1, len(turmas_candidatas)):
            t1, t2 = turmas_candidatas[i], turmas_candidatas[j]
            if t1.codigo_componente == t2.codigo_componente:
                continue
            conflitos = horarios_conflitam(t1.horarios, t2.horarios)
            if conflitos:
                choques_evitados.append(
                    {
                        "turma_a": f"{t1.codigo_componente} (T{t1.codigo_turma})",
                        "turma_b": f"{t2.codigo_componente} (T{t2.codigo_turma})",
                        "conflitos": conflitos,
                    }
                )

    # Gerar todas as combinações viáveis via Branch-and-Bound
    combinacoes_validas: list[list[TurmaOfertada]] = []

    def _co_requisitos_satisfeitos(grade: list[TurmaOfertada]) -> bool:
        codigos_na_grade = {t.codigo_componente for t in grade}
        for t in grade:
            comp = mapa_comp.get(t.codigo_componente)
            if comp is None:
                continue
            for co in comp.co_requisitos:
                if co not in cumpridos and co not in codigos_na_grade:
                    return False
        return True

    def _backtrack(idx: int, atual: list[TurmaOfertada], codigos_usados: set[str]) -> None:
        if atual and _co_requisitos_satisfeitos(atual):
            combinacoes_validas.append(list(atual))
        if len(atual) >= max_disc or idx >= len(turmas_candidatas):
            return

        for k in range(idx, len(turmas_candidatas)):
            cand = turmas_candidatas[k]
            if cand.codigo_componente in codigos_usados:
                continue
            tem_choque = any(
                horarios_conflitam(cand.horarios, ja.horarios) for ja in atual
            )
            if tem_choque:
                continue
            atual.append(cand)
            codigos_usados.add(cand.codigo_componente)
            _backtrack(k + 1, atual, codigos_usados)
            codigos_usados.remove(cand.codigo_componente)
            atual.pop()

    _backtrack(0, [], set())

    # Preferir combinações maximais (ou que atinjam o maior número possível de disciplinas até max_disc)
    if combinacoes_validas:
        maior_tam = max(len(g) for g in combinacoes_validas)
        candidatas_topo = [g for g in combinacoes_validas if len(g) >= max(1, maior_tam - 1)]
    else:
        candidatas_topo = []

    perfis_alvo: list[PerfilOtimizacaoGrade] = (
        ["desbloqueio", "compacta", "equilibrada"]
        if estrategia == "diversificada"
        else [estrategia]
    )

    grades_sugeridas: list[GradeSugerida] = []
    assinaturas_vistas: set[tuple[str, ...]] = set()

    for perfil in perfis_alvo:
        avaliadas: list[tuple[MetricasGradeSugerida, list[TurmaOfertada]]] = []
        for comb in candidatas_topo:
            met = _avaliar_grade_perfil(
                comb,
                perfil=perfil,
                mapa_comp=mapa_comp,
                fecho=grafo.descendentes_transitivos_por_codigo,
                turno_preferido=turno_preferido,
                codigos_desejados_set=desejados_set,
            )
            avaliadas.append((met, comb))

        avaliadas.sort(
            key=lambda par: (
                par[0].escore_total,
                par[0].total_disciplinas,
                par[0].total_disciplinas_destravadas_no_curso,
            ),
            reverse=True,
        )

        for met_cand, comb_cand in avaliadas:
            assinatura = tuple(
                sorted(f"{t.codigo_componente}:{t.codigo_turma}" for t in comb_cand)
            )
            if estrategia == "diversificada" and assinatura in assinaturas_vistas and len(avaliadas) > 1:
                continue
            assinaturas_vistas.add(assinatura)
            grades_sugeridas.append(
                GradeSugerida(
                    perfil=perfil,
                    justificativa_perfil=DESCRICOES_PERFIS[perfil],
                    turmas=comb_cand,
                    codigos_selecionados=[t.codigo_componente for t in comb_cand],
                    metricas=met_cand,
                )
            )
            break

        # Se estratégia for única, podemos retornar até 3 melhores daquele perfil
        if estrategia != "diversificada":
            for met_extra, comb_extra in avaliadas[1:3]:
                grades_sugeridas.append(
                    GradeSugerida(
                        perfil=perfil,
                        justificativa_perfil=DESCRICOES_PERFIS[perfil],
                        turmas=comb_extra,
                        codigos_selecionados=[t.codigo_componente for t in comb_extra],
                        metricas=met_extra,
                    )
                )

    return {
        "estrategia_solicitada": estrategia,
        "turno_preferido": turno_preferido,
        "max_disciplinas": max_disc,
        "validacao_grafo": grafo.model_dump(),
        "total_combinacoes_sem_choque_avaliadas": len(combinacoes_validas),
        "choques_evitados": choques_evitados,
        "grades_sugeridas": [g.model_dump() for g in grades_sugeridas],
        "avisos": avisos,
    }
