"""Leitura do certificado digital A1 (.pfx / .p12).

Responsabilidades:
  * abrir o arquivo com a senha e extrair chave privada, certificado e cadeia;
  * informar titular, CNPJ e validade (usados na tela de cadastro);
  * exportar um par PEM temporario para a conexao mTLS com a API do Portal
    Nacional - os arquivos nascem com permissao 600 e sao apagados no final.
"""

from __future__ import annotations

import contextlib
import os
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12

from . import util

# OIDs usados pela ICP-Brasil para guardar CNPJ/CPF do titular.
OID_CNPJ_PESSOA_JURIDICA = "2.16.76.1.3.3"
OID_CPF_PESSOA_FISICA = "2.16.76.1.3.1"


class ErroDeCertificado(Exception):
    """Certificado ausente, senha incorreta ou arquivo invalido."""


@dataclass
class InfoCertificado:
    """Dados do certificado + material criptografico carregado."""

    titular: str
    documento: str
    validade_inicio: datetime
    validade_fim: datetime
    emissor: str
    numero_serie: str
    chave_privada: object = None
    certificado: x509.Certificate = None
    cadeia: list = None
    arquivo: str = ""

    @property
    def vencido(self) -> bool:
        return datetime.now(timezone.utc) > self.validade_fim

    @property
    def dias_para_vencer(self) -> int:
        return (self.validade_fim - datetime.now(timezone.utc)).days

    def resumo(self) -> str:
        situacao = ("VENCIDO" if self.vencido
                    else f"valido por mais {self.dias_para_vencer} dia(s)")
        doc = util.formatar_documento(self.documento) if self.documento else "-"
        return (f"{self.titular} | {doc} | vence em "
                f"{self.validade_fim.astimezone(util.FUSO_BRASILIA):%d/%m/%Y} ({situacao})")


def _validade(certificado: x509.Certificate) -> tuple[datetime, datetime]:
    """Inicio e fim da validade, sempre com fuso UTC.

    Os atributos ``not_valid_*_utc`` existem a partir do cryptography 42; em
    versoes anteriores usamos os antigos, que vem sem fuso.
    """
    try:
        return certificado.not_valid_before_utc, certificado.not_valid_after_utc
    except AttributeError:
        inicio = certificado.not_valid_before
        fim = certificado.not_valid_after
        if inicio.tzinfo is None:
            inicio = inicio.replace(tzinfo=timezone.utc)
        if fim.tzinfo is None:
            fim = fim.replace(tzinfo=timezone.utc)
        return inicio, fim


def _extrair_documento(certificado: x509.Certificate) -> str:
    """Procura o CNPJ/CPF do titular no certificado ICP-Brasil."""
    # 1) otherName do subjectAltName (formato oficial da ICP-Brasil)
    try:
        san = certificado.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        for nome in san.value:
            if isinstance(nome, x509.OtherName):
                oid = nome.type_id.dotted_string
                if oid in (OID_CNPJ_PESSOA_JURIDICA, OID_CPF_PESSOA_FISICA):
                    bruto = nome.value.decode("latin-1", errors="ignore")
                    digitos = util.so_digitos(bruto)
                    if oid == OID_CNPJ_PESSOA_JURIDICA and len(digitos) >= 14:
                        return digitos[-14:]
                    if oid == OID_CPF_PESSOA_FISICA and len(digitos) >= 11:
                        # O campo traz data de nascimento + CPF + NIS + RG.
                        return digitos[8:19] if len(digitos) > 11 else digitos
    except x509.ExtensionNotFound:
        pass

    # 2) Common Name no formato "RAZAO SOCIAL LTDA:12345678000199"
    try:
        cn = certificado.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value
    except (IndexError, ValueError):
        return ""
    if ":" in cn:
        digitos = util.so_digitos(cn.rsplit(":", 1)[1])
        if len(digitos) in (11, 14):
            return digitos
    return ""


