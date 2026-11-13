"""
Parser Genérico das 15 Telas de Listagem do Portal do Discente (`listagem`).
Implementa as 5 regras da Parte 05, Ferramenta 17 (incluindo detecção de retorno ao portal
com aviso `.erros/.warning/.info`, omissão de Dados do Discente e exclusão de botões de ação).
"""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from ufc_mcp.fontes.sigaa.modelos import (
    TIPOS_LISTAGEM_PERMITIDOS,
    ResultadoListagemGenerica,
    TabelaListagemGenerica,
)
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.paginas import TipoPagina, achar_tag, identificar_pagina, titulo_da_tela

MAPA_ACAO_MENU_LISTAGEM: dict[str, str] = {
    "enfases": "registroDiscenteEnfaseMBean.iniciarBuscaRegistrosDiscente",
    "plano_estudo": "planoEstudoPortalDiscenteMBean.iniciarVizualizacaoMovimentacoesPortalDiscente",
    "enade": "participacaoDiscenteEnade.iniciarVizualizacaoParticipacoes",
    "bloqueios": "marcacaoBloqueioDiscenteGraduacaoMBean.iniciarBuscaBloqueiosUsuarioDiscente",
    "movimentacoes": "movimentacaoAluno.iniciarVizualizacaoMovimentacoesPortalDiscente",
    "mobilidades": "mobilidadeEstudantil.listarMobilidadesDiscente",
    "solicitacoes_mobilidade": "solicitacaoMobilidadeEstudantilPerfilDiscente.listarMinhasSolicitacoes",
    "matricula_solicitacoes": "matriculaGraduacao.acompanharSolicitacoes",
    "trancamentos": "trancamentoMatricula.iniciarMeusTrancamentos",
    "supressoes": "supressaoMatricula.iniciarMinhasSupressoes",
    "extensao_minhas_acoes": "documentosAutenticadosExtensao.participacoesDiscenteUsuarioLogado",
    "auxilios_anuncios": "interessadoAuxilio.listarAnuncios",
    "auxilios_meus_processos": "interessadoAuxilio.acompanharInscricoes",
    "bolsas_indicacoes": "aceiteIndicacaoBolsa.iniciarListaIndicacoesDiscente",
    "estagios_termos": "termoEstagioMBean.iniciarConsulta",
}

ASSINATURAS_LISTAGEM: dict[str, tuple[str, ...]] = {
    "enfases": ("ênfase", "enfase", "registro"),
    "plano_estudo": ("plano de estudo", "plano"),
    "enade": ("enade", "participa"),
    "bloqueios": ("bloqueio",),
    "movimentacoes": ("movimenta", "afastamento"),
    "mobilidades": ("mobilidade",),
    "solicitacoes_mobilidade": ("solicita", "mobilidade"),
    "matricula_solicitacoes": ("solicita", "matrícula", "matricula"),
    "trancamentos": ("trancamento",),
    "supressoes": ("supress",),
    "extensao_minhas_acoes": ("extens", "ação", "acoes"),
    "auxilios_anuncios": ("auxílio", "auxilio", "edital", "anúncio"),
    "auxilios_meus_processos": ("inscri", "auxílio", "processo"),
    "bolsas_indicacoes": ("bolsa", "indica"),
    "estagios_termos": ("estágio", "estagio", "termo"),
}


def _limpar_celula_sem_acao(td: Tag) -> str:
    """Extrai apenas texto visível legítimo, ignorando links/botões de ação JSF (`onclick`)."""
    copia = BeautifulSoup(str(td), "lxml")
    for el_acao in copia.find_all(["a", "input", "button", "img"]):
        if el_acao.decomposed:  # já removido junto com um ancestral
            continue
        if el_acao.name in ("input", "button", "img"):
            el_acao.decompose()
            continue
        if el_acao.get("onclick") or el_acao.find("img"):
            el_acao.decompose()
    return " ".join(copia.get_text(" ", strip=True).split())


