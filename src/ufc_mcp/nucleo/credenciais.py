"""Arquitetura Tripla de Cofre de Credenciais: CofreSistema, CofreSessao e CofreArquivo."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ufc_mcp.nucleo.erros import CodigoErro, ErroUfc
from ufc_mcp.nucleo.modelos_base import BaseModel, Field

CABECALHO_COFRE_ARQUIVO = b"UFCMCP1"
AAD_COFRE_ARQUIVO = b"ufc-mcp cofre v1"
SERVICO_KEYRING = "ufc-mcp"
CHAVE_CRED_KEYRING = "sigaa"
CHAVE_SESSAO_KEYRING = "sigaa-sessao"


class Credencial(BaseModel):
    """Credencial de login do estudante (nunca exposta fora de nucleo/)."""

    usuario: str
    senha: str = Field(repr=False)  # fora de repr/str: não vaza em traceback nem em log


class SessaoGuardada(BaseModel):
    """Cookies temporários de sessão para o modo --so-sessao (Zero Senha Persistente)."""

    cookies: dict[str, str] = Field(repr=False)
    criada_em: str = Field(
        default_factory=lambda: datetime.now(UTC).replace(microsecond=0).isoformat()
    )


def _derivar_chave_argon2id(frase_mestra: str, salt: bytes) -> bytes:
    """
    Deriva chave de 32 bytes com Argon2id (64 MiB, time_cost=3, parallelism=1).
    Se argon2-cffi não estiver instalado no ambiente de teste isolado, usa scrypt equivalente.
    """
    try:
        from argon2.low_level import Type, hash_secret_raw

        return bytes(
            hash_secret_raw(
                secret=frase_mestra.encode("utf-8"),
                salt=salt,
                time_cost=3,
                memory_cost=65536,
                parallelism=1,
                hash_len=32,
                type=Type.ID,
            )
        )
    except ImportError:
        return hashlib.scrypt(
            frase_mestra.encode("utf-8"),
            salt=salt,
            n=16384,
            r=8,
            p=1,
            maxmem=67108864,
            dklen=32,
        )


def _gravar_privado(caminho: Path, dados: bytes) -> None:
    """Grava o arquivo já criado com permissão 0600 (sem janela de leitura por outros usuários)."""
    fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(dados)
    os.chmod(caminho, 0o600)


def _validar_backend_keyring(kr: Any) -> None:
    modulo = kr.__class__.__module__
    nome_classe = kr.__class__.__name__
    if (
        modulo.startswith("keyrings.alt")
        or "Fail" in nome_classe
        or "Null" in nome_classe
        or "Plaintext" in nome_classe
    ):
        raise ErroUfc(
            CodigoErro.COFRE_INDISPONIVEL,
            f"Backend de keyring inseguro ou indisponível ({modulo}.{nome_classe}).",
        )


@contextlib.contextmanager
def _traduzir_erros_keyring() -> Iterator[None]:
    """Converte erros do pacote `keyring` (ex.: NoKeyringError) em COFRE_INDISPONIVEL."""
    try:
        yield
    except ErroUfc:
        raise
    except Exception as exc:
        if exc.__class__.__module__.startswith("keyring"):
            raise ErroUfc(
                CodigoErro.COFRE_INDISPONIVEL,
                "Chaveiro do sistema indisponível (sem backend). "
                "Use `--so-sessao` ou o cofre em arquivo criptografado.",
            ) from exc
        raise


class Cofre(Protocol):
    """Protocolo comum das 3 implementações de cofre."""

    def descricao(self) -> str: ...
    def estado(self) -> str: ...
    def salvar_credencial(self, cred: Credencial) -> None: ...
    def obter_credencial(self) -> Credencial | None: ...
    def salvar_sessao(self, sessao: SessaoGuardada) -> None: ...
    def obter_sessao(self) -> SessaoGuardada | None: ...
    def limpar(self) -> None: ...


class CofreSistema:
    """Armazena credencial no chaveiro nativo do SO (SecretService/KWallet/Keychain/WinVault)."""

    def __init__(self, backend_keyring: Any | None = None) -> None:
        self._kr = backend_keyring

    def _obter_kr(self) -> Any:
        if self._kr is not None:
            _validar_backend_keyring(self._kr)
            return self._kr
        try:
            import keyring

            kr = keyring.get_keyring()
        except ImportError as exc:
            raise ErroUfc(
                CodigoErro.COFRE_INDISPONIVEL,
                "Biblioteca `keyring` não disponível neste ambiente.",
            ) from exc
        _validar_backend_keyring(kr)
        return kr

    def descricao(self) -> str:
        return "CofreSistema (Chaveiro nativo do Sistema Operacional)"

    def estado(self) -> str:
        try:
            if self.obter_credencial() is not None:
                return "guardada"
            if self.obter_sessao() is not None:
                return "so_sessao"
        except ErroUfc as exc:
            if exc.codigo == CodigoErro.COFRE_INDISPONIVEL:
                return "chaveiro_indisponivel"
            return "ausente"
        return "ausente"

    def salvar_credencial(self, cred: Credencial) -> None:
        kr = self._obter_kr()
        with _traduzir_erros_keyring():
            kr.set_password(SERVICO_KEYRING, CHAVE_CRED_KEYRING, cred.model_dump_json())

    def obter_credencial(self) -> Credencial | None:
        kr = self._obter_kr()
        with _traduzir_erros_keyring():
            bruto = kr.get_password(SERVICO_KEYRING, CHAVE_CRED_KEYRING)
        if not bruto:
            return None
        dados = json.loads(bruto)
        return Credencial.model_validate(dados)

    def salvar_sessao(self, sessao: SessaoGuardada) -> None:
        kr = self._obter_kr()
        with _traduzir_erros_keyring():
            kr.set_password(SERVICO_KEYRING, CHAVE_SESSAO_KEYRING, sessao.model_dump_json())

    def obter_sessao(self) -> SessaoGuardada | None:
        kr = self._obter_kr()
        with _traduzir_erros_keyring():
            bruto = kr.get_password(SERVICO_KEYRING, CHAVE_SESSAO_KEYRING)
        if not bruto:
            return None
        return SessaoGuardada.model_validate(json.loads(bruto))

    def limpar(self) -> None:
        kr = self._obter_kr()
        for chave in (CHAVE_CRED_KEYRING, CHAVE_SESSAO_KEYRING):
            with contextlib.suppress(Exception):
                kr.delete_password(SERVICO_KEYRING, chave)


class CofreSessao:
    """
    Modo --so-sessao (Decisão D5): descarta a senha imediatamente após autenticar
    e armazena apenas os cookies temporários da sessão (1h30).
    """

    def __init__(
        self,
        backend_keyring: Any | None = None,
        arquivo_sessao_fallback: Path | None = None,
    ) -> None:
        self._kr = backend_keyring
        self._arquivo_fallback = arquivo_sessao_fallback
        self._memoria: SessaoGuardada | None = None

    def descricao(self) -> str:
        return "CofreSessao (Modo --so-sessao: zero senha persistente)"

    def estado(self) -> str:
        return "so_sessao" if self.obter_sessao() is not None else "ausente"

    def salvar_credencial(self, cred: Credencial) -> None:
        raise ErroUfc(
            CodigoErro.ACAO_BLOQUEADA,
            "CofreSessao (--so-sessao) jamais persiste senhas.",
        )

    def obter_credencial(self) -> Credencial | None:
        return None

    def salvar_sessao(self, sessao: SessaoGuardada) -> None:
        self._memoria = sessao
        if self._kr is not None:
            _validar_backend_keyring(self._kr)
            self._kr.set_password(
                SERVICO_KEYRING, CHAVE_SESSAO_KEYRING, sessao.model_dump_json()
            )
        elif self._arquivo_fallback is not None:
            self._arquivo_fallback.parent.mkdir(parents=True, exist_ok=True)
            _gravar_privado(self._arquivo_fallback, sessao.model_dump_json().encode("utf-8"))

    def obter_sessao(self) -> SessaoGuardada | None:
        if self._memoria is not None:
            return self._memoria
        if self._kr is not None:
            _validar_backend_keyring(self._kr)
            bruto = self._kr.get_password(SERVICO_KEYRING, CHAVE_SESSAO_KEYRING)
            if bruto:
                self._memoria = SessaoGuardada.model_validate(json.loads(bruto))
                return self._memoria
        if self._arquivo_fallback is not None and self._arquivo_fallback.exists():
            bruto = self._arquivo_fallback.read_text(encoding="utf-8")
            self._memoria = SessaoGuardada.model_validate(json.loads(bruto))
            return self._memoria
        return None

    def limpar(self) -> None:
        self._memoria = None
        if self._kr is not None:
            with contextlib.suppress(Exception):
                self._kr.delete_password(SERVICO_KEYRING, CHAVE_SESSAO_KEYRING)
        if self._arquivo_fallback is not None and self._arquivo_fallback.exists():
            self._arquivo_fallback.unlink()


class CofreArquivo:
    """
    Cofre criptografado em disco (`cofre.bin`, permissão 0600) usando
    Argon2id (64 MiB, t=3) + AES-256-GCM com cabeçalho `UFCMCP1`.
    """

    def __init__(self, caminho_arquivo: Path, frase_mestra: str) -> None:
        if not frase_mestra or len(frase_mestra) < 4:
            raise ErroUfc(
                CodigoErro.PARAMETRO_INVALIDO,
                "A frase-mestra do CofreArquivo deve possuir pelo menos 4 caracteres.",
            )
        self.caminho_arquivo = caminho_arquivo
        self._frase_mestra = frase_mestra

    def descricao(self) -> str:
        return "CofreArquivo (AES-256-GCM + Argon2id, permissão 0600)"

    def estado(self) -> str:
        if not self.caminho_arquivo.exists():
            return "ausente"
        dados = self._ler_payload()
        if "usuario" in dados and "senha" in dados:
            return "guardada"
        if "cookies" in dados:
            return "so_sessao"
        return "ausente"

    def _gravar_payload(self, payload: dict[str, Any]) -> None:
        self.caminho_arquivo.parent.mkdir(parents=True, exist_ok=True)
        salt = os.urandom(16)
        nonce = os.urandom(12)
        chave = _derivar_chave_argon2id(self._frase_mestra, salt)
        aes = AESGCM(chave)
        texto_json = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        cifrado = aes.encrypt(nonce, texto_json, AAD_COFRE_ARQUIVO)
        blob = CABECALHO_COFRE_ARQUIVO + salt + nonce + cifrado
        _gravar_privado(self.caminho_arquivo, blob)

    def _ler_payload(self) -> dict[str, Any]:
        if not self.caminho_arquivo.exists():
            return {}
        blob = self.caminho_arquivo.read_bytes()
        if len(blob) < 7 + 16 + 12 + 16 or not blob.startswith(CABECALHO_COFRE_ARQUIVO):
            raise ErroUfc(
                CodigoErro.COFRE_INDISPONIVEL,
                "Arquivo de cofre inválido ou corrompido (cabeçalho UFCMCP1 ausente).",
            )
        salt = blob[7:23]
        nonce = blob[23:35]
        cifrado = blob[35:]
        chave = _derivar_chave_argon2id(self._frase_mestra, salt)
        aes = AESGCM(chave)
        try:
            decifrado = aes.decrypt(nonce, cifrado, AAD_COFRE_ARQUIVO)
        except InvalidTag as exc:
            raise ErroUfc(
                CodigoErro.CREDENCIAL_INVALIDA,
                "Frase-mestra incorreta ou arquivo de cofre adulterado.",
            ) from exc
        res: dict[str, Any] = json.loads(decifrado.decode("utf-8"))
        return res

    def salvar_credencial(self, cred: Credencial) -> None:
        self._gravar_payload(cred.model_dump())

    def obter_credencial(self) -> Credencial | None:
        dados = self._ler_payload()
        if "usuario" in dados and "senha" in dados:
            return Credencial.model_validate(dados)
        return None

    def salvar_sessao(self, sessao: SessaoGuardada) -> None:
        self._gravar_payload(sessao.model_dump())

    def obter_sessao(self) -> SessaoGuardada | None:
        dados = self._ler_payload()
        if "cookies" in dados:
            return SessaoGuardada.model_validate(dados)
        return None

    def limpar(self) -> None:
        if self.caminho_arquivo.exists():
            self.caminho_arquivo.unlink()


class CofreComposto:
    """
    Cascata de cofres usada pelo servidor MCP.

    Permite que `login --so-sessao` (arquivo efêmero) e `login --cofre arquivo`
    continuem válidos em um processo `servir` separado, mesmo quando o chaveiro
    nativo do sistema operacional não possui backend disponível.
    """

    def __init__(self, cofres: Sequence[Cofre]) -> None:
        if not cofres:
            raise ErroUfc(
                CodigoErro.COFRE_INDISPONIVEL,
                "Nenhum cofre configurado para a cascata de credenciais.",
            )
        self._cofres: list[Cofre] = list(cofres)

    def descricao(self) -> str:
        return "CofreComposto (" + " + ".join(c.descricao() for c in self._cofres) + ")"

    def estado(self) -> str:
        indisponivel = False
        for cofre in self._cofres:
            try:
                estado = cofre.estado()
            except Exception:
                continue
            if estado in ("guardada", "so_sessao"):
                return estado
            if estado == "chaveiro_indisponivel":
                indisponivel = True
        return "chaveiro_indisponivel" if indisponivel else "ausente"

    @staticmethod
    def _ignorar_indisponivel(exc: ErroUfc) -> bool:
        return exc.codigo == CodigoErro.COFRE_INDISPONIVEL

    def salvar_credencial(self, cred: Credencial) -> None:
        ultimo: ErroUfc | None = None
        for cofre in self._cofres:
            try:
                cofre.salvar_credencial(cred)
                return
            except ErroUfc as exc:
                if not self._ignorar_indisponivel(exc):
                    raise
                ultimo = exc
        raise ultimo or ErroUfc(
            CodigoErro.COFRE_INDISPONIVEL,
            "Nenhum cofre conseguiu armazenar a credencial. "
            "Use `--so-sessao` ou configure `UFC_MCP_FRASE_MESTRA` para o cofre em arquivo.",
        )

    def obter_credencial(self) -> Credencial | None:
        ultimo: ErroUfc | None = None
        for cofre in self._cofres:
            try:
                cred = cofre.obter_credencial()
            except ErroUfc as exc:
                if not self._ignorar_indisponivel(exc):
                    raise
                ultimo = exc
                continue
            if cred is not None:
                return cred
        if ultimo is not None and self.estado() == "chaveiro_indisponivel":
            raise ultimo
        return None

    def salvar_sessao(self, sessao: SessaoGuardada) -> None:
        sucesso = False
        ultimo: ErroUfc | None = None
        for cofre in self._cofres:
            try:
                cofre.salvar_sessao(sessao)
                sucesso = True
            except ErroUfc as exc:
                if not self._ignorar_indisponivel(exc):
                    ultimo = exc
            except OSError as exc:
                ultimo = ErroUfc(
                    CodigoErro.COFRE_INDISPONIVEL,
                    f"Falha ao gravar sessão no cofre: {exc}",
                )
        if not sucesso and ultimo is not None:
            raise ultimo

    def obter_sessao(self) -> SessaoGuardada | None:
        ultimo: ErroUfc | None = None
        for cofre in self._cofres:
            try:
                sessao = cofre.obter_sessao()
            except ErroUfc as exc:
                if not self._ignorar_indisponivel(exc):
                    raise
                ultimo = exc
                continue
            if sessao is not None:
                return sessao
        if ultimo is not None and self.estado() == "chaveiro_indisponivel":
            raise ultimo
        return None

    def limpar(self) -> None:
        for cofre in self._cofres:
            with contextlib.suppress(Exception):
                cofre.limpar()


def cofre_padrao(pasta_config: Path) -> CofreComposto:
    """Monta a cascata padrão: arquivo (se houver frase-mestra), sistema e sessão efêmera."""
    cofres: list[Cofre] = []
    frase = os.environ.get("UFC_MCP_FRASE_MESTRA", "").strip()
    if frase:
        cofres.append(CofreArquivo(pasta_config / "cofre.bin", frase))
    cofres.append(CofreSistema())
    cofres.append(CofreSessao(arquivo_sessao_fallback=pasta_config / "sessao_efemera.json"))
    return CofreComposto(cofres)
