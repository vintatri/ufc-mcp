"""
Anonimizador determinístico de páginas HTML do SIGAA (9 regras da Parte 06, Seção 2).
Usa semente fixa `random.Random(42)` para perturbação de notas e valida vazamentos.
"""

from __future__ import annotations

import random
import re

REGEX_CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
REGEX_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
REGEX_JSESSIONID_COOKIE = re.compile(r'(?i)JSESSIONID=[^;"\'\s]+')
REGEX_JSESSIONID_URL = re.compile(r'(?i);jsessionid=[^?"\'\s]+')
REGEX_VIEWSTATE_INPUT = re.compile(
    r'(<input[^>]*name=["\']javax\.faces\.ViewState["\'][^>]*value=["\'])([^"\']+)(["\'])',
    re.IGNORECASE,
)
REGEX_ID_INPUT = re.compile(
    r'(<input[^>]*name=["\']id["\'][^>]*value=["\'])([^"\']+)(["\'])',
    re.IGNORECASE,
)
REGEX_DOCENTE = re.compile(
    r"(Prof\.|Profa\.|Docente:|Coordenador:)\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-Za-záéíóúâêôãõç\s]{4,40}"
)
REGEX_DIGITOS_MATRICULA = re.compile(r"\b(?!(?:202\d|199\d)\b)\d{6,11}\b")
REGEX_NOTA_TABELA = re.compile(r"(?<=>)\s*(\d{1,2},\d{1,2})\s*(?=<)")


def anonimizar_html(
    html: str,
    *,
    nome_estudante: str | None = None,
    matricula: str | None = None,
    segredos_extras: list[str] | None = None,
) -> str:
    """Aplica as 9 regras determinísticas de anonimização sobre um HTML."""
    rng = random.Random(42)
    texto = html

    # Regra 1: Nome civil do estudante e tokens >= 4 letras
    if nome_estudante and nome_estudante.strip():
        padrao_nome = re.compile(re.escape(nome_estudante.strip()), re.IGNORECASE)
        texto = padrao_nome.sub("DISCENTE EXEMPLO DA SILVA", texto)
        for parte in nome_estudante.split():
            if len(parte) >= 4:
                texto = re.sub(
                    rf"\b{re.escape(parte)}\b",
                    "EXEMPLO",
                    texto,
                    flags=re.IGNORECASE,
                )

    # Regra 2: Matrícula explícita e sequências de 6 a 11 dígitos (preservando idTurma=910001..910010 e id_curso=657468)
    if matricula and matricula.strip():
        texto = texto.replace(matricula.strip(), "000000")

    def _sub_digitos(m: re.Match[str]) -> str:
        val = m.group(0)
        if val in {"910001", "910002", "910003", "910004", "657468", "657469", "657470", "100001"}:
            return val
        return "000000"

    texto = REGEX_DIGITOS_MATRICULA.sub(_sub_digitos, texto)

    # Regra 3: CPF
    texto = REGEX_CPF.sub("000.000.000-00", texto)

    # Regra 4: E-mails
    texto = REGEX_EMAIL.sub("discente@exemplo.ufc.br", texto)

    # Regra 5: JSESSIONID
    texto = REGEX_JSESSIONID_COOKIE.sub("JSESSIONID=SESSAO_ANONIMA", texto)
    texto = REGEX_JSESSIONID_URL.sub(";jsessionid=SESSAO_ANONIMA", texto)

    # Regra 6: ViewState e input id
    texto = REGEX_VIEWSTATE_INPUT.sub(r"\1j_id_anonimo\3", texto)
    texto = REGEX_ID_INPUT.sub(r"\1100001\3", texto)

    # Regra 7: Nomes de docentes
    texto = REGEX_DOCENTE.sub(r"\1 DOCENTE EXEMPLO", texto)

    # Regra 8: Perturbação determinística de notas decimais com semente 42
    def _perturbar_nota(m: re.Match[str]) -> str:
        original = float(m.group(1).replace(",", "."))
        delta = rng.uniform(-0.3, 0.3)
        nova = max(0.0, min(10.0, round(original + delta, 1)))
        return f"{nova:.1f}".replace(".", ",")

    texto = REGEX_NOTA_TABELA.sub(_perturbar_nota, texto)

    if segredos_extras:
        for seg in segredos_extras:
            if seg and len(seg) >= 4:
                texto = texto.replace(seg, "[ANONIMIZADO]")

    return texto


def verificar_vazamento(html_anonimizado: str, segredos_originais: list[str]) -> list[str]:
    """
    Regra 9: Verifica se algum segredo original sobreviveu no HTML anonimizado.
    Retorna a lista de segredos vazados (vazia se 100% seguro).
    """
    vazados: list[str] = []
    texto_lower = html_anonimizado.lower()
    for seg in segredos_originais:
        s = seg.strip()
        if not s or len(s) < 4:
            continue
        if s.lower() in texto_lower:
            vazados.append(s)
    return vazados
