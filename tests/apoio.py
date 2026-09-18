"""Apoio aos testes: gera um certificado A1 falso, no formato ICP-Brasil.

O certificado e autoassinado e serve apenas para exercitar a leitura do .pfx e
a assinatura XML. Nunca substitui um certificado real na emissao.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

OID_CNPJ = x509.ObjectIdentifier("2.16.76.1.3.3")


def gerar_pfx(destino: str | Path,
              senha: str = "teste123",
              razao_social: str = "EMPRESA MODELO LTDA",
              cnpj: str = "11222333000181",
              dias_validade: int = 365) -> Path:
    """Cria um .pfx autoassinado com CN 'RAZAO:CNPJ' e SAN otherName."""
    destino = Path(destino)
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ICP-Brasil"),
        x509.NameAttribute(NameOID.COMMON_NAME, f"{razao_social}:{cnpj}"),
    ])
    agora = dt.datetime.now(dt.timezone.utc)
    # Um certificado ja vencido (dias_validade negativo) precisa comecar antes
    # de terminar: recua o inicio o suficiente.
    inicio = agora - dt.timedelta(days=1 if dias_validade >= 0 else abs(dias_validade) + 365)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
            x509.NameAttribute(NameOID.COMMON_NAME, "AC TESTE NFSE"),
        ]))
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(inicio)
        .not_valid_after(agora + dt.timedelta(days=dias_validade))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.OtherName(OID_CNPJ, b"\x04\x0e" + cnpj.encode("ascii")),
            ]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(chave, hashes.SHA256())
    )
    destino.write_bytes(pkcs12.serialize_key_and_certificates(
        name=b"teste",
        key=chave,
        cert=certificado,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(senha.encode()),
    ))
    return destino
