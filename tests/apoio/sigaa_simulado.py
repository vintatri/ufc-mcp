"""
Simulador determinístico em memória do ecossistema da UFC (`si3.ufc.br`, `ufc2012.ufc.br`,
feeds RSS e download binário de PDFs de aula com validação de `javax.faces.ViewState`).
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx

from ufc_mcp.fontes.sigaa.parsers.listagem import MAPA_ACAO_MENU_LISTAGEM
from ufc_mcp.gravador.gravar import (
    html_agenda_padrao,
    html_calendario_curso_publico_padrao,
    html_calendario_ufc,
    html_ira_padrao,
    html_listagem_padrao,
    html_ofertas_padrao,
    html_pendencias_padrao,
    html_portal_discente_padrao,
    html_progresso_padrao,
    html_ru_cardapio,
    html_turma_virtual_secao,
    xml_rss_padrao,
)


def _escapar_pdf_texto(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def gerar_pdf_aula_bytes() -> bytes:
    """Gera um PDF multipágina válido em memória com texto extraível de Engenharia Química."""
    paginas = [
        "Balanco de massa. Fracao massica de um componente = massa do componente / massa total da mistura.",
        "Exemplo: misturam-se 100 kg/h de solucao com 10% de soluto e 100 kg/h de agua pura. Soluto: 10 kg/h. Mistura: 200 kg/h. Fracao massica final: 5%.",
        "Exercicio: misture 60 kg/h de solucao a 10% com 40 kg/h de agua pura. Calcule a fracao massica final.",
    ]

    # Obj 1: Catalog, Obj 2: Pages, Obj 3: Font Helvetica
    # Para cada pagina i: Obj (4 + 2*i) = Page, Obj (5 + 2*i) = Content stream
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(paginas)))
    objetos: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(paginas)} >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, texto in enumerate(paginas):
        num_stream = 5 + 2 * i
        objetos.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {num_stream} 0 R >>"
            ).encode("ascii")
        )
        conteudo = f"BT\n/F1 12 Tf\n72 720 Td\n({_escapar_pdf_texto(texto)}) Tj\nET\n".encode("ascii")
        objetos.append(
            f"<< /Length {len(conteudo)} >>\nstream\n".encode("ascii") + conteudo + b"endstream"
        )

    partes: list[bytes] = [b"%PDF-1.4\n"]
    offsets: list[int] = [0]
    pos = len(partes[0])
    for idx, corpo in enumerate(objetos, start=1):
        offsets.append(pos)
        bloco = f"{idx} 0 obj\n".encode("ascii") + corpo + b"\nendobj\n"
        partes.append(bloco)
        pos += len(bloco)

    inicio_xref = pos
    linhas_xref = [f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode("ascii")]
    for off in offsets[1:]:
        linhas_xref.append(f"{off:010d} 00000 n \n".encode("ascii"))
    trailer = (
        f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\n"
        f"startxref\n{inicio_xref}\n%%EOF\n"
    ).encode("ascii")

    return b"".join(partes + linhas_xref + [trailer])


class TransporteUfcSimulado(httpx.AsyncBaseTransport):
    """Transporte httpx assíncrono que simula todas as rotas da UFC localmente."""

    def __init__(self, *, senha_esperada: str = "senha_correta_123") -> None:
        self.senha_esperada = senha_esperada
        self.view_ativa_servidor: str = "PORTAL"
        self.contagem_logins: int = 0
        self.pdf_bytes = gerar_pdf_aula_bytes()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        parsed = urlparse(url)
        host = parsed.hostname or ""
        path = parsed.path

        # 1. Redirecionamento http:// -> https:// no si3.ufc.br
        if parsed.scheme == "http":
            return httpx.Response(302, headers={"Location": url.replace("http://", "https://", 1)})

        # 2. Restaurante Universitário
        if host == "ufc2012.ufc.br" and "/restaurante/cardapio/" in path:
            qs = parse_qs(parsed.query)
            dt = qs.get("data", ["2026-11-13"])[0]
            vazio = dt.endswith("-15")
            return httpx.Response(
                200,
                headers={"Content-Type": "text/html; charset=utf-8"},
                content=html_ru_cardapio(data_iso=dt, vazio=vazio).encode("utf-8"),
            )

        # 3. Calendário Universitário
        if host == "ufc2012.ufc.br" and "/calendario-universitario" in path:
            return httpx.Response(
                200,
                headers={"Content-Type": "text/html; charset=utf-8"},
                content=html_calendario_ufc().encode("utf-8"),
            )

        # 4. Feeds RSS
        if host in ("ufcinforma.ufc.br", "prograd.ufc.br", "prae.ufc.br"):
            fonte_nome = host.split(".")[0].replace("ufcinforma", "ufc")
            return httpx.Response(
                200,
                headers={"Content-Type": "application/xml; charset=utf-8"},
                content=xml_rss_padrao(fonte_nome).encode("utf-8"),
            )

        # 5. SIGAA Público e Autenticado (si3.ufc.br)
        if host == "si3.ufc.br":
            if path == "/sigaa/public/curso/calendario.jsf":
                return httpx.Response(
                    200,
                    content=html_calendario_curso_publico_padrao(
                        657468, "ENGENHARIA QUÍMICA"
                    ).encode("iso-8859-1", errors="replace"),
                )
            if path == "/sigaa/public/curso/turmas.jsf":
                return httpx.Response(
                    200,
                    content=html_ofertas_padrao().encode("iso-8859-1", errors="replace"),
                )
            if path == "/sigaa/verTelaLogin.do":
                html_l = (
                    '<html><body><form name="loginForm" action="/sigaa/logar.do?dispatch=logOn" method="post">'
                    '<input type="text" name="user.login" value="" />'
                    '<input type="password" name="user.senha" value="" />'
                    '<input type="hidden" name="width" value="1920" />'
                    '<input type="submit" name="entrar" value="Entrar" />'
                    "</form></body></html>"
                )
                return httpx.Response(200, content=html_l.encode("iso-8859-1"))

            if path == "/sigaa/logar.do":
                self.contagem_logins += 1
                corpo_form = parse_qs(request.content.decode("utf-8", errors="replace"))
                senha = corpo_form.get("user.senha", [""])[0]
                if senha != self.senha_esperada:
                    return httpx.Response(
                        200,
                        content=b"<html><body><div class='erros'>Usuario e/ou senha invalidos.</div></body></html>",
                    )
                return httpx.Response(
                    302,
                    headers={
                        "Location": "http://si3.ufc.br/sigaa/verPortalDiscente.do",
                        "Set-Cookie": "JSESSIONID=SESSAO_SIMULADA_UFC; Path=/sigaa",
                    },
                )

            if path == "/sigaa/verPortalDiscente.do":
                self.view_ativa_servidor = "PORTAL"
                return httpx.Response(
                    200,
                    content=html_portal_discente_padrao().encode("iso-8859-1", errors="replace"),
                )

            if path == "/sigaa/portais/discente/discente.jsf" and request.method == "POST":
                dados = parse_qs(request.content.decode("utf-8", errors="replace"))
                if "idTurma" in dados and any("turmaVirtual" in k for k in dados):
                    self.view_ativa_servidor = "AVA:Principal"
                    return httpx.Response(
                        200,
                        content=html_turma_virtual_secao("principal").encode(
                            "iso-8859-1", errors="replace"
                        ),
                    )

                jscook = dados.get("jscook_action", [""])[0]
                if "iniciarConsultaProgresso" in jscook:
                    self.view_ativa_servidor = "MENU:Progresso"
                    return httpx.Response(
                        200,
                        content=html_progresso_padrao().encode("iso-8859-1", errors="replace"),
                    )
                if "iniciarConsultaHistoricoIRA" in jscook:
                    self.view_ativa_servidor = "MENU:IRA"
                    return httpx.Response(
                        200,
                        content=html_ira_padrao().encode("iso-8859-1", errors="replace"),
                    )
                if "iniciarConsultaPendencias" in jscook:
                    self.view_ativa_servidor = "MENU:Pendencias"
                    return httpx.Response(
                        200,
                        content=html_pendencias_padrao("Pendências para Conclusão de Curso").encode(
                            "iso-8859-1", errors="replace"
                        ),
                    )
                if "iniciarConsultaSituacao" in jscook:
                    self.view_ativa_servidor = "MENU:Biblioteca"
                    return httpx.Response(
                        200,
                        content=html_pendencias_padrao("Situação na Biblioteca").encode(
                            "iso-8859-1", errors="replace"
                        ),
                    )
                if "visualizarAgendaTurmas" in jscook:
                    self.view_ativa_servidor = "MENU:Agenda"
                    return httpx.Response(
                        200,
                        content=html_agenda_padrao().encode("iso-8859-1", errors="replace"),
                    )

                for t_list, bean_str in MAPA_ACAO_MENU_LISTAGEM.items():
                    if bean_str in jscook:
                        self.view_ativa_servidor = f"MENU:{t_list}"
                        return httpx.Response(
                            200,
                            content=html_listagem_padrao(t_list).encode(
                                "iso-8859-1", errors="replace"
                            ),
                        )

            if path == "/sigaa/ava/index.jsf" and request.method == "POST":
                dados = parse_qs(request.content.decode("utf-8", errors="replace"))
                if "formAvaMat:download" in dados:
                    if self.view_ativa_servidor != "AVA:Principal":
                        return httpx.Response(
                            200,
                            headers={"Content-Type": "text/html"},
                            content=b"<html><body>ViewState invalido fora da pagina Principal</body></html>",
                        )
                    return httpx.Response(
                        200,
                        headers={
                            "Content-Type": "application/pdf",
                            "Content-Disposition": 'attachment; filename="Slides_Navier_Stokes.pdf"',
                        },
                        content=self.pdf_bytes,
                    )

                acao = dados.get("acao", ["Principal"])[0]
                mapa_sec = {
                    "Principal": "principal",
                    "Ver Notas": "notas",
                    "Frequência": "frequencia",
                    "Avaliações": "avaliacoes",
                    "Tarefas": "tarefas",
                    "Notícias": "noticias",
                    "Plano de Curso": "plano_curso",
                    "Visualizar Programa": "plano_curso",
                }
                sec = mapa_sec.get(acao, "principal")
                self.view_ativa_servidor = f"AVA:{acao}"
                return httpx.Response(
                    200,
                    content=html_turma_virtual_secao(sec).encode("iso-8859-1", errors="replace"),
                )

        return httpx.Response(404, content=b"Nao encontrado no simulador")
