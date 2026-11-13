"""
Execução dos 8 Canários de Saúde e Integridade Estrutural (`C1` a `C8` — Parte 06, Seção 1).
"""

from __future__ import annotations

from datetime import date, timedelta

from bs4 import BeautifulSoup

from ufc_mcp.fontes.calendario.cliente import ClienteCalendario
from ufc_mcp.fontes.noticias.cliente import ClienteNoticias
from ufc_mcp.fontes.ru.cliente import ClienteRu
from ufc_mcp.fontes.sigaa.cliente import ClienteSigaa
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.modelos_base import BaseModel
from ufc_mcp.nucleo.paginas import validar_campos_visiveis_login
from ufc_mcp.nucleo.risco import ACOES_MENU_PERMITIDAS
from ufc_mcp.nucleo.sessao_sigaa import URL_TELA_LOGIN


class ResultadoCanario(BaseModel):
    id_canario: str
    fonte: str
    requer_login: bool
    ok: bool
    detalhe: str
    codigo_erro: str | None = None


class _C2Tratado(Exception):
    """Sinaliza que o resultado de C2 já foi registrado."""


def _ultima_quarta_util(ref: date | None = None) -> str:
    hoje = ref or date.today()
    for d in range(1, 10):
        cand = hoje - timedelta(days=d)
        if cand.weekday() == 2:  # Quarta-feira
            return cand.isoformat()
    return hoje.isoformat()


