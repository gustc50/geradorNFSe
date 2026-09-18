"""Validacao opcional do XML contra o schema oficial (XSD).

O Portal Nacional publica os arquivos ``.xsd`` do layout. Eles nao podem ser
redistribuidos aqui, mas se voce baixa-los e colocar na pasta ``schemas/``, o
sistema passa a conferir cada XML antes de enviar - os erros aparecem no log
com o nome do campo, em vez de virem como rejeicao do Portal.

Baixe em: https://www.gov.br/nfse  (area de documentacao tecnica / layout)
Coloque em: schemas/DPS_v1.00.xsd  (e os demais arquivos que vierem juntos)

Sem os arquivos, a validacao e simplesmente pulada.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

PASTA_PADRAO = Path(__file__).resolve().parent.parent / "schemas"
_cache: dict[str, etree.XMLSchema | None] = {}


class ErroDeEsquema(Exception):
    """O XML nao bate com o schema oficial."""


def localizar(nome_base: str, pasta: str | Path | None = None) -> Path | None:
    """Procura um XSD cujo nome comece por ``nome_base`` (ex.: 'DPS')."""
    diretorio = Path(pasta or PASTA_PADRAO)
    if not diretorio.is_dir():
        return None
    candidatos = sorted(diretorio.glob(f"{nome_base}*.xsd"))
    return candidatos[0] if candidatos else None


def carregar(nome_base: str, pasta: str | Path | None = None) -> etree.XMLSchema | None:
    """Carrega o schema uma vez e guarda em memoria. None quando nao existe."""
    chave = f"{pasta or PASTA_PADRAO}|{nome_base}"
    if chave in _cache:
        return _cache[chave]

    arquivo = localizar(nome_base, pasta)
    esquema = None
    if arquivo is not None:
        try:
            esquema = etree.XMLSchema(etree.parse(str(arquivo)))
        except etree.XMLSyntaxError as exc:
            raise ErroDeEsquema(
                f"O arquivo {arquivo.name} nao pode ser lido como schema: {exc}") from exc
    _cache[chave] = esquema
    return esquema


def validar(xml: bytes, nome_base: str = "DPS",
            pasta: str | Path | None = None) -> list[str]:
    """Devolve a lista de erros do schema. Lista vazia = ok (ou sem XSD)."""
    esquema = carregar(nome_base, pasta)
    if esquema is None:
        return []
    documento = etree.fromstring(xml, parser=etree.XMLParser(
        resolve_entities=False, no_network=True))
    if esquema.validate(documento):
        return []
    return [f"linha {erro.line}: {erro.message}" for erro in esquema.error_log]


def limpar_cache() -> None:
    _cache.clear()
