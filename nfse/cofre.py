"""Cofre de senhas: guarda a senha do certificado digital criptografada.

Como funciona
-------------
A senha nunca e gravada em texto puro. Ela e cifrada com AES-GCM usando uma
chave mestra de 256 bits que fica em ``dados/chave.key`` com permissao 600
(somente o dono le).

Se a variavel de ambiente ``NFSE_SENHA_MESTRE`` estiver definida, a chave passa
a ser derivada dessa senha (PBKDF2-HMAC-SHA256, 480.000 iteracoes) com o sal de
``dados/salt.bin``. Nesse modo nada utilizavel fica no disco: sem a senha mestra
as senhas dos certificados nao podem ser recuperadas.

Limite conhecido: no modo padrao (arquivo de chave), quem tiver acesso de
leitura ao diretorio ``dados/`` consegue decifrar as senhas. Use a senha mestra
em computadores compartilhados.
"""

from __future__ import annotations

import base64
import os
import secrets
import stat
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

VARIAVEL_SENHA_MESTRE = "NFSE_SENHA_MESTRE"
ITERACOES = 480_000
PREFIXO = "aesgcm:"


class ErroDeCofre(Exception):
    """Falha ao cifrar ou decifrar uma senha."""


def _restringir_permissao(caminho: Path) -> None:
    """Deixa o arquivo legivel apenas pelo dono (silencioso no Windows)."""
    try:
        os.chmod(caminho, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


class Cofre:
    """Cifra e decifra as senhas dos certificados."""

    def __init__(self, diretorio: str | Path, senha_mestre: str | None = None):
        self.diretorio = Path(diretorio)
        self.diretorio.mkdir(parents=True, exist_ok=True)
        self.arquivo_chave = self.diretorio / "chave.key"
        self.arquivo_salt = self.diretorio / "salt.bin"
        self._senha_mestre = senha_mestre or os.environ.get(VARIAVEL_SENHA_MESTRE) or None
        self._chave: bytes | None = None

    # ----------------------------------------------------------------- #
    @property
    def usa_senha_mestre(self) -> bool:
        return self._senha_mestre is not None

    def _salt(self) -> bytes:
        if not self.arquivo_salt.exists():
            self.arquivo_salt.write_bytes(secrets.token_bytes(16))
            _restringir_permissao(self.arquivo_salt)
        return self.arquivo_salt.read_bytes()

    def _obter_chave(self) -> bytes:
        if self._chave is not None:
            return self._chave

        if self.usa_senha_mestre:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=self._salt(),
                iterations=ITERACOES,
            )
            self._chave = kdf.derive(self._senha_mestre.encode("utf-8"))
        else:
            if self.arquivo_chave.exists():
                self._chave = base64.urlsafe_b64decode(self.arquivo_chave.read_bytes())
            else:
                self._chave = AESGCM.generate_key(bit_length=256)
                self.arquivo_chave.write_bytes(base64.urlsafe_b64encode(self._chave))
                _restringir_permissao(self.arquivo_chave)
        return self._chave

    # ----------------------------------------------------------------- #
    def cifrar(self, senha: str) -> str:
        """Devolve a senha cifrada, pronta para gravar no cadastro."""
        if senha is None:
            senha = ""
        nonce = secrets.token_bytes(12)
        bruto = AESGCM(self._obter_chave()).encrypt(nonce, senha.encode("utf-8"), None)
        return PREFIXO + base64.b64encode(nonce + bruto).decode("ascii")

    def decifrar(self, valor: str) -> str:
        """Recupera a senha original a partir do texto cifrado."""
        if not valor:
            return ""
        if not valor.startswith(PREFIXO):
            # Cadastro antigo gravado em texto puro: aceita e segue.
            return valor
        try:
            bruto = base64.b64decode(valor[len(PREFIXO):])
            nonce, corpo = bruto[:12], bruto[12:]
            return AESGCM(self._obter_chave()).decrypt(nonce, corpo, None).decode("utf-8")
        except Exception as exc:  # noqa: BLE001 - qualquer falha e erro de chave
            motivo = ("a senha mestre esta incorreta"
                      if self.usa_senha_mestre
                      else f"o arquivo {self.arquivo_chave.name} nao confere")
            raise ErroDeCofre(
                f"Nao foi possivel recuperar a senha do certificado: {motivo}. "
                "Cadastre a senha novamente."
            ) from exc

    def esta_cifrado(self, valor: str) -> bool:
        return bool(valor) and valor.startswith(PREFIXO)
