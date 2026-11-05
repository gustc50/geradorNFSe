"""Validacao do XML contra o schema oficial (XSD) antes do envio.

A pasta ``schemas/`` ja vem com os XSD oficiais do layout nacional (v1.01).
Cada DPS e cada evento sao conferidos antes de ir ao Portal Nacional - os erros
aparecem no log com o nome do campo, em vez de virem como rejeicao.

Quando o Portal publicar uma versao nova, basta trocar os arquivos da pasta.
Sem arquivos, a validacao e pulada (o sistema continua funcionando).
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

PASTA_PADRAO = Path(__file__).resolve().parent.parent / "schemas"
_cache: dict[str, etree.XMLSchema | None] = {}


class ErroDeEsquema(Exception):
    """O XML nao bate com o schema oficial."""


def pasta_do_layout(layout: str | None) -> Path:
    """schemas/<layout>/ ; sem subpasta para o layout, usa schemas/ direto."""
    if layout:
        subpasta = PASTA_PADRAO / layout
        if subpasta.is_dir():
            return subpasta
    return PASTA_PADRAO


def localizar(nome_base: str, pasta: str | Path | None = None) -> Path | None:
    """Procura um XSD cujo nome comece por ``nome_base`` (ex.: 'DPS')."""
    diretorio = Path(pasta or PASTA_PADRAO)
    if not diretorio.is_dir():
        return None
    candidatos = sorted(diretorio.glob(f"{nome_base}_v*.xsd")) or sorted(
        diretorio.glob(f"{nome_base}*.xsd"))
    # Com varias versoes na pasta, vale a mais nova (ordem alfabetica: v1.01 > v1.00).
    return candidatos[-1] if candidatos else None


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
            pasta: str | Path | None = None, layout: str | None = None) -> list[str]:
    """Devolve a lista de erros do schema. Lista vazia = ok (ou sem XSD).

    ``layout`` escolhe a subpasta (schemas/anterior, schemas/nt009).
    """
    esquema = carregar(nome_base, pasta or pasta_do_layout(layout))
    if esquema is None:
        return []
    documento = etree.fromstring(xml, parser=etree.XMLParser(
        resolve_entities=False, no_network=True))
    if esquema.validate(documento):
        return []
    return [f"linha {erro.line}: {erro.message}" for erro in esquema.error_log]


def limpar_cache() -> None:
    _cache.clear()
