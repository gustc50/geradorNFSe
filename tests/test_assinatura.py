"""Assinatura XMLDSig do DPS."""

import pytest
from lxml import etree

from nfse.assinatura import (NS_DSIG, ErroDeAssinatura, _c14n, assinar_xml,
                             verificar_assinatura)

XML_BASE = (b'<DPS xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00">'
            b'<infDPS Id="DPS123"><tpAmb>2</tpAmb><serie>00001</serie></infDPS></DPS>')


def test_assina_e_confere(certificado):
    assinado = assinar_xml(XML_BASE, "DPS123", certificado)
    assert verificar_assinatura(assinado) is True


def test_assinatura_usa_o_formato_canonico_sem_prefixo(certificado):
    texto = assinar_xml(XML_BASE, "DPS123", certificado).decode()
    assert '<Signature xmlns="http://www.w3.org/2000/09/xmldsig#">' in texto
    assert "ns0:" not in texto, "a Signature nao pode sair com prefixo gerado"


def test_algoritmos_exigidos_pelo_layout(certificado):
    texto = assinar_xml(XML_BASE, "DPS123", certificado).decode()
    assert "http://www.w3.org/TR/2001/REC-xml-c14n-20010315" in texto
    assert "http://www.w3.org/2000/09/xmldsig#rsa-sha1" in texto
    assert "http://www.w3.org/2000/09/xmldsig#sha1" in texto
    assert "http://www.w3.org/2000/09/xmldsig#enveloped-signature" in texto
    assert "<X509Certificate>" in texto


def test_signature_entra_como_irmao_do_elemento_assinado(certificado):
    raiz = etree.fromstring(assinar_xml(XML_BASE, "DPS123", certificado))
    assert [etree.QName(f).localname for f in raiz] == ["infDPS", "Signature"]


def test_canonicalizacao_nao_insere_xmlns_vazio(certificado):
    """Regressao: o libxml2 inseria xmlns="" e invalidava a assinatura."""
    raiz = etree.fromstring(assinar_xml(XML_BASE, "DPS123", certificado))
    info_assinada = raiz.find(f"{{{NS_DSIG}}}Signature").find(f"{{{NS_DSIG}}}SignedInfo")
    assert b'xmlns=""' not in _c14n(info_assinada)


def test_adulteracao_do_conteudo_e_detectada(certificado):
    assinado = assinar_xml(XML_BASE, "DPS123", certificado)
    adulterado = assinado.replace(b"<tpAmb>2</tpAmb>", b"<tpAmb>1</tpAmb>")
    with pytest.raises(ErroDeAssinatura, match="alterado"):
        verificar_assinatura(adulterado)


def test_adulteracao_da_assinatura_e_detectada(certificado):
    raiz = etree.fromstring(assinar_xml(XML_BASE, "DPS123", certificado))
    valor = raiz.find(f".//{{{NS_DSIG}}}SignatureValue")
    valor.text = "QUJD" + valor.text[4:]
    with pytest.raises(ErroDeAssinatura, match="nao confere"):
        verificar_assinatura(etree.tostring(raiz))


def test_id_inexistente(certificado):
    with pytest.raises(ErroDeAssinatura, match="Nenhum elemento"):
        assinar_xml(XML_BASE, "NAO_EXISTE", certificado)


def test_xml_sem_assinatura():
    with pytest.raises(ErroDeAssinatura, match="nao possui assinatura"):
        verificar_assinatura(XML_BASE)
