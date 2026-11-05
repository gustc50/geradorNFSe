"""Tributos aproximados conforme o regime do prestador (regras E0712 / E0710).

Recusa real recebida em homologacao (nov/2026), empresa ME/EPP do Simples:
  [E0712] Para ME/EPP o indicador de informacao de valor total de tributos nao
  pode ser informado.
"""

from decimal import Decimal as D
from pathlib import Path

import pytest
from lxml import etree

from nfse import dps, esquema, tabelas
from nfse.assinatura import assinar_xml

PASTA = Path(__file__).resolve().parent.parent / "schemas"


def tot_trib(xml):
    bloco = etree.fromstring(xml).find(".//{*}totTrib")
    return [(etree.QName(e).localname, e.text) for e in bloco]


@pytest.fixture
def me_epp(empresa):
    empresa.optante_simples, empresa.regime_apuracao_sn = "3", "1"
    empresa.percentual_simples = "6"
    return empresa


def test_me_epp_manda_o_percentual_do_simples_e_nao_o_indicador(nota, me_epp):
    xml, _ = dps.montar_xml(nota, me_epp)
    assert tot_trib(xml) == [("pTotTribSN", "6.00")]
    assert b"indTotTrib" not in xml


def test_percentual_da_planilha_vence_o_do_cadastro(nota, me_epp):
    nota.percentual_simples = D("11.2")
    xml, _ = dps.montar_xml(nota, me_epp)
    assert tot_trib(xml) == [("pTotTribSN", "11.20")]


def test_me_epp_sem_percentual_e_barrada_antes_do_envio(nota, me_epp):
    me_epp.percentual_simples = ""
    problemas = dps.validar(nota, me_epp)
    assert any("% tributos do Simples" in p for p in problemas)


def test_me_epp_com_valores_detalhados_dispensa_o_percentual(nota, me_epp):
    me_epp.percentual_simples = ""
    nota.tributos_federais = D("50")
    assert dps.validar(nota, me_epp) == []
    xml, _ = dps.montar_xml(nota, me_epp)
    assert tot_trib(xml)[0][0] == "vTotTrib"


def test_percentual_fora_da_faixa(nota, me_epp):
    me_epp.percentual_simples = "150"
    assert any("0 e 99,99" in p for p in dps.validar(nota, me_epp))
    assert any("Simples" in p for p in me_epp.validar())


def test_mei_nunca_manda_o_percentual_do_simples(nota, empresa):
    """Regra inversa (E0710): MEI nao pode informar pTotTribSN."""
    empresa.optante_simples = "2"
    empresa.percentual_simples = "6"
    nota.percentual_simples = D("6")
    xml, _ = dps.montar_xml(nota, empresa)
    assert tot_trib(xml) == [("indTotTrib", "0")]


def test_nao_optante_continua_igual(nota, empresa):
    xml, _ = dps.montar_xml(nota, empresa)
    assert tot_trib(xml) == [("indTotTrib", "0")]


@pytest.mark.parametrize("layout", [tabelas.LAYOUT_ANTERIOR, tabelas.LAYOUT_NT009])
def test_percentual_do_simples_passa_no_schema(layout, nota, me_epp, certificado):
    xml, identificador = dps.montar_xml(nota, me_epp, layout=layout)
    assinado = assinar_xml(xml, identificador, certificado)
    assert esquema.validar(assinado, "DPS", pasta=PASTA / layout) == []


def test_coluna_da_planilha_e_lida(planilha_modelo):
    from openpyxl import load_workbook
    from nfse import modelo_planilha, planilha
    livro = load_workbook(planilha_modelo)
    folha = livro["EMPRESA EXEMPLO"]
    mapa = {c.value: c.column for c in folha[modelo_planilha.LINHA_TITULOS]}
    for titulo, valor in {"Tipo doc. tomador": "CNPJ", "CNPJ/CPF do tomador": "11444777000161",
                          "Nome/Razao social do tomador": "X", "Cod. tributacao nacional": "040101",
                          "Descricao do servico": "Exame", "Valor do servico": 100,
                          "% tributos Simples Nacional": "6,5"}.items():
        folha.cell(row=4, column=mapa[titulo]).value = valor
    livro.save(planilha_modelo)
    assert planilha.ler(planilha_modelo)["EMPRESA EXEMPLO"].notas[0].percentual_simples == D("6.5")
