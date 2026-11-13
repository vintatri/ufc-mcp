"""
Barreira Determinística de Segurança (Nível 2 de Defesa contra Indirect Prompt Injection).
Contém as listas fechadas de 22 ações de menu e 12 postbacks permitidos (somente leitura)
e bloqueia estruturalmente qualquer operação de escrita, emissão ou acesso a dados de terceiros.
"""

from __future__ import annotations

from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.paginas import REGEX_VERBOS_PROIBIDOS

ACOES_MENU_PERMITIDAS: frozenset[str] = frozenset({
    # Consultas do Discente (Ensino)
    "registroDiscenteEnfaseMBean.iniciarBuscaRegistrosDiscente",
    "consultaProgressoDiscenteCurso.iniciarConsultaProgresso",
    "consultaPendencias.iniciarConsultaPendencias",
    "consultaSituacaoDiscenteBiblioteca.iniciarConsultaSituacao",
    "planoEstudoPortalDiscenteMBean.iniciarVizualizacaoMovimentacoesPortalDiscente",
    "participacaoDiscenteEnade.iniciarVizualizacaoParticipacoes",
    "consultaIRADiscente.iniciarConsultaHistoricoIRA",
    "marcacaoBloqueioDiscenteGraduacaoMBean.iniciarBuscaBloqueiosUsuarioDiscente",
    "movimentacaoAluno.iniciarVizualizacaoMovimentacoesPortalDiscente",
    # Matrícula, Oferta de Turmas, Trancamento e Supressão (Somente Leitura)
    "matriculaGraduacao.acompanharSolicitacoes",
    "agendaTurmaDiscenteMBean.visualizarAgendaTurmas",
    "buscaTurmaBean.popularBuscaGeral",
    "trancamentoMatricula.iniciarMeusTrancamentos",
    "supressaoMatricula.iniciarMinhasSupressoes",
    # Mobilidade Estudantil (Apenas listagem)
    "mobilidadeEstudantil.listarMobilidadesDiscente",
    "solicitacaoMobilidadeEstudantilPerfilDiscente.listarMinhasSolicitacoes",
    # Extensão (Apenas listagem de participações do próprio discente)
    "documentosAutenticadosExtensao.participacoesDiscenteUsuarioLogado",
    # Auxílios e Bolsas (Apenas visualização de anúncios, processos e indicações)
    "interessadoAuxilio.listarAnuncios",
    "interessadoAuxilio.acompanharInscricoes",
    "aceiteIndicacaoBolsa.iniciarListaIndicacoesDiscente",
    # Estágios e Agendamentos (Apenas consulta da lista)
    "termoEstagioMBean.iniciarConsulta",
    "agendamento.consultar",
})

POSTBACKS_PERMITIDOS: frozenset[tuple[str, str]] = frozenset({
    # Menu lateral da Turma Virtual (AVA)
    ("/sigaa/ava/index.jsf", "Principal"),
    ("/sigaa/ava/index.jsf", "Plano de Curso"),
    ("/sigaa/ava/index.jsf", "Visualizar Programa"),
    ("/sigaa/ava/index.jsf", "Notícias"),
    ("/sigaa/ava/index.jsf", "Frequência"),
    ("/sigaa/ava/index.jsf", "Ver Notas"),
    ("/sigaa/ava/index.jsf", "Conteúdo"),
    ("/sigaa/ava/index.jsf", "Referências"),
    ("/sigaa/ava/index.jsf", "Avaliações"),
    ("/sigaa/ava/index.jsf", "Tarefas"),
    # Download somente leitura de arquivo anexado em tópico de aula da Turma Virtual
    ("/sigaa/ava/index.jsf", "Baixar Material"),
    # Botão de consulta somente leitura na tela de Busca Geral de Turmas
    ("/sigaa/ensino/turma/busca_turma.jsf", "Buscar"),
})

