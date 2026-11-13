"""Parser puro do Histórico de IRA (`consulta_ira.jsf`)."""

from __future__ import annotations

from bs4 import BeautifulSoup

from ufc_mcp.fontes.sigaa.modelos import RegistroIraSemestre, ResultadoHistoricoIra
from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc


def _conv_float(s: str) -> float | None:
    limpo = s.strip()
    if "," in limpo:
        # Formato brasileiro: ponto = milhar, vírgula = decimal ("1.234,56").
        limpo = limpo.replace(".", "").replace(",", ".")
    # Sem vírgula, o ponto já é o separador decimal ("7.6612"), como nos dados do gráfico do SIGAA.
    try:
        return round(float(limpo), 4)
    except ValueError:
        return None


def parse_historico_ira(html: str) -> ResultadoHistoricoIra:
    soup = BeautifulSoup(html, "lxml")
    mapa_ind: dict[str, tuple[float, float]] = {}
    mapa_curso: dict[str, tuple[float | None, float | None]] = {}

    for table in soup.find_all("table"):
        ths = [" ".join(th.get_text(" ", strip=True).split()).upper() for th in table.find_all("th")]
        texto_ths = " | ".join(ths)
        if "IRA-I" in texto_ths and "IRA-G" in texto_ths:
            for tr in table.find_all("tr"):
                tds = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all("td")]
                if len(tds) >= 3:
                    per = tds[0]
                    irai = _conv_float(tds[1])
                    irag = _conv_float(tds[2])
                    if per and irai is not None and irag is not None:
                        mapa_ind[per] = (irai, irag)
        elif ("MÉDIA" in texto_ths or "MEDIA" in texto_ths) and "DESVIO" in texto_ths:
            for tr in table.find_all("tr"):
                tds = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all("td")]
                if len(tds) >= 3:
                    per = tds[0]
                    med = _conv_float(tds[1])
                    dp = _conv_float(tds[2])
                    if per:
                        mapa_curso[per] = (med, dp)

    if not mapa_ind:
        raise ErroUfc(
            CodigoErro.LAYOUT_MUDOU,
            "Tabela de evolução do IRA (Período, IRA-I, IRA-G) não encontrada.",
        )

    registros: list[RegistroIraSemestre] = []
    for per, (irai, irag) in mapa_ind.items():
        med, dp = mapa_curso.get(per, (None, None))
        registros.append(
            RegistroIraSemestre(
                periodo=per,
                ira_individual=irai,
                ira_geral=irag,
                media_curso=med,
                desvio_padrao_curso=dp,
            )
        )
    return ResultadoHistoricoIra(registros=registros)
