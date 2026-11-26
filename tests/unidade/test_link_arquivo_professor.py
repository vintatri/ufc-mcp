from ufc_mcp.nucleo.sessao_sigaa import _achar_link_arquivo_professor


def test_acha_link_do_arquivo_do_professor() -> None:
    html = (
        b'<html><body><a href="/sigaa/outra">x</a>'
        b'<a href="/sigaa/verFoto?idArquivo=123&key=abc">Arquivo do Professor</a>'
        b"</body></html>"
    )
    assert _achar_link_arquivo_professor(html) == "/sigaa/verFoto?idArquivo=123&key=abc"


def test_sem_link_devolve_none() -> None:
    assert _achar_link_arquivo_professor(b"<html><a href='/sigaa/outra'>x</a></html>") is None


def test_ignora_verfoto_sem_id_de_arquivo() -> None:
    assert _achar_link_arquivo_professor(b"<a href='/sigaa/verFoto?idFoto=9'>f</a>") is None
