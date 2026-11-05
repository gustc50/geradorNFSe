"""Montagem e validacao do XML da DPS."""

from decimal import Decimal

import pytest
from lxml import etree

from nfse import dps
from nfse.util import ErroDeValidacao

NS = {"n": dps.NS_NFSE}


def valor(xml: bytes, caminho: str) -> str:
    achado = etree.fromstring(xml).find(caminho, NS)
    return achado.text if achado is not None else None


def test_id_da_dps_tem_45_caracteres(empresa):
    identificador = dps.montar_id(empresa, "1", 7)
    assert identificador.startswith("DPS")
    assert len(identificador) == 45
    assert identificador == "DPS" + "3550308" + "2" + "11222333000181" + "00001" + "7".zfill(15)


def test_montagem_basica(empresa, nota):
    xml, identificador = dps.montar_xml(nota, empresa)
    assert valor(xml, "n:infDPS/n:tpAmb") == "2"
    assert valor(xml, "n:infDPS/n:cLocEmi") == "3550308"
    assert valor(xml, "n:infDPS/n:serie") == "00001"
    assert valor(xml, "n:infDPS/n:nDPS") == "1"
    assert valor(xml, "n:infDPS/n:prest/n:CNPJ") == "11222333000181"
    assert valor(xml, "n:infDPS/n:prest/n:IM") == "987654"
    assert valor(xml, "n:infDPS/n:toma/n:CNPJ") == "11444777000161"
    assert valor(xml, "n:infDPS/n:serv/n:cServ/n:cTribNac") == "010701"
    assert valor(xml, "n:infDPS/n:valores/n:vServPrest/n:vServ") == "1500.00"
    assert etree.fromstring(xml).find("n:infDPS", NS).get("Id") == identificador


def test_ordem_dos_elementos_segue_o_layout(empresa, nota):
    from nfse import tabelas
    base = ["tpAmb", "dhEmi", "verAplic", "serie", "nDPS", "dCompet", "tpEmit"]
    resto = ["cLocEmi", "prest", "toma", "serv", "valores"]
    for layout, esperado in ((tabelas.LAYOUT_ANTERIOR, base + resto),
                             (tabelas.LAYOUT_NT009, base + ["finNFSe"] + resto)):
        xml, _ = dps.montar_xml(nota, empresa, layout=layout)
        filhos = [etree.QName(e).localname for e in etree.fromstring(xml).find("n:infDPS", NS)]
        assert filhos == esperado, layout


def test_endereco_nacional_do_tomador(empresa, nota):
    xml, _ = dps.montar_xml(nota, empresa)
    assert valor(xml, "n:infDPS/n:toma/n:end/n:endNac/n:cMun") == "3550308"
    assert valor(xml, "n:infDPS/n:toma/n:end/n:endNac/n:CEP") == "01310100"
    assert valor(xml, "n:infDPS/n:toma/n:end/n:xLgr") == "Avenida Paulista"


def test_tomador_pessoa_fisica(empresa, nota):
    nota.tomador_tipo_documento = "CPF"
    nota.tomador_documento = "529.982.247-25"
    xml, _ = dps.montar_xml(nota, empresa)
    assert valor(xml, "n:infDPS/n:toma/n:CPF") == "52998224725"


def test_tomador_no_exterior(empresa, nota):
    nota.tomador_tipo_documento = "NIF"
    nota.tomador_documento = "US-99887766"
    nota.tomador_codigo_pais = "US"
    nota.tomador_cidade_exterior = "Miami"
    nota.tomador_estado_exterior = "FL"
    nota.tomador_cep_exterior = "33101"
    nota.tomador_cep = nota.tomador_codigo_municipio = ""
    nota.tributacao_issqn = "2"
    nota.codigo_pais_resultado = "US"
    xml, _ = dps.montar_xml(nota, empresa)
    assert valor(xml, "n:infDPS/n:toma/n:NIF") == "US-99887766"
    assert valor(xml, "n:infDPS/n:toma/n:end/n:endExt/n:cPais") == "US"
    assert valor(xml, "n:infDPS/n:valores/n:trib/n:tribMun/n:cPaisResult") == "US"


def test_descontos_e_deducoes(empresa, nota):
    nota.desconto_incondicionado = Decimal("100")
    nota.desconto_condicionado = Decimal("50")
    nota.valor_deducoes = Decimal("200")
    xml, _ = dps.montar_xml(nota, empresa, layout="anterior")
    assert valor(xml, "n:infDPS/n:valores/n:vDescCondIncond/n:vDescIncond") == "100.00"
    assert valor(xml, "n:infDPS/n:valores/n:vDescCondIncond/n:vDescCond") == "50.00"
    assert valor(xml, "n:infDPS/n:valores/n:vDedRed/n:vDR") == "200.00"


