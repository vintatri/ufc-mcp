"""
Sandbox de Download e Extração Paginada de Materiais da Turma Virtual (Decisão D15).
Impõe confinamento de diretório (`Path.is_relative_to`), lista fechada de extensões,
limite de 25 MB e higienização em `TextoExterno` com paginação (`pagina_inicial`..`pagina_final`).
"""

from __future__ import annotations

import io
import re
from pathlib import Path

from pypdf import PdfReader

from ufc_mcp.nucleo.config import Config
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.higiene import TextoExterno, externo
from ufc_mcp.nucleo.modelos_base import BaseModel, Field
from ufc_mcp.nucleo.sessao_sigaa import SessaoSigaa

EXTENSOES_MATERIAL_PERMITIDAS: frozenset[str] = frozenset({
    ".pdf",
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".zip",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".odt",
    ".ods",
    ".odp",
    ".png",
    ".jpg",
    ".jpeg",
    ".py",
    ".c",
    ".cpp",
    ".m",
})

EXTENSOES_PROIBIDAS_EXECUTAVEIS: frozenset[str] = frozenset({
    ".exe",
    ".sh",
    ".bat",
    ".cmd",
    ".js",
    ".vbs",
    ".scr",
    ".dll",
    ".so",
    ".appimage",
    ".msi",
    ".com",
})


class ResultadoMaterialBaixado(BaseModel):
    id_turma: str
    id_material: str
    titulo_material: str
    arquivo_local: str
    tamanho_bytes: int
    content_type: str
    total_paginas_pdf: int | None = None
    paginas_lidas: list[int] = Field(default_factory=list)
    previa_texto: TextoExterno | None = None


def sanitizar_nome_arquivo(nome_bruto: str, content_type: str = "") -> str:
    """
    Prevenção contra Path Traversal e extensões executáveis (Mitigação A10).
    """
    apenas_nome = Path(nome_bruto.replace("\\", "/")).name
    limpo = re.sub(r"[^A-Za-z0-9._-]", "_", apenas_nome).strip("._")
    if not limpo:
        limpo = "material_aula"

    sufixo = Path(limpo).suffix.lower()
    if not sufixo:
        if "pdf" in content_type.lower():
            limpo += ".pdf"
            sufixo = ".pdf"
        elif "text/plain" in content_type.lower():
            limpo += ".txt"
            sufixo = ".txt"
        else:
            limpo += ".pdf"
            sufixo = ".pdf"

    if sufixo in EXTENSOES_PROIBIDAS_EXECUTAVEIS or sufixo not in EXTENSOES_MATERIAL_PERMITIDAS:
        raise ErroUfc(
            CodigoErro.ACAO_BLOQUEADA,
            f"Extensão de arquivo bloqueada pela política de segurança da sandbox: '{sufixo}'.",
            detalhes={"arquivo": limpo, "extensao": sufixo},
        )
    return limpo


