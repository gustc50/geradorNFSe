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


# Pontuacao "tipografica" que o Excel/Word colocam sozinhos -> equivalente ASCII.
_TROCAS_TIPOGRAFICAS = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u2032": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u2033": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u2010": "-", "\u2011": "-",
    "\u2026": "...", "\u2022": "-", "\u00a0": " ", "\u2009": " ", "\u200b": "",
    "\u20ac": "EUR", "\u2122": "TM", "\t": " ",
    "\u0141": "L", "\u0142": "l", "\u0152": "OE", "\u0153": "oe", "\u0110": "D", "\u0111": "d",
})


def texto_fiscal(valor, maximo: int | None = None, quebras: bool = False) -> str:
    """Texto aceito pelo schema da NFS-e (caracteres Latin-1, de '!' a 'y com trema').

    Troca aspas curvas, travessoes e reticencias pelo equivalente simples e
    descarta o que sobrar fora da faixa permitida (emojis, por exemplo).
    Com ``quebras=True`` mantem as quebras de linha (so a descricao do servico
    aceita); nos demais campos elas viram espaco.
    """
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    s = unicodedata.normalize("NFC", str(valor).translate(_TROCAS_TIPOGRAFICAS))
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    permitidos = []
    for c in s:
        if c == "\n":
            permitidos.append("\n" if quebras else " ")
        elif 0x20 <= ord(c) <= 0xFF and ord(c) not in range(0x7F, 0xA0):
            permitidos.append(c)
        else:
            decomposto = unicodedata.normalize("NFKD", c)
            permitidos.append("".join(x for x in decomposto if 0x20 <= ord(x) <= 0x7E))
    s = "".join(permitidos)
    if quebras:
        linhas = [re.sub(r"[ ]+", " ", linha).strip() for linha in s.split("\n")]
        s = "\n".join(linhas).strip("\n")
        s = re.sub(r"\n{3,}", "\n\n", s)
    else:
        s = re.sub(r"\s+", " ", s).strip()
    if maximo is not None and len(s) > maximo:
        s = s[:maximo].rstrip()
    return s


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


def percentual(valor) -> str:
    """Formata aliquotas com exatamente 2 casas decimais: 2 -> "2.00".

    O schema oficial (TSDec1V2 / TSDec2V2) recusa "2.5" e "0.6500": a aliquota
    precisa ser um inteiro sozinho ou ter exatamente duas casas.
    """
    d = decimal(valor, Decimal("0"))
    return str(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


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
        # Celula do Excel so com data chega como datetime a meia-noite.
        if dt.tzinfo is None and dt.time() == time(0, 0):
            dt = datetime.combine(dt.date(), agora().time().replace(tzinfo=None))
    elif isinstance(valor, date):
        dt = datetime.combine(valor, agora().time().replace(tzinfo=None))
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
            # So a data foi informada: usa a hora atual DE BRASILIA, nunca a do
            # relogio local - senao, num computador em outro fuso, a nota de hoje
            # poderia sair com horario no futuro e ser recusada pelo Portal.
            dt = datetime.combine(d, agora().time().replace(tzinfo=None))
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