def test_tributos_federais(empresa, nota):
    nota.cst_pis_cofins = "01"
    nota.retencao_pis_cofins = "1"
    nota.valor_pis = Decimal("9.75")
    nota.valor_cofins = Decimal("45")
    nota.valor_irrf = Decimal("22.50")
    nota.valor_inss = Decimal("165")
    xml, _ = dps.montar_xml(nota, empresa)
    base = "n:infDPS/n:valores/n:trib/n:tribFed"
    assert valor(xml, f"{base}/n:piscofins/n:CST") == "01"
    assert valor(xml, f"{base}/n:piscofins/n:vPis") == "9.75"
    assert valor(xml, f"{base}/n:piscofins/n:tpRetPisCofins") == "1"
    assert valor(xml, f"{base}/n:piscofins/n:pAliqPis") is None
    assert valor(xml, f"{base}/n:vRetIRRF") == "22.50"
    assert valor(xml, f"{base}/n:vRetCP") == "165.00"


def test_sem_tributos_federais_o_bloco_nao_aparece(empresa, nota):
    xml, _ = dps.montar_xml(nota, empresa)
    assert etree.fromstring(xml).find("n:infDPS/n:valores/n:trib/n:tribFed", NS) is None


def test_total_de_tributos_padrao_e_nao_informado(empresa, nota):
    xml, _ = dps.montar_xml(nota, empresa)
    assert valor(xml, "n:infDPS/n:valores/n:trib/n:totTrib/n:indTotTrib") == "0"


def test_total_de_tributos_detalhado(empresa, nota):
    nota.tributos_federais = Decimal("120")
    nota.tributos_municipais = Decimal("30")
    xml, _ = dps.montar_xml(nota, empresa)
    base = "n:infDPS/n:valores/n:trib/n:totTrib/n:vTotTrib"
    assert valor(xml, f"{base}/n:vTotTribFed") == "120.00"
    assert valor(xml, f"{base}/n:vTotTribEst") == "0.00"
    assert valor(xml, f"{base}/n:vTotTribMun") == "30.00"


def test_simples_nacional_inclui_regime_de_apuracao(empresa, nota):
    empresa.optante_simples = "3"
    empresa.regime_apuracao_sn = "1"
    empresa.percentual_simples = "6"
    xml, _ = dps.montar_xml(nota, empresa)
    assert valor(xml, "n:infDPS/n:prest/n:regTrib/n:opSimpNac") == "3"
    assert valor(xml, "n:infDPS/n:prest/n:regTrib/n:regApTribSN") == "1"


def test_municipio_da_prestacao_cai_para_o_do_emitente(empresa, nota):
    nota.codigo_municipio_prestacao = ""
    xml, _ = dps.montar_xml(nota, empresa)
    assert valor(xml, "n:infDPS/n:serv/n:locPrest/n:cLocPrestacao") == "3550308"


# --------------------------------------------------------------------------- #
# Validacao
# --------------------------------------------------------------------------- #
def test_valor_zerado_e_recusado(empresa, nota):
    nota.valor_servico = Decimal("0")
    assert any("maior que zero" in p for p in dps.validar(nota, empresa))


def test_cnpj_do_tomador_invalido(empresa, nota):
    nota.tomador_documento = "11444777000162"
    assert any("CNPJ do tomador invalido" in p for p in dps.validar(nota, empresa))


def test_codigo_de_servico_precisa_ter_6_digitos(empresa, nota):
    nota.codigo_tributacao_nacional = "0107"
    assert any("6 digitos" in p for p in dps.validar(nota, empresa))


def test_imunidade_exige_o_tipo(empresa, nota):
    nota.tributacao_issqn = "4"
    assert any("imunidade" in p.lower() for p in dps.validar(nota, empresa))


def test_exportacao_exige_pais_de_resultado(empresa, nota):
    nota.tributacao_issqn = "2"
    assert any("pais de resultado" in p.lower() for p in dps.validar(nota, empresa))


def test_endereco_incompleto_e_apontado(empresa, nota):
    nota.tomador_cep = ""
    assert any("CEP" in p for p in dps.validar(nota, empresa))