def parse_listagem_generica(
    html: str, *, tipo: str, max_linhas: int = 50
) -> ResultadoListagemGenerica:
    if tipo not in TIPOS_LISTAGEM_PERMITIDOS:
        raise ErroUfc(CodigoErro.PARAMETRO_INVALIDO, f"Tipo de listagem inválido: {tipo}")

    soup = BeautifulSoup(html, "lxml")

    # Regra 1: Retorno ao PORTAL_DISCENTE com aviso em .erros/.warning/.info
    if identificar_pagina(html) == TipoPagina.PORTAL_DISCENTE:
        msgs = [
            " ".join(li.get_text(" ", strip=True).split())
            for li in soup.select(".erros li, .warning li, .info li, #painel-erros li")
        ]
        msgs = [m for m in msgs if m]
        if msgs:
            return ResultadoListagemGenerica(
                tipo=tipo,
                vazio=True,
                mensagem="; ".join(msgs),
                tabelas=[],
            )
        # O SIGAA devolve o próprio portal, sem lista nem aviso, quando a funcionalidade não está
        # disponível no momento (ex.: trancamento/solicitações fora do período). Não é mudança de layout.
        return ResultadoListagemGenerica(
            tipo=tipo,
            vazio=True,
            mensagem="O SIGAA retornou ao Portal do Discente sem listar itens "
            "(funcionalidade indisponível no momento ou sem registros).",
            tabelas=[],
        )

    conteudo = achar_tag(soup, id="conteudo") or soup
    texto_conteudo = conteudo.get_text(" ", strip=True).lower()
    titulo = titulo_da_tela(html).lower()

    msgs_vazio = [
        " ".join(el.get_text(" ", strip=True).split())
        for el in soup.select(".erros li, .warning li, .info li, .vazio")
    ]
    if any(
        frase in texto_conteudo
        for frase in (
            "nenhum registro encontrado",
            "não foram encontrados registros",
            "nao foram encontrados registros",
            "nenhuma solicitação encontrada",
            "lista vazia",
        )
    ):
        return ResultadoListagemGenerica(
            tipo=tipo,
            vazio=True,
            mensagem=msgs_vazio[0] if msgs_vazio else "Nenhum registro encontrado.",
            tabelas=[],
        )

    assinaturas = ASSINATURAS_LISTAGEM.get(tipo, ())
    if not any(ass in titulo or ass in texto_conteudo for ass in assinaturas):
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            f"Assinatura estrutural para a listagem '{tipo}' não reconhecida.",
        )

    tabelas_extraidas: list[TabelaListagemGenerica] = []
    for table in conteudo.find_all("table"):
        classes_t = {str(c) for c in (table.get("class") or [])}
        if not classes_t.intersection({"listagem", "visualizacao", "formulario", "subFormulario"}):
            continue

        # Regra 4: Ignorar tabelas de identificação do aluno ou formulários de busca
        ths_brutos = [" ".join(th.get_text(" ", strip=True).split()) for th in table.find_all("th")]
        if any(r in " ".join(ths_brutos).lower() for r in ("matrícula:", "discente:", "cpf:")):
            continue
        if table.find("input", attrs={"type": "text"}) or table.find("select"):
            continue

        cap = table.find("caption")
        titulo_tab = " ".join(cap.get_text(" ", strip=True).split()) if cap else (titulo_da_tela(html) or tipo)
        cabecalhos = [h for h in ths_brutos if h]

        linhas: list[list[str]] = []
        truncada = False
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if not tds:
                continue
            valores = [_limpar_celula_sem_acao(td) for td in tds]
            valores_nao_vazios = [v for v in valores if v]
            if not valores_nao_vazios:
                continue
            if len(linhas) >= max_linhas:
                truncada = True
                break
            linhas.append(valores_nao_vazios)

        if linhas:
            tabelas_extraidas.append(
                TabelaListagemGenerica(
                    titulo=titulo_tab,
                    cabecalhos=cabecalhos,
                    linhas=linhas,
                    truncada=truncada,
                )
            )

    if not tabelas_extraidas:
        return ResultadoListagemGenerica(
            tipo=tipo,
            vazio=True,
            mensagem="Nenhum item listado.",
            tabelas=[],
        )

    return ResultadoListagemGenerica(
        tipo=tipo,
        vazio=False,
        mensagem=None,
        tabelas=tabelas_extraidas,
    )
