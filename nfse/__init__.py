"""Gerador de NFS-e - Padrao Nacional (Sefin Nacional / ADN).

Modulos:
    util        - funcoes auxiliares (numeros, datas, documentos)
    tabelas     - tabelas de dominio e URLs dos ambientes
    cofre       - criptografia das senhas dos certificados
    config      - cadastro das empresas (uma aba por empresa)
    certificado - leitura do certificado A1 (.pfx/.p12)
    assinatura  - assinatura digital XMLDSig do DPS
    dps         - montagem do XML da DPS
    esquema     - validacao opcional contra o XSD oficial
    planilha    - leitura da planilha de notas
    modelo_planilha - geracao da planilha modelo
    api         - cliente HTTP da API do Portal Nacional
    emissor     - orquestracao da emissao em lote
"""

__version__ = "1.0.0"
__all__ = [
    "util",
    "tabelas",
    "cofre",
    "config",
    "certificado",
    "assinatura",
    "dps",
    "esquema",
    "planilha",
    "modelo_planilha",
    "api",
    "emissor",
]