def test_desconto_maior_que_o_servico(empresa, nota):
    nota.desconto_incondicionado = Decimal("2000")
    assert any("descontos" in p for p in dps.validar(nota, empresa))


def test_montar_xml_recusa_nota_invalida(empresa, nota):
    nota.descricao_servico = ""
    with pytest.raises(ErroDeValidacao, match="Descricao do servico"):
        dps.montar_xml(nota, empresa)


def test_valor_liquido_desconta_retencoes(empresa, nota):
    nota.iss_retido = "2"
    nota.aliquota_iss = Decimal("5")
    nota.valor_irrf = Decimal("22.50")
    # 1500 - ISS retido (75) - IRRF (22,50)
    assert nota.valor_liquido == Decimal("1402.50")


# --------------------------------------------------------------------------- #
# Evento de cancelamento
# --------------------------------------------------------------------------- #
def test_evento_de_cancelamento(empresa):
    chave = "3" * 50
    xml, identificador = dps.montar_evento_cancelamento(
        empresa, chave, "1", "Valor digitado errado na nota")
    assert identificador == f"PRE{chave}101101"
    assert len(identificador) == 59
    raiz = etree.fromstring(xml)
    assert raiz.find("n:infPedReg/n:chNFSe", NS).text == chave
    assert raiz.find("n:infPedReg/n:CNPJAutor", NS).text == "11222333000181"
    assert raiz.find("n:infPedReg/n:e101101/n:cMotivo", NS).text == "1"


def test_cancelamento_recusa_chave_invalida(empresa):
    with pytest.raises(ErroDeValidacao, match="50 caracteres"):
        dps.montar_evento_cancelamento(empresa, "123", "1", "Valor digitado errado")


def test_cancelamento_exige_motivo_com_15_caracteres(empresa):
    with pytest.raises(ErroDeValidacao, match="15"):
        dps.montar_evento_cancelamento(empresa, "3" * 50, "1", "Erro")


def test_cancelamento_so_aceita_motivos_do_schema(empresa):
    with pytest.raises(ValueError, match="Motivo"):
        dps.montar_evento_cancelamento(empresa, "3" * 50, "4", "Valor digitado errado")


def test_ordem_do_issqn_segue_o_schema(empresa, nota):
    xml, _ = dps.montar_xml(nota, empresa)
    filhos = [etree.QName(e).localname for e in
              etree.fromstring(xml).find("n:infDPS/n:valores/n:trib/n:tribMun", NS)]
    assert filhos == ["tribISSQN", "tpRetISSQN", "pAliq"]


@pytest.mark.parametrize("campo,valor,trecho", [
    ("aliquota_iss", Decimal("15"), "0 a 9,99"),
    ("valor_irrf", Decimal("-1"), "negativo"),
    ("codigo_tributacao_municipal", "12", "3 digitos"),
    ("codigo_nbs", "123", "9 digitos"),
    ("tomador_telefone", "123", "6 a 20"),
    ("tomador_email", "sem-arroba", "E-mail"),
    ("serie", "A1", "Serie"),
    ("codigo_pais_prestacao", "USA", "ISO de 2 letras"),
])
def test_formatos_exigidos_pelo_schema(empresa, nota, campo, valor, trecho):
    setattr(nota, campo, valor)
    assert any(trecho in p for p in dps.validar(nota, empresa))


def test_endereco_no_exterior_incompleto(empresa, nota):
    nota.tomador_tipo_documento, nota.tomador_documento = "NIF", "X1"
    nota.tomador_codigo_pais, nota.tomador_cidade_exterior = "US", "Miami"
    problemas = dps.validar(nota, empresa)
    assert any("Estado/Provincia" in p for p in problemas)
    assert any("Codigo postal" in p for p in problemas)


def test_competencia_posterior_a_emissao(empresa, nota):
    from datetime import date
    from nfse import util
    nota.data_emissao = util.para_datahora("15/01/2026 10:00")
    nota.competencia = date(2026, 2, 1)
    assert any("competencia" in p.lower() for p in dps.validar(nota, empresa))


def test_data_de_emissao_no_futuro_e_recusada(empresa, nota):
    from datetime import timedelta
    from nfse import util
    nota.data_emissao = util.agora() + timedelta(days=2)
    assert any("futuro" in p for p in dps.validar(nota, empresa))


def test_serie_reservada_na_nt009(empresa, nota):
    nota.serie = "95000"
    assert any("reservada" in p for p in dps.validar(nota, empresa, "nt009"))
    assert not any("reservada" in p for p in dps.validar(nota, empresa, "anterior"))
