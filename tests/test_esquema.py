"""Validacao opcional contra o XSD oficial."""

from pathlib import Path

from nfse import esquema

XSD = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns="http://www.sped.fazenda.gov.br/nfse"
           targetNamespace="http://www.sped.fazenda.gov.br/nfse"
           elementFormDefault="qualified">
  <xs:element name="DPS">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="infDPS">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="tpAmb" type="xs:string"/>
            </xs:sequence>
            <xs:attribute name="Id" type="xs:string"/>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
      <xs:attribute name="versao" type="xs:string"/>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""

VALIDO = (b'<DPS xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00">'
          b'<infDPS Id="X"><tpAmb>2</tpAmb></infDPS></DPS>')
INVALIDO = (b'<DPS xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00">'
            b'<infDPS Id="X"><campoInexistente>2</campoInexistente></infDPS></DPS>')


def test_sem_xsd_a_validacao_e_pulada(tmp_path):
    esquema.limpar_cache()
    assert esquema.validar(INVALIDO, "DPS", pasta=tmp_path) == []


def test_xml_valido_passa(tmp_path):
    esquema.limpar_cache()
    (tmp_path / "DPS_v1.00.xsd").write_text(XSD, encoding="utf-8")
    assert esquema.validar(VALIDO, "DPS", pasta=tmp_path) == []


def test_xml_invalido_e_apontado(tmp_path):
    esquema.limpar_cache()
    (tmp_path / "DPS_v1.00.xsd").write_text(XSD, encoding="utf-8")
    erros = esquema.validar(INVALIDO, "DPS", pasta=tmp_path)
    assert erros and "campoInexistente" in erros[0]


def test_localiza_o_arquivo_do_schema(tmp_path):
    esquema.limpar_cache()
    (tmp_path / "DPS_v1.00.xsd").write_text(XSD, encoding="utf-8")
    assert Path(esquema.localizar("DPS", tmp_path)).name == "DPS_v1.00.xsd"
