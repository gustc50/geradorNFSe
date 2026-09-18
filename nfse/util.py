"""Funcoes auxiliares: numeros, datas, documentos e textos."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

FUSO_BRASILIA = timezone(timedelta(hours=-3))

_RE_NAO_DIGITO = re.compile(r"\D")
_RE_ESPACOS = re.compile(r"\s+")


class ErroDeValidacao(Exception):
    """Erro de preenchimento detectado antes de enviar a nota."""


# --------------------------------------------------------------------------- #
# Texto
# --------------------------------------------------------------------------- #
def texto(valor, maximo: int | None = None) -> str:
    """Converte para string limpa (sem espacos duplicados nas pontas)."""
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    s = _RE_ESPACOS.sub(" ", str(valor)).strip()
    if maximo is not None and len(s) > maximo:
        s = s[:maximo].strip()
    return s


def normalizar_chave(valor) -> str:
    """Normaliza um titulo de coluna: minusculo, sem acento, com underscore."""
    s = texto(valor).lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def so_digitos(valor) -> str:
    return _RE_NAO_DIGITO.sub("", texto(valor))


def vazio(valor) -> bool:
    return texto(valor) == ""


# --------------------------------------------------------------------------- #
# Numeros
# --------------------------------------------------------------------------- #
def decimal(valor, padrao: Decimal | None = None) -> Decimal | None:
    """Converte para Decimal aceitando os formatos brasileiro e americano.

    Aceita 1234.56, "1.234,56", "1234,56", "R$ 1.234,56" e "1,234.56".
    """
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return padrao
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, (int,)) and not isinstance(valor, bool):
        return Decimal(valor)
    if isinstance(valor, float):
        return Decimal(str(valor))

    s = texto(valor).replace("R$", "").replace("%", "").replace(" ", "")
    s = s.replace(" ", "")
    if not s:
        return padrao
    negativo = s.startswith("-")
    s = s.lstrip("+-")

    if "," in s and "." in s:
        # O separador decimal e o ultimo simbolo que aparece.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")

    try:
        d = Decimal(s)
    except InvalidOperation as exc:
        raise ErroDeValidacao(f"Valor numerico invalido: {valor!r}") from exc
    return -d if negativo else d


def inteiro(valor, padrao: int | None = None) -> int | None:
    d = decimal(valor)
    if d is None:
        return padrao
    return int(d)


def moeda(valor) -> str:
    """Formata com 2 casas decimais, como exigido no XML."""
    d = decimal(valor, Decimal("0"))
    return str(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def percentual(valor, casas: int = 4) -> str:
    """Formata aliquotas com ate 4 casas decimais, sem zeros sobrando.

    2 -> "2", 2,5 -> "2.5", 0,6500 -> "0.65". O XSD aceita qualquer uma dessas
    formas; manter a mais curta deixa o XML legivel na conferencia.
    """
    d = decimal(valor, Decimal("0")).quantize(
        Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)
    formatado = format(d, "f")
    if "." in formatado:
        formatado = formatado.rstrip("0").rstrip(".")
    return formatado or "0"


def arredondar(valor, casas: int = 2) -> Decimal:
    d = decimal(valor, Decimal("0"))
    return d.quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- #
# Datas
# --------------------------------------------------------------------------- #
def para_data(valor, padrao: date | None = None) -> date | None:
    """Aceita date/datetime, 'dd/mm/aaaa', 'aaaa-mm-dd' e 'mm/aaaa'."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return padrao
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor

    s = texto(valor)
    formatos = ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%Y", "%Y/%m/%d")
    for fmt in formatos:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Competencia informada como mm/aaaa ou aaaa-mm
    for fmt in ("%m/%Y", "%Y-%m", "%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date().replace(day=1)
        except ValueError:
            continue
    raise ErroDeValidacao(f"Data invalida: {valor!r} (use dd/mm/aaaa)")


def para_datahora(valor, padrao: datetime | None = None) -> datetime | None:
    """Converte para datetime com fuso de Brasilia."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return padrao
    if isinstance(valor, datetime):
        dt = valor
    elif isinstance(valor, date):
        dt = datetime.combine(valor, time(0, 0))
    else:
        s = texto(valor)
        dt = None
        for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        if dt is None:
            d = para_data(s)
            dt = datetime.combine(d, datetime.now().time().replace(microsecond=0))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=FUSO_BRASILIA)
    return dt.replace(microsecond=0)


def agora() -> datetime:
    return datetime.now(FUSO_BRASILIA).replace(microsecond=0)


def data_xml(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def datahora_xml(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=FUSO_BRASILIA)
    return dt.replace(microsecond=0).isoformat()


# --------------------------------------------------------------------------- #
# Documentos
# --------------------------------------------------------------------------- #
def _digitos_verificadores(base: str, pesos: list[int]) -> int:
    soma = sum(int(d) * p for d, p in zip(base, pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def cnpj_valido(valor) -> bool:
    c = so_digitos(valor)
    if len(c) != 14 or c == c[0] * 14:
        return False
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    p2 = [6] + p1
    return (_digitos_verificadores(c[:12], p1) == int(c[12])
            and _digitos_verificadores(c[:13], p2) == int(c[13]))


def cpf_valido(valor) -> bool:
    c = so_digitos(valor)
    if len(c) != 11 or c == c[0] * 11:
        return False
    return (_digitos_verificadores(c[:9], list(range(10, 1, -1))) == int(c[9])
            and _digitos_verificadores(c[:10], list(range(11, 1, -1))) == int(c[10]))


def formatar_cnpj(valor) -> str:
    c = so_digitos(valor)
    if len(c) != 14:
        return texto(valor)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def formatar_cpf(valor) -> str:
    c = so_digitos(valor)
    if len(c) != 11:
        return texto(valor)
    return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"


def formatar_documento(valor) -> str:
    c = so_digitos(valor)
    if len(c) == 14:
        return formatar_cnpj(c)
    if len(c) == 11:
        return formatar_cpf(c)
    return texto(valor)


def tipo_documento(valor) -> str:
    """Retorna 'CNPJ', 'CPF' ou '' conforme a quantidade de digitos."""
    c = so_digitos(valor)
    if len(c) == 14:
        return "CNPJ"
    if len(c) == 11:
        return "CPF"
    return ""


def nome_arquivo_seguro(valor, padrao: str = "arquivo") -> str:
    """Transforma um nome qualquer em nome de arquivo seguro."""
    s = normalizar_chave(valor)
    return s or padrao
