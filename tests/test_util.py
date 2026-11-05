"""Conversao de numeros, datas e documentos."""

from datetime import date
from decimal import Decimal

import pytest

from nfse import util


@pytest.mark.parametrize("entrada,esperado", [
    ("1.234,56", Decimal("1234.56")),
    ("1234,56", Decimal("1234.56")),
    ("1234.56", Decimal("1234.56")),
    ("1,234.56", Decimal("1234.56")),
    ("R$ 1.234,56", Decimal("1234.56")),
    ("-50,25", Decimal("-50.25")),
    (1000, Decimal("1000")),
    (1500.5, Decimal("1500.5")),
    ("", None),
    (None, None),
])
def test_decimal_aceita_formatos_brasileiro_e_americano(entrada, esperado):
    assert util.decimal(entrada) == esperado


def test_decimal_recusa_texto_invalido():
    with pytest.raises(util.ErroDeValidacao):
        util.decimal("mil reais")


def test_moeda_arredonda_para_duas_casas():
    assert util.moeda("1234,567") == "1234.57"
    assert util.moeda("1234,564") == "1234.56"
    assert util.moeda(None) == "0.00"


def test_percentual_sempre_com_duas_casas():
    """O schema recusa "2.5" e "0.6500": precisa ser "2.50" e "0.65"."""
    assert util.percentual("2") == "2.00"
    assert util.percentual("2,5") == "2.50"
    assert util.percentual("0,6500") == "0.65"
    assert util.percentual("7,6") == "7.60"


def test_texto_fiscal_troca_pontuacao_tipografica():
    assert util.texto_fiscal("“Aspas” – travessão… ok") == '"Aspas" - travessão... ok'


def test_texto_fiscal_remove_emoji_e_mantem_acentos():
    assert util.texto_fiscal("Pão de açúcar 🍞") == "Pão de açúcar"


def test_texto_fiscal_quebras_de_linha():
    assert util.texto_fiscal("a\r\nb") == "a b"
    assert util.texto_fiscal("a\r\nb", quebras=True) == "a\nb"


def test_texto_fiscal_respeita_tamanho_maximo():
    assert util.texto_fiscal("abcdef", maximo=3) == "abc"


@pytest.mark.parametrize("entrada,esperado", [
    ("15/01/2026", date(2026, 1, 15)),
    ("2026-01-15", date(2026, 1, 15)),
    ("01/2026", date(2026, 1, 1)),
])
def test_para_data(entrada, esperado):
    assert util.para_data(entrada) == esperado


def test_para_data_invalida():
    with pytest.raises(util.ErroDeValidacao):
        util.para_data("32/13/2026")


def test_datahora_sai_com_fuso_de_brasilia():
    assert util.datahora_xml(util.para_datahora("15/01/2026 10:30")).endswith("-03:00")


def test_validacao_de_documentos():
    assert util.cnpj_valido("11.222.333/0001-81")
    assert not util.cnpj_valido("11.222.333/0001-80")
    assert not util.cnpj_valido("11111111111111")
    assert util.cpf_valido("529.982.247-25")
    assert not util.cpf_valido("529.982.247-26")
    assert util.tipo_documento("11222333000181") == "CNPJ"
    assert util.tipo_documento("52998224725") == "CPF"


def test_normalizar_chave_remove_acentos_e_pontuacao():
    assert util.normalizar_chave("Descrição do Serviço") == "descricao_do_servico"
    assert util.normalizar_chave("CNPJ/CPF do tomador") == "cnpj_cpf_do_tomador"


def test_data_sem_hora_usa_horario_de_brasilia():
    """Data sem hora vira 'data + hora atual de Brasilia', nunca a hora local."""
    from datetime import datetime, timedelta
    agora = util.agora()
    dt = util.para_datahora(agora.strftime("%d/%m/%Y"))
    assert dt.utcoffset() == timedelta(hours=-3)
    assert abs((dt - agora).total_seconds()) < 5
    excel = util.para_datahora(datetime(agora.year, agora.month, agora.day))
    assert abs((excel - agora).total_seconds()) < 5