def _nome_titular(certificado: x509.Certificate) -> str:
    try:
        cn = certificado.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value
    except (IndexError, ValueError):
        return ""
    return cn.rsplit(":", 1)[0].strip() if ":" in cn else cn.strip()


def _nome_emissor(certificado: x509.Certificate) -> str:
    try:
        return certificado.issuer.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value
    except (IndexError, ValueError):
        return ""


def ler_certificado(arquivo: str | Path, senha: str) -> InfoCertificado:
    """Abre o .pfx e devolve os dados + material criptografico."""
    caminho = Path(arquivo).expanduser()
    if not caminho.exists():
        raise ErroDeCertificado(f"Certificado nao encontrado: {caminho}")

    conteudo = caminho.read_bytes()
    senha_bytes = (senha or "").encode("utf-8") or None
    try:
        chave, certificado, cadeia = pkcs12.load_key_and_certificates(conteudo, senha_bytes)
    except Exception as exc:  # noqa: BLE001 - a lib levanta varios tipos
        detalhe = str(exc).lower()
        if "mac" in detalhe or "invalid password" in detalhe or "incorrect" in detalhe:
            raise ErroDeCertificado(
                f"Senha incorreta para o certificado {caminho.name}.") from exc
        if "unsupported" in detalhe or "algorithm" in detalhe or "rc2" in detalhe:
            raise ErroDeCertificado(
                f"O certificado {caminho.name} usa criptografia antiga (RC2/legacy) que a "
                "biblioteca nao abre. Converta com:\n"
                "  openssl pkcs12 -legacy -in antigo.pfx -nodes -out temp.pem\n"
                "  openssl pkcs12 -export -in temp.pem -out novo.pfx"
            ) from exc
        raise ErroDeCertificado(
            f"Nao foi possivel abrir o certificado {caminho.name}: {exc}") from exc

    if chave is None or certificado is None:
        raise ErroDeCertificado(
            f"O arquivo {caminho.name} nao contem chave privada e certificado. "
            "Use um certificado A1 (.pfx/.p12) com a chave exportavel.")

    inicio, fim = _validade(certificado)
    return InfoCertificado(
        titular=_nome_titular(certificado),
        documento=_extrair_documento(certificado),
        validade_inicio=inicio,
        validade_fim=fim,
        emissor=_nome_emissor(certificado),
        numero_serie=format(certificado.serial_number, "X"),
        chave_privada=chave,
        certificado=certificado,
        cadeia=list(cadeia or []),
        arquivo=str(caminho),
    )


def impressao_digital(certificado: x509.Certificate) -> str:
    return certificado.fingerprint(hashes.SHA1()).hex().upper()


@contextlib.contextmanager
def par_pem_temporario(info: InfoCertificado):
    """Gera (arquivo_cert, arquivo_chave) em PEM para o mTLS do ``requests``.

    Os arquivos ficam num diretorio temporario exclusivo com permissao 600 e sao
    removidos ao sair do bloco ``with``.
    """
    pasta = Path(tempfile.mkdtemp(prefix="nfse_cert_"))
    try:
        os.chmod(pasta, stat.S_IRWXU)
    except OSError:
        pass

    arquivo_cert = pasta / "cliente.pem"
    arquivo_chave = pasta / "cliente.key"
    try:
        blocos = [info.certificado.public_bytes(serialization.Encoding.PEM)]
        for intermediario in info.cadeia or []:
            blocos.append(intermediario.public_bytes(serialization.Encoding.PEM))
        arquivo_cert.write_bytes(b"".join(blocos))
        arquivo_chave.write_bytes(info.chave_privada.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        for arq in (arquivo_cert, arquivo_chave):
            try:
                os.chmod(arq, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
        yield str(arquivo_cert), str(arquivo_chave)
    finally:
        for arq in (arquivo_cert, arquivo_chave):
            try:
                if arq.exists():
                    arq.write_bytes(b"\0" * max(1, arq.stat().st_size))
                    arq.unlink()
            except OSError:
                pass
        try:
            pasta.rmdir()
        except OSError:
            pass