ACOES_PROIBIDAS_CONHECIDAS: frozenset[str] = frozenset({
    # Risco 4 (Destrutivas)
    "trancamentoMatricula.popularSolicitacao",
    "supressaoMatricula.popularSolicitacao",
    "matriculaInstitucional.iniciarCancelamentoMatriculaInstitucionalDiscente",
    "rescisaoTermoEstagioMBean.buscaTermoCadastro",
    "recadastramentoEmailMBean.entrarFormulario",
    "/sigaa/alterar_dados.jsf",
    "Gerenciar Perfil",
    # Risco 3 (Escrita difícil de desfazer)
    "solicitacaoCreditacao.iniciarCadastroSolicitacaoCreditacaoExtensao",
    "solicitacaoCreditacao.iniciarCadastroSolicitacaoCreditacaoComplementar",
    "solicitacaoMobilidadeEstudantilPerfilDiscente.iniciarInscricaoEditalMobilidade",
    "solicitacaoMobilidadeEstudantilPerfilDiscente.iniciarSolicitacaoProrrogacaoMobilidade",
    "matriculaInstitucional.iniciarMatriculaInstitucionalDiscente",
    "termoEstagioMBean.iniciarCadastroEstagioObrigatorio",
    "termoEstagioMBean.iniciarCadastroEstagioNaoObrigatorio",
    "termoEstagioMBean.iniciarCadastroEstagioNaoObrigatorioUFC",
    "relatorioAtividadesMBean.buscaTermoCadastro",
    "solicitacaoDocumentoTraducao.iniciarCadastroSolicitacao",
    "atendimentoAluno.novaPergunta",
    "Dar Aceite na Indicação",
    "Enviar Tarefa",
    "Postar Mensagem",
    "Votar",
    # Risco 2 (Escrita reversível / Sessão)
    "agendamento.agendar",
    "buscarComunidadeVirtualMBean.criar",
    "/sigaa/logar.do?dispatch=logOff",
    # Risco 1 Excluído por Efeito Colateral no Banco (D8) ou Privacidade/LGPD (D7)
    "portalDiscente.atestadoMatricula",
    "portalDiscente.historico",
    "declaracaoVinculo.iniciarEmissaoDeclaracao",
    "emissaoDocumentoTraduzidoDiscente.iniciarEmissaoHistoricoDiscente",
    "emissaoDocumentoTraduzidoDiscente.iniciarEmissaoDeclaracaoVinculoDiscente",
    "consultarDocumentosBasicosMBean.iniciar",
    "resultadoExameCovidSigaaMBean.entrarVisualizacaoDiscenteResultado",
    "consultaParticipacaoAtividadeExtensaoMBean.iniciarConsultaMembros",
    "Participantes",
})


def exigir_acao_menu(acao: str) -> None:
    """Verifica se a expressão JSF do menu do Portal do Discente é permitida."""
    acao_limpa = acao.strip()
    if acao_limpa in ACOES_PROIBIDAS_CONHECIDAS or acao_limpa not in ACOES_MENU_PERMITIDAS:
        raise ErroUfc(
            CodigoErro.ACAO_BLOQUEADA,
            f"Ação de menu bloqueada pela política somente leitura: '{acao_limpa}'.",
            detalhes={"acao": acao_limpa},
        )


def exigir_postback(view: str, rotulo: str) -> None:
    """Verifica se o par (view, rotulo) está na allowlist e não contém verbos de mutação."""
    view_limpa = view.split(";")[0].split("?")[0].strip()
    rotulo_limpo = rotulo.strip()

    if rotulo_limpo in ACOES_PROIBIDAS_CONHECIDAS or REGEX_VERBOS_PROIBIDOS.search(rotulo_limpo):
        raise ErroUfc(
            CodigoErro.ACAO_BLOQUEADA,
            f"Postback bloqueado por conter verbo de mutação ou ação proibida: '{rotulo_limpo}'.",
            detalhes={"view": view_limpa, "rotulo": rotulo_limpo},
        )

    if (view_limpa, rotulo_limpo) not in POSTBACKS_PERMITIDOS:
        raise ErroUfc(
            CodigoErro.ACAO_BLOQUEADA,
            f"Postback ({view_limpa!r}, {rotulo_limpo!r}) fora da lista de leitura permitida.",
            detalhes={"view": view_limpa, "rotulo": rotulo_limpo},
        )