async def executar_diagnostico_canarios(
    *,
    ru: ClienteRu,
    calendario: ClienteCalendario,
    noticias: ClienteNoticias,
    sigaa: ClienteSigaa,
    fontes_filtro: list[str] | None = None,
) -> dict[str, object]:
    fontes_ativas = set(fontes_filtro or ["ru", "calendario", "noticias", "sigaa_publico", "sigaa"])
    resultados: list[ResultadoCanario] = []

    # C1 e C2: RU
    if "ru" in fontes_ativas:
        hoje_iso = date.today().isoformat()
        try:
            c1, _, _, _ = await ru.consultar_dia(hoje_iso, restaurante=1, atualizar=True)
            resultados.append(
                ResultadoCanario(
                    id_canario="C1",
                    fonte="ru",
                    requer_login=False,
                    ok=True,
                    detalhe=f"Cardápio de {hoje_iso} verificado (tem_cardapio={c1.tem_cardapio}).",
                )
            )
        except ErroUfc as exc:
            resultados.append(
                ResultadoCanario(
                    id_canario="C1",
                    fonte="ru",
                    requer_login=False,
                    ok=False,
                    detalhe=exc.mensagem,
                    codigo_erro=exc.codigo.value,
                )
            )

        quarta_iso = _ultima_quarta_util()
        try:
            c2, _, _, avisos_c2 = await ru.consultar_dia(quarta_iso, restaurante=1, atualizar=True)
            total_pratos = sum(len(r.pratos) for r in c2.refeicoes)
            if any("não devolveu o cardápio" in a for a in avisos_c2):
                resultados.append(
                    ResultadoCanario(
                        id_canario="C2",
                        fonte="ru",
                        requer_login=False,
                        ok=False,
                        detalhe=f"A página do RU ignorou a data {quarta_iso} e exibiu outro dia.",
                        codigo_erro="LAYOUT_MUDOU",
                    )
                )
                raise _C2Tratado
            # Sem pratos mas com a data confirmada pela página = dia sem cardápio (feriado), válido.
            ok_c2 = total_pratos >= 1 or not c2.tem_cardapio
            resultados.append(
                ResultadoCanario(
                    id_canario="C2",
                    fonte="ru",
                    requer_login=False,
                    ok=ok_c2,
                    detalhe=f"Quarta-feira útil ({quarta_iso}) retornou {total_pratos} pratos.",
                    codigo_erro=None if ok_c2 else "LAYOUT_MUDOU",
                )
            )
        except _C2Tratado:
            pass
        except ErroUfc as exc:
            resultados.append(
                ResultadoCanario(
                    id_canario="C2",
                    fonte="ru",
                    requer_login=False,
                    ok=False,
                    detalhe=exc.mensagem,
                    codigo_erro=exc.codigo.value,
                )
            )

    # C3: Calendário Universitário
    if "calendario" in fontes_ativas:
        ano = date.today().year
        try:
            evs, _, _, _, _ = await calendario.consultar_eventos(
                f"{ano}-01-01", f"{ano}-12-31", limite=200, atualizar=True
            )
            ok_c3 = len(evs) >= 6
            resultados.append(
                ResultadoCanario(
                    id_canario="C3",
                    fonte="calendario",
                    requer_login=False,
                    ok=ok_c3,
                    detalhe=f"Calendário {ano} retornou {len(evs)} eventos estruturados.",
                    codigo_erro=None if ok_c3 else "LAYOUT_MUDOU",
                )
            )
        except ErroUfc as exc:
            resultados.append(
                ResultadoCanario(
                    id_canario="C3",
                    fonte="calendario",
                    requer_login=False,
                    ok=False,
                    detalhe=exc.mensagem,
                    codigo_erro=exc.codigo.value,
                )
            )

    # C4: Feeds RSS de Notícias
    if "noticias" in fontes_ativas:
        try:
            itens_rss, _, _, _ = await noticias.consultar("todas", limite=15, atualizar=True)
            ok_c4 = len(itens_rss) >= 1
            resultados.append(
                ResultadoCanario(
                    id_canario="C4",
                    fonte="noticias",
                    requer_login=False,
                    ok=ok_c4,
                    detalhe=f"Feeds RSS validados ({len(itens_rss)} itens extraídos).",
                    codigo_erro=None if ok_c4 else "LAYOUT_MUDOU",
                )
            )
        except ErroUfc as exc:
            resultados.append(
                ResultadoCanario(
                    id_canario="C4",
                    fonte="noticias",
                    requer_login=False,
                    ok=False,
                    detalhe=exc.mensagem,
                    codigo_erro=exc.codigo.value,
                )
            )

    # C5: Tela Pública de Login do SIGAA
    if "sigaa_publico" in fontes_ativas:
        try:
            resp_login = await sigaa.sessao.http.get(URL_TELA_LOGIN)
            validar_campos_visiveis_login(resp_login.texto)
            resultados.append(
                ResultadoCanario(
                    id_canario="C5",
                    fonte="sigaa_publico",
                    requer_login=False,
                    ok=True,
                    detalhe="loginForm contém exatamente os campos visíveis user.login e user.senha.",
                )
            )
        except ErroUfc as exc:
            resultados.append(
                ResultadoCanario(
                    id_canario="C5",
                    fonte="sigaa_publico",
                    requer_login=False,
                    ok=False,
                    detalhe=exc.mensagem,
                    codigo_erro=exc.codigo.value,
                )
            )

    # C6, C7 e C8: Canários autenticados do SIGAA
    if "sigaa" in fontes_ativas:
        try:
            html_portal = await sigaa.sessao.abrir_portal(forcar_atualizacao=True)
            presentes = sum(1 for ac in ACOES_MENU_PERMITIDAS if ac in html_portal)
            taxa = presentes / len(ACOES_MENU_PERMITIDAS)
            ok_c6 = taxa >= 0.90
            resultados.append(
                ResultadoCanario(
                    id_canario="C6",
                    fonte="sigaa",
                    requer_login=True,
                    ok=ok_c6,
                    detalhe=f"Portal do Discente contém {presentes}/{len(ACOES_MENU_PERMITIDAS)} ({taxa:.0%}) ações de menu.",
                    codigo_erro=None if ok_c6 else "LAYOUT_MUDOU",
                )
            )
        except ErroUfc as exc:
            resultados.append(
                ResultadoCanario(
                    id_canario="C6",
                    fonte="sigaa",
                    requer_login=True,
                    ok=False,
                    detalhe=exc.mensagem,
                    codigo_erro=exc.codigo.value,
                )
            )

        try:
            ira_res, _, _ = await sigaa.obter_historico_ira(atualizar=True)
            resultados.append(
                ResultadoCanario(
                    id_canario="C7",
                    fonte="sigaa",
                    requer_login=True,
                    ok=len(ira_res.registros) >= 1,
                    detalhe=f"Histórico de IRA validado ({len(ira_res.registros)} semestres).",
                )
            )
        except ErroUfc as exc:
            resultados.append(
                ResultadoCanario(
                    id_canario="C7",
                    fonte="sigaa",
                    requer_login=True,
                    ok=False,
                    detalhe=exc.mensagem,
                    codigo_erro=exc.codigo.value,
                )
            )

        try:
            portal_res, _, _ = await sigaa.obter_resumo_portal()
            if not portal_res.turmas:
                raise ErroUfc(
                    CodigoErro.NAO_ENCONTRADO, "Nenhuma turma encontrada para testar C8."
                )
            html_t = await sigaa.sessao.abrir_turma(portal_res.turmas[0].id_turma)
            soup_t = BeautifulSoup(html_t, "lxml")
            texto_menu = soup_t.get_text(" ", strip=True)
            ok_c8 = all(
                rot in texto_menu for rot in ("Ver Notas", "Frequência", "Plano de Curso")
            )
            resultados.append(
                ResultadoCanario(
                    id_canario="C8",
                    fonte="sigaa",
                    requer_login=True,
                    ok=ok_c8,
                    detalhe="Menu da Turma Virtual contém Ver Notas, Frequência e Plano de Curso.",
                    codigo_erro=None if ok_c8 else "LAYOUT_MUDOU",
                )
            )
        except ErroUfc as exc:
            resultados.append(
                ResultadoCanario(
                    id_canario="C8",
                    fonte="sigaa",
                    requer_login=True,
                    ok=False,
                    detalhe=exc.mensagem,
                    codigo_erro=exc.codigo.value,
                )
            )

    todos_ok = all(r.ok for r in resultados)
    return {
        "todos_ok": todos_ok,
        "total_canarios": len(resultados),
        "canarios_ok": sum(1 for r in resultados if r.ok),
        "resultados": [r.model_dump() for r in resultados],
    }
