"""Identificação de telas JSF do SIGAA, extração de formulários e expressões regulares canônicas."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from bs4 import BeautifulSoup, Tag

from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.modelos_base import BaseModel, Field


def achar_tag(no: Any, *args: Any, **kwargs: Any) -> Tag | None:
    """`find` com o tipo estreitado: o bs4 pode devolver `NavigableString`."""
    achado = no.find(*args, **kwargs)
    return achado if isinstance(achado, Tag) else None


def achar_tags(no: Any, *args: Any, **kwargs: Any) -> list[Tag]:
    """`find_all` garantindo apenas elementos `Tag` (nunca `NavigableString`)."""
    return [item for item in no.find_all(*args, **kwargs) if isinstance(item, Tag)]

# 1. Acha a ação JSCookMenu no HTML do portal: grupo 1 = prefixo do menu, grupo 2 = expressão do bean
REGEX_JSCOOK_ACTION = re.compile(
    r"(menu_form_menu_discente\w*_menu):A\]#\{([^}]+)\}"
)

# 2. Extrai o formulário e a lista de pares 'chave,valor,chave2,valor2' de links JSF (jsfcljs)
REGEX_JSFCLJS = re.compile(
    r"jsfcljs\(\s*document\.forms\['([^']+)'\]\s*,\s*'([^']+)'"
)

# 3. Horário de turma expandido na página inicial do SIGAA: ex. "SEG 08:00-10:00"
REGEX_HORARIO_SIGAA = re.compile(
    r"\b(SEG|TER|QUA|QUI|SEX|SAB|DOM)\s+(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\b"
)

# 4. Código de horário compacto do SIGAA: ex. "24M12", "35T34", "6N1234"
REGEX_CODIGO_HORARIO_COMPACTO = re.compile(
    r"\b([2-7]+)\s*([MTN])\s*([1-6]+)\b"
)

# 5. Vigência da turma: ex. "(10/08/2026 - 11/12/2026)"
REGEX_VIGENCIA_TURMA = re.compile(
    r"\((\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})\)"
)

# 6. Código de componente curricular da UFC: ex. "CT0101", "EQ0042", "RUS0123"
REGEX_CODIGO_COMPONENTE = re.compile(r"\b([A-Z]{2,4}\d{3,4})\b")

# 7. ID de componente na div de progresso: ex. "desc_g_periodo_3_cc_65432"
REGEX_ID_PROGRESSO = re.compile(r"^desc_g_periodo_(\d+)_cc_(\d+)$")

# 8. Verbos de mutação proibidos em qualquer rótulo de postback
REGEX_VERBOS_PROIBIDOS = re.compile(
    r"(?i)\b(tranc|suprim|cancel|exclu|remov|apag|solicit|confirm|envi|cadastr|"
    r"inscrev|matricul|salv|alter|grav|respond|submet|aceit|recus|desist|rescind|"
    r"agendar|public|postar|votar|emitir)\w*"
)

# 9. Bloqueio deliberado do SIGAA a acesso automatizado (tolerante a acentos e maiúsculas)
REGEX_ACESSO_APLICATIVO_NEGADO = re.compile(
    r"Tentativa\s+de\s+acesso\s+por\s+aplicativo\s+externo|Opera[cç][aã]o\s+negada",
    re.IGNORECASE,
)


class TipoPagina(StrEnum):
    """Classificação estrutural de uma página HTML retornada pelo SIGAA."""

    ACESSO_APLICATIVO_NEGADO = "ACESSO_APLICATIVO_NEGADO"
    TELA_LOGIN = "TELA_LOGIN"
    LOGIN_INVALIDO = "LOGIN_INVALIDO"
    SESSAO_EXPIRADA = "SESSAO_EXPIRADA"
    SELECAO_VINCULO = "SELECAO_VINCULO"
    QUESTIONARIO_INTERSTICIAL = "QUESTIONARIO_INTERSTICIAL"
    PORTAL_DISCENTE = "PORTAL_DISCENTE"
    TURMA_VIRTUAL = "TURMA_VIRTUAL"
    TELA_INTERNA = "TELA_INTERNA"
    ERRO_SISTEMA = "ERRO_SISTEMA"


class FormularioJsf(BaseModel):
    """Representa um formulário HTML/JSF extraído com seu action, view e campos ocultos."""

    nome: str
    action: str
    view: str
    campos: dict[str, str] = Field(default_factory=dict)


def extrair_pares_jsfcljs(onclick: str) -> tuple[str, dict[str, str]]:
    """
    Recebe o atributo onclick de um link JSF e devolve (nome_do_form, {chave: valor}).
    Levanta ErroUfc(LAYOUT_MUDOU) se o padrão jsfcljs não for encontrado ou tiver número ímpar de itens.
    """
    m = REGEX_JSFCLJS.search(onclick)
    if not m:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            "Atributo onclick não contém chamada jsfcljs válida.",
        )
    nome_form = m.group(1)
    partes = [p.strip() for p in m.group(2).split(",") if p.strip()]
    if len(partes) % 2 != 0:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            "Lista de parâmetros jsfcljs malformada (número ímpar de elementos).",
        )
    pares = {partes[i]: partes[i + 1] for i in range(0, len(partes), 2)}
    return nome_form, pares


def identificar_pagina(html: str) -> TipoPagina:
    """Identifica deterministicamente o tipo de tela do SIGAA."""
    soup = BeautifulSoup(html, "lxml")
    texto = soup.get_text(" ", strip=True)

    if re.search(r"Usu[aá]rio e/ou senha inv[aá]lidos", texto, re.IGNORECASE):
        return TipoPagina.LOGIN_INVALIDO

    if REGEX_ACESSO_APLICATIVO_NEGADO.search(texto):
        return TipoPagina.ACESSO_APLICATIVO_NEGADO

    if soup.find("form", attrs={"name": "loginForm"}) is not None:
        return TipoPagina.TELA_LOGIN

    if re.search(
        r"(Sess[aã]o expirada|Comportamento inesperado|ViewExpiredException)",
        texto,
        re.IGNORECASE,
    ):
        return TipoPagina.SESSAO_EXPIRADA

    if soup.find("a", href=re.compile(r"escolheVinculo\.do")) is not None or re.search(
        r"Escolha o V[ií]nculo", texto, re.IGNORECASE
    ):
        return TipoPagina.SELECAO_VINCULO

    if soup.find("a", string=re.compile(r"Responder depois|Continuar para o Portal", re.I)):
        return TipoPagina.QUESTIONARIO_INTERSTICIAL

    if (
        soup.find(id="turmas-portal") is not None
        or soup.find("form", id="menu:form_menu_discente") is not None
        or soup.find("form", attrs={"name": "menu:form_menu_discente"}) is not None
    ):
        return TipoPagina.PORTAL_DISCENTE

    form_ava = achar_tag(soup, "form", id="formMenu") or achar_tag(
        soup, "form", attrs={"name": "formMenu"}
    )
    if form_ava is not None and "/sigaa/ava/" in str(form_ava.get("action", "")):
        return TipoPagina.TURMA_VIRTUAL

    if re.search(r"Ocorreu um erro inesperado no sistema", texto, re.IGNORECASE):
        return TipoPagina.ERRO_SISTEMA

    return TipoPagina.TELA_INTERNA


def titulo_da_tela(html: str) -> str:
    """Extrai o título principal da tela interna do SIGAA (`#conteudo h2`, `h3` ou `caption`)."""
    soup = BeautifulSoup(html, "lxml")
    for sel in ("#conteudo h2", "h2.title", "h2.tituloPagina", "#conteudo h3", "caption.formulario", "title"):
        el = soup.select_one(sel)
        if el:
            txt = " ".join(el.get_text(" ", strip=True).split())
            if txt:
                return txt
    return ""


def extrair_formulario(html: str, nome_ou_id: str, *, incluir_botoes: bool = False) -> FormularioJsf:
    """Extrai action, caminho da view JSF e todos os inputs de um formulário pelo nome ou id."""
    soup = BeautifulSoup(html, "lxml")
    form = achar_tag(soup, "form", attrs={"name": nome_ou_id}) or achar_tag(
        soup, "form", id=nome_ou_id
    )
    if form is None:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            f"Formulário JSF '{nome_ou_id}' não encontrado na página.",
        )
    action_bruto = str(form.get("action") or "").strip()
    if not action_bruto:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            f"Formulário JSF '{nome_ou_id}' não possui atributo action.",
        )
    view = action_bruto.split(";")[0].split("?")[0]
    campos: dict[str, str] = {}
    for inp in form.find_all("input"):
        tipo = str(inp.get("type") or "text").lower()
        if tipo in ("submit", "button", "image", "reset") and not incluir_botoes:
            continue
        nome_campo = inp.get("name")
        if nome_campo:
            campos[str(nome_campo)] = str(inp.get("value") or "")
    for select in form.find_all("select"):
        nome_campo = select.get("name")
        if not nome_campo:
            continue
        opcao = select.find("option", selected=True) or select.find("option")
        if opcao is not None:
            campos[str(nome_campo)] = str(opcao.get("value") or opcao.get_text(strip=True))
    return FormularioJsf(nome=nome_ou_id, action=action_bruto, view=view, campos=campos)


def validar_campos_visiveis_login(html: str) -> None:
    """
    Canário C5 / Invariante de Login: verifica que `loginForm` contém apenas
    os campos visíveis `user.login` e `user.senha`. Levanta LAYOUT_MUDOU se houver CAPTCHA/2FA.
    """
    soup = BeautifulSoup(html, "lxml")
    form = achar_tag(soup, "form", attrs={"name": "loginForm"})
    if form is None:
        raise ErroUfc(CodigoErro.LAYOUT_MUDOU, "Formulário loginForm não encontrado.")
    visiveis: set[str] = set()
    for inp in form.find_all("input"):
        tipo = str(inp.get("type") or "text").lower()
        if tipo in ("hidden", "submit", "button", "image"):
            continue
        nome = str(inp.get("name") or "")
        if nome:
            visiveis.add(nome)
    if visiveis != {"user.login", "user.senha"}:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            f"Campos visíveis inesperados na tela de login: {sorted(visiveis)}",
        )