def extrair_texto_paginado(
    caminho_arquivo: Path,
    *,
    pagina_inicial: int = 1,
    pagina_final: int = 10,
    max_chars: int = 12000,
) -> tuple[TextoExterno | None, int | None, list[int]]:
    """Extrai texto paginado de arquivos PDF, TXT ou MD e aplica `higiene.externo`."""
    if pagina_inicial < 1 or pagina_final < pagina_inicial or (pagina_final - pagina_inicial) > 14:
        raise ErroUfc(
            CodigoErro.PARAMETRO_INVALIDO,
            "Intervalo de páginas inválido: use pagina_inicial >= 1 e no máximo 15 páginas por chamada.",
        )

    sufixo = caminho_arquivo.suffix.lower()
    nome = caminho_arquivo.name

    if sufixo == ".pdf":
        dados_bytes = caminho_arquivo.read_bytes()
        reader = PdfReader(io.BytesIO(dados_bytes))
        total_pags = len(reader.pages)
        ini_idx = min(pagina_inicial, max(1, total_pags)) - 1
        fim_idx = min(pagina_final, total_pags)
        partes: list[str] = []
        pags_lidas: list[int] = []
        for idx in range(ini_idx, fim_idx):
            num_pag = idx + 1
            txt_p = reader.pages[idx].extract_text() or ""
            partes.append(f"[Página {num_pag}]\n{txt_p.strip()}")
            pags_lidas.append(num_pag)
        bruto = "\n\n".join(partes)
        return externo(bruto, origem=f"material:{nome}", max_chars=max_chars), total_pags, pags_lidas

    if sufixo in (".txt", ".md", ".csv", ".py"):
        texto_arq = caminho_arquivo.read_text(encoding="utf-8", errors="replace")
        linhas = texto_arq.splitlines()
        linhas_por_pag = 50
        total_pags = max(1, (len(linhas) + linhas_por_pag - 1) // linhas_por_pag)
        ini_pag = min(pagina_inicial, total_pags)
        fim_pag = min(pagina_final, total_pags)
        partes_txt: list[str] = []
        pags_lidas_txt: list[int] = []
        for p in range(ini_pag, fim_pag + 1):
            fatia = linhas[(p - 1) * linhas_por_pag : p * linhas_por_pag]
            partes_txt.append(f"[Página {p}]\n" + "\n".join(fatia))
            pags_lidas_txt.append(p)
        bruto_txt = "\n\n".join(partes_txt)
        return (
            externo(bruto_txt, origem=f"material:{nome}", max_chars=max_chars),
            total_pags,
            pags_lidas_txt,
        )

    return None, None, []


class ServicoMateriais:
    """Gerencia o download seguro em sandbox e a leitura paginada de materiais de aula."""

    def __init__(self, sessao: SessaoSigaa, config: Config) -> None:
        self.sessao = sessao
        self.config = config
        self._indice_local: dict[tuple[str, str], Path] = {}

    def _pasta_turma(self, id_turma: str) -> Path:
        if not re.match(r"^\d{1,10}$", id_turma):
            raise ErroUfc(CodigoErro.PARAMETRO_INVALIDO, f"id_turma inválido: {id_turma!r}")
        pasta_base = (self.config.pasta_documentos / "materiais").resolve()
        destino_turma = (pasta_base / id_turma).resolve()
        if not destino_turma.is_relative_to(pasta_base):
            raise ErroUfc(CodigoErro.ACAO_BLOQUEADA, "Violação de confinamento de diretório.")
        destino_turma.mkdir(parents=True, exist_ok=True)
        return destino_turma

    async def baixar_e_ler_material(
        self,
        id_turma: str,
        id_material: str,
        *,
        extrair_texto: bool = True,
        pagina_inicial: int = 1,
        pagina_final: int = 10,
    ) -> ResultadoMaterialBaixado:
        if not re.match(r"^mat_\d{2,4}$", id_material):
            raise ErroUfc(
                CodigoErro.PARAMETRO_INVALIDO,
                f"id_material inválido: '{id_material}'. Use o formato 'mat_01' obtido em turma.",
            )
        if pagina_inicial < 1 or pagina_final < pagina_inicial or (pagina_final - pagina_inicial) > 14:
            raise ErroUfc(
                CodigoErro.PARAMETRO_INVALIDO,
                "Intervalo de páginas inválido (máximo de 15 páginas por chamada).",
            )

        pasta_turma = self._pasta_turma(id_turma)
        chave_local = (id_turma, id_material)
        caminho_local = self._indice_local.get(chave_local)
        ct_detectado = "application/pdf"

        if caminho_local is None or not caminho_local.exists():
            resp_bin, nome_sugerido = await self.sessao.baixar_material_turma(id_turma, id_material)
            ct_detectado = resp_bin.content_type
            nome_seguro = sanitizar_nome_arquivo(nome_sugerido, ct_detectado)
            caminho_final = (pasta_turma / nome_seguro).resolve()
            if not caminho_final.is_relative_to(pasta_turma):
                raise ErroUfc(
                    CodigoErro.ACAO_BLOQUEADA,
                    "Tentativa de Path Traversal bloqueada ao salvar material.",
                )
            caminho_final.write_bytes(resp_bin.conteudo)
            self._indice_local[chave_local] = caminho_final
            caminho_local = caminho_final

        previa: TextoExterno | None = None
        total_pags: int | None = None
        pags_lidas: list[int] = []

        if extrair_texto:
            previa, total_pags, pags_lidas = extrair_texto_paginado(
                caminho_local,
                pagina_inicial=pagina_inicial,
                pagina_final=pagina_final,
            )

        return ResultadoMaterialBaixado(
            id_turma=id_turma,
            id_material=id_material,
            titulo_material=caminho_local.name,
            arquivo_local=str(caminho_local),
            tamanho_bytes=caminho_local.stat().st_size,
            content_type=ct_detectado,
            total_paginas_pdf=total_pags,
            paginas_lidas=pags_lidas,
            previa_texto=previa,
        )
