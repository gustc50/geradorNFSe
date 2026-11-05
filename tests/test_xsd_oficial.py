"""Todo XML gerado precisa passar no schema oficial (schemas/*.xsd).

Estes testes usam os XSD do layout nacional que acompanham o projeto: se o
sistema montar algum campo fora de ordem ou de formato, o Portal rejeitaria a
nota, e o teste falha antes disso.
"""

import copy
from decimal import Decimal as D
from pathlib import Path

import pytest
from lxml import etree

from nfse import dps, esquema
from nfse.assinatura import assinar_xml

PASTA = Path(__file__).resolve().parent.parent / "schemas"


@pytest.fixture(scope="module")
def xsd_dps():
    arquivo = esquema.localizar("DPS", PASTA)
    assert arquivo is not None, "os XSD oficiais devem estar em schemas/"
    return etree.XMLSchema(etree.parse(str(arquivo)))


@pytest.fixture(scope="module")
def xsd_evento():
    return etree.XMLSchema(etree.parse(str(esquema.localizar("pedRegEvento", PASTA))))


def _aplicar(objeto, alteracoes):
    copia = copy.deepcopy(objeto)
    for campo, valor in alteracoes.items():
        setattr(copia, campo, valor)
    return copia


SEM_ENDERECO = dict(tomador_cep="", tomador_codigo_municipio="", tomador_logradouro="",
                    tomador_numero="", tomador_bairro="")

CENARIOS_NOTA = {
    "basico": {},
    "tomador CPF sem endereco": dict(SEM_ENDERECO, tomador_tipo_documento="CPF",
                                     tomador_documento="52998224725"),
    "tomador nao identificado": dict(SEM_ENDERECO, tomador_tipo_documento="SEM",
                                     tomador_documento="", tomador_nome=""),
    "complemento, IM, e-mail e telefone": dict(
        tomador_complemento="Sala 12", tomador_inscricao_municipal="12.345-6",
        tomador_email="fin@cliente.com.br", tomador_telefone="(11) 99999-8888"),
    "ISS retido": dict(iss_retido="2", aliquota_iss=D("5")),
    "sem aliquota": dict(aliquota_iss=None),
    "aliquota fracionada": dict(aliquota_iss=D("2.5")),
    "aliquota zero": dict(aliquota_iss=D("0")),
    "descontos e deducoes": dict(desconto_incondicionado=D("100"),
                                 desconto_condicionado=D("50"), valor_deducoes=D("200")),
    "PIS/COFINS completo": dict(cst_pis_cofins="01", retencao_pis_cofins="3",
                                base_pis_cofins=D("1500"), aliquota_pis=D("0.65"),
                                aliquota_cofins=D("3"), valor_pis=D("9.75"),
                                valor_cofins=D("45")),
    "PIS/COFINS so CST": dict(cst_pis_cofins="50"),
    "aliquotas PIS/COFINS nao cumulativas": dict(cst_pis_cofins="01",
                                                 aliquota_pis=D("1.65"),
                                                 aliquota_cofins=D("7.6")),
    "IRRF CSLL INSS": dict(valor_irrf=D("22.5"), valor_csll=D("15"), valor_inss=D("165")),
    "tributos aproximados": dict(tributos_federais=D("120"), tributos_municipais=D("30")),
    "codigos opcionais": dict(codigo_tributacao_municipal="123", codigo_nbs="1.1502.20.00",
                              numero_interno="PED-77/A"),
    "informacoes complementares em varias linhas": dict(
        informacoes_complementares="Contrato 15/2026\nVencimento 10/02"),
    "municipio de prestacao diferente": dict(codigo_municipio_prestacao="3304557"),
    "nao incidencia": dict(tributacao_issqn="3", aliquota_iss=None),
    "imunidade": dict(tributacao_issqn="4", tipo_imunidade="2", aliquota_iss=None),
    "exportacao com tomador no exterior": dict(
        tomador_tipo_documento="NIF", tomador_documento="US123456", tomador_codigo_pais="us",
        tomador_cidade_exterior="Miami", tomador_estado_exterior="FL",
        tomador_cep_exterior="33101", tomador_cep="", tomador_codigo_municipio="",
        tributacao_issqn="2", codigo_pais_resultado="US", aliquota_iss=None),
    "servico prestado no exterior": dict(codigo_pais_prestacao="PT"),
    "serie e numero no limite": dict(serie="99999", numero=999999999999999),
    "descricao longa com quebras": dict(descricao_servico=("Linha de servico\n" * 200)),
    "texto colado do Word/Excel": dict(
        tomador_nome="Padaria “Pão Quente” – Filial Łódź 🍞",
        descricao_servico="Serviço “premium”… ref. 01/2026 — pago ✅",
        tomador_logradouro="Rua São João\t\t nº 10",
        informacoes_complementares="Obs.: “urgente” • ligar antes"),
}

