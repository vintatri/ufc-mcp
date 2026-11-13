"""Modelos de domínio das telas autenticadas do SIGAA e da Turma Virtual (AVA)."""

from __future__ import annotations

from typing import Literal

from ufc_mcp.nucleo.higiene import TextoExterno
from ufc_mcp.nucleo.modelos_base import BaseModel, Field
from ufc_mcp.servicos.horario import Horario

TIPOS_LISTAGEM_PERMITIDOS = (
    "enfases",
    "plano_estudo",
    "enade",
    "bloqueios",
    "movimentacoes",
    "mobilidades",
    "solicitacoes_mobilidade",
    "matricula_solicitacoes",
    "trancamentos",
    "supressoes",
    "extensao_minhas_acoes",
    "auxilios_anuncios",
    "auxilios_meus_processos",
    "bolsas_indicacoes",
    "estagios_termos",
)

TipoListagemSigaa = Literal[
    "enfases",
    "plano_estudo",
    "enade",
    "bloqueios",
    "movimentacoes",
    "mobilidades",
    "solicitacoes_mobilidade",
    "matricula_solicitacoes",
    "trancamentos",
    "supressoes",
    "extensao_minhas_acoes",
    "auxilios_anuncios",
    "auxilios_meus_processos",
    "bolsas_indicacoes",
    "estagios_termos",
]


class TurmaPortal(BaseModel):
    id_turma: str
    codigo: str
    nome: str
    local: str
    horario_bruto: str
    horarios: list[Horario] = Field(default_factory=list)
    inicio_vigencia: str | None = None
    fim_vigencia: str | None = None
    carga_horaria_h: int = 64


class AtividadePortal(BaseModel):
    data: str | None = None
    turma: str
    descricao: TextoExterno


class ResumoPortalDiscente(BaseModel):
    nome: str | None = None
    matricula: str | None = None
    curso: str
    nivel: str = "GRADUAÇÃO"
    status: str = "ATIVO"
    entrada: str | None = None
    integralizacao: str | None = None
    turmas: list[TurmaPortal] = Field(default_factory=list)
    noticias_portal: list[TextoExterno] = Field(default_factory=list)
    atividades_proximas: list[AtividadePortal] = Field(default_factory=list)


class ComponenteProgresso(BaseModel):
    id_componente: str
    codigo: str
    nome: str
    periodo_sugerido: int
    carga_horaria_h: int
    obrigatoria: bool = True
    situacao: Literal["cursado", "cursando", "a_cursar"] = "a_cursar"
    pre_requisitos: list[str] = Field(default_factory=list)
    co_requisitos: list[str] = Field(default_factory=list)


class ResultadoProgressoCurso(BaseModel):
    curso: str
    componentes: list[ComponenteProgresso] = Field(default_factory=list)


class RegistroIraSemestre(BaseModel):
    periodo: str
    ira_individual: float
    ira_geral: float
    media_curso: float | None = None
    desvio_padrao_curso: float | None = None


class ResultadoHistoricoIra(BaseModel):
    registros: list[RegistroIraSemestre] = Field(default_factory=list)


class SecaoPendencias(BaseModel):
    titulo: str
    itens: list[dict[str, str]] = Field(default_factory=list)


class ResultadoPendencias(BaseModel):
    titulo_tela: str
    secoes: list[SecaoPendencias] = Field(default_factory=list)


class TabelaListagemGenerica(BaseModel):
    titulo: str
    cabecalhos: list[str] = Field(default_factory=list)
    linhas: list[list[str]] = Field(default_factory=list)
    truncada: bool = False


class ResultadoListagemGenerica(BaseModel):
    tipo: str
    vazio: bool = False
    mensagem: str | None = None
    tabelas: list[TabelaListagemGenerica] = Field(default_factory=list)


class TurmaOfertada(BaseModel):
    codigo_componente: str
    nome_componente: str
    codigo_turma: str
    docente: str = "DOCENTE EXEMPLO"
    horario_bruto: str
    horarios: list[Horario] = Field(default_factory=list)
    local: str = "CT - Bloco 710"
    capacidade_vagas: int = 40
    carga_horaria_h: int = 64


class MaterialAula(BaseModel):
    id_material: str
    titulo: TextoExterno


class TopicoAulaTurma(BaseModel):
    data: str | None = None
    titulo: TextoExterno
    resumo: TextoExterno | None = None
    materiais: list[MaterialAula] = Field(default_factory=list)


class VisaoGeralTurma(BaseModel):
    id_turma: str
    turma: str
    topicos: list[TopicoAulaTurma] = Field(default_factory=list)


class AvaliacaoNota(BaseModel):
    nome: str
    nota: float | None = None


class NotasTurma(BaseModel):
    id_turma: str
    turma: str
    avaliacoes: list[AvaliacaoNota] = Field(default_factory=list)
    media_parcial: float | None = None
    faltas: int | None = None
    situacao: str | None = None


class RegistroFrequenciaDia(BaseModel):
    data: str
    situacao: str
    faltas_no_dia: int = 0


class FrequenciaTurma(BaseModel):
    id_turma: str
    turma: str
    total_faltas_horas: int = 0
    registros: list[RegistroFrequenciaDia] = Field(default_factory=list)


class ItemAvaliacaoAgendada(BaseModel):
    data: str
    hora: str | None = None
    descricao: TextoExterno


class AvaliacoesTurma(BaseModel):
    id_turma: str
    turma: str
    avaliacoes: list[ItemAvaliacaoAgendada] = Field(default_factory=list)


class ItemTarefaTurma(BaseModel):
    titulo: TextoExterno
    descricao: TextoExterno
    inicio_entrega: str | None = None
    fim_entrega: str | None = None
    enviada: bool | None = None


class TarefasTurma(BaseModel):
    id_turma: str
    turma: str
    tarefas: list[ItemTarefaTurma] = Field(default_factory=list)


class ItemNoticiaTurma(BaseModel):
    titulo: TextoExterno
    corpo: TextoExterno
    publicada_em: str | None = None


class NoticiasTurma(BaseModel):
    id_turma: str
    turma: str
    noticias: list[ItemNoticiaTurma] = Field(default_factory=list)


class ItemCronogramaPlano(BaseModel):
    data: str | None = None
    topico: TextoExterno


class PlanoCursoTurma(BaseModel):
    id_turma: str
    turma: str
    metodologia: TextoExterno
    procedimentos_avaliacao: TextoExterno
    cronograma_aulas: list[ItemCronogramaPlano] = Field(default_factory=list)
    referencias: list[TextoExterno] = Field(default_factory=list)