CENARIOS_EMPRESA = {
    "Simples ME/EPP": dict(optante_simples="3", regime_apuracao_sn="1"),
    "MEI": dict(optante_simples="2"),
    "regime especial outros": dict(regime_especial="9"),
    "prestador pessoa fisica": dict(cnpj="52998224725"),
    "producao": dict(ambiente="producao"),
    "empresa com e-mail e telefone": dict(email="fiscal@empresa.com.br",
                                          telefone="(11) 3333-4444"),
}


@pytest.mark.parametrize("nome", list(CENARIOS_NOTA))
def test_nota_passa_no_schema_oficial(nome, nota, empresa, certificado, xsd_dps):
    variante = _aplicar(nota, CENARIOS_NOTA[nome])
    xml, identificador = dps.montar_xml(variante, empresa)
    documento = etree.fromstring(assinar_xml(xml, identificador, certificado))
    assert xsd_dps.validate(documento), "\n".join(e.message for e in xsd_dps.error_log)


@pytest.mark.parametrize("nome", list(CENARIOS_EMPRESA))
def test_empresa_passa_no_schema_oficial(nome, nota, empresa, certificado, xsd_dps):
    variante = _aplicar(empresa, CENARIOS_EMPRESA[nome])
    xml, identificador = dps.montar_xml(nota, variante)
    documento = etree.fromstring(assinar_xml(xml, identificador, certificado))
    assert xsd_dps.validate(documento), "\n".join(e.message for e in xsd_dps.error_log)


@pytest.mark.parametrize("codigo", ["1", "2", "9"])
def test_evento_de_cancelamento_passa_no_schema(codigo, empresa, certificado, xsd_evento):
    xml, identificador = dps.montar_evento_cancelamento(
        empresa, "3" * 50, codigo, "Valor do servico digitado errado")
    documento = etree.fromstring(assinar_xml(xml, identificador, certificado))
    assert xsd_evento.validate(documento), "\n".join(e.message for e in xsd_evento.error_log)


def test_textos_sao_limpos_para_o_padrao_do_schema(nota, empresa):
    nota.tomador_nome = "Padaria “Pão Quente” – Filial 🍞"
    xml, _ = dps.montar_xml(nota, empresa)
    nome = etree.fromstring(xml).find(".//{*}toma/{*}xNome").text
    assert nome == 'Padaria "Pão Quente" - Filial'


def test_descricao_mantem_quebras_de_linha(nota, empresa):
    nota.descricao_servico = "Item 1\r\nItem 2"
    xml, _ = dps.montar_xml(nota, empresa)
    assert etree.fromstring(xml).find(".//{*}xDescServ").text == "Item 1\nItem 2"


def test_emissor_valida_no_schema_antes_de_enviar(config, nota, tmp_path, monkeypatch):
    """Se o XML sair fora do schema, a nota vira erro e nada e enviado."""
    from unittest.mock import patch
    from nfse.emissor import STATUS_ERRO, Emissor

    monkeypatch.setattr(esquema, "validar", lambda xml, base="DPS", pasta=None: ["campo X"])
    emissor = Emissor(config, diretorio_saida=tmp_path / "saida")
    empresa = config.obter("EMPRESA EXEMPLO")
    with patch("nfse.emissor.ClienteNFSe") as cliente:
        resultado = emissor.emitir_nota(empresa, emissor.abrir_certificado(empresa), nota)
    cliente.return_value.emitir.assert_not_called()
    assert resultado.status == STATUS_ERRO and "schema oficial" in resultado.mensagem
