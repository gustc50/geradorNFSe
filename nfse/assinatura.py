"""Assinatura digital XMLDSig do DPS e dos eventos.

Padrao exigido pelo layout nacional da NFS-e (mesmo da NF-e):

* assinatura ``enveloped``, aplicada ao elemento identificado pelo atributo
  ``Id`` (``infDPS`` na DPS, ``infPedReg`` nos eventos);
* canonicalizacao C14N 1.0 inclusiva, sem comentarios;
* ``DigestMethod`` SHA-1 e ``SignatureMethod`` RSA-SHA1;
* ``KeyInfo`` com o certificado do assinante em ``X509Certificate``.

O elemento ``<Signature>`` entra como ultimo filho da raiz, irmao do elemento
assinado.
"""

from __future__ import annotations

import base64

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from lxml import etree

from .certificado import InfoCertificado

NS_DSIG = "http://www.w3.org/2000/09/xmldsig#"
ALG_C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
ALG_ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
ALG_RSA_SHA1 = "http://www.w3.org/2000/09/xmldsig#rsa-sha1"
ALG_SHA1 = "http://www.w3.org/2000/09/xmldsig#sha1"


class ErroDeAssinatura(Exception):
    """Falha ao assinar ou conferir a assinatura do XML."""


def _c14n(elemento: etree._Element) -> bytes:
    """Canonicaliza em C14N 1.0 inclusiva, sem comentarios.

    O subtree e serializado e reinterpretado antes da canonicalizacao. Esse
    passo extra contorna um defeito do libxml2: ao canonicalizar um trecho cujo
    ancestral redeclara o namespace padrao - exatamente o caso de
    ``<Signature xmlns="...xmldsig#">`` dentro de ``<DPS xmlns="...nfse">`` -
    ele insere ``xmlns=""`` nos elementos descendentes e a assinatura sai
    invalida para qualquer verificador (inclusive o do Portal Nacional).

    A serializacao do lxml ja carrega todos os namespaces visiveis no trecho,
    inclusive os declarados e nao usados, entao o resultado continua sendo a
    C14N inclusiva correta.
    """
    fragmento = etree.tostring(elemento)
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    isolado = etree.fromstring(fragmento, parser=parser)
    return etree.tostring(isolado, method="c14n", exclusive=False, with_comments=False)


def _sha1_b64(dados: bytes) -> str:
    digest = hashes.Hash(hashes.SHA1())
    digest.update(dados)
    return base64.b64encode(digest.finalize()).decode("ascii")


def _sub(pai: etree._Element, nome: str, **atributos) -> etree._Element:
    return etree.SubElement(pai, f"{{{NS_DSIG}}}{nome}", attrib=atributos or None)


def _localizar_por_id(raiz: etree._Element, id_referencia: str) -> etree._Element:
    for elemento in raiz.iter():
        if elemento.get("Id") == id_referencia:
            return elemento
    raise ErroDeAssinatura(
        f"Nenhum elemento com Id={id_referencia!r} foi encontrado no XML.")


def assinar_elemento(raiz: etree._Element, id_referencia: str,
                     info: InfoCertificado) -> etree._Element:
    """Assina o elemento de ``Id`` informado e anexa a ``<Signature>`` a raiz."""
    if not isinstance(info.chave_privada, rsa.RSAPrivateKey):
        raise ErroDeAssinatura(
            "O certificado nao contem uma chave RSA. A NFS-e nacional exige RSA-SHA1.")

    alvo = _localizar_por_id(raiz, id_referencia)
    digest = _sha1_b64(_c14n(alvo))

    # nsmap default: gera <Signature xmlns="...xmldsig#"> sem prefixo, como o
    # restante do ecossistema fiscal brasileiro (NF-e, NFS-e) espera.
    assinatura = etree.SubElement(raiz, f"{{{NS_DSIG}}}Signature",
                                  nsmap={None: NS_DSIG})
    info_assinada = _sub(assinatura, "SignedInfo")
    _sub(info_assinada, "CanonicalizationMethod", Algorithm=ALG_C14N)
    _sub(info_assinada, "SignatureMethod", Algorithm=ALG_RSA_SHA1)

    referencia = _sub(info_assinada, "Reference", URI=f"#{id_referencia}")
    transformacoes = _sub(referencia, "Transforms")
    _sub(transformacoes, "Transform", Algorithm=ALG_ENVELOPED)
    _sub(transformacoes, "Transform", Algorithm=ALG_C14N)
    _sub(referencia, "DigestMethod", Algorithm=ALG_SHA1)
    _sub(referencia, "DigestValue").text = digest

    valor = info.chave_privada.sign(_c14n(info_assinada), padding.PKCS1v15(), hashes.SHA1())
    _sub(assinatura, "SignatureValue").text = base64.b64encode(valor).decode("ascii")

    chave_info = _sub(assinatura, "KeyInfo")
    dados_x509 = _sub(chave_info, "X509Data")
    der = info.certificado.public_bytes(serialization.Encoding.DER)
    _sub(dados_x509, "X509Certificate").text = base64.b64encode(der).decode("ascii")

    return raiz


def assinar_xml(xml: bytes | str, id_referencia: str, info: InfoCertificado) -> bytes:
    """Assina um XML inteiro e devolve os bytes assinados (UTF-8, sem quebras)."""
    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    parser = etree.XMLParser(remove_blank_text=True, resolve_entities=False,
                             no_network=True)
    raiz = etree.fromstring(xml, parser=parser)
    assinar_elemento(raiz, id_referencia, info)
    return etree.tostring(raiz, encoding="UTF-8", xml_declaration=True)


def verificar_assinatura(xml: bytes | str) -> bool:
    """Confere digest e assinatura usando o certificado embutido no proprio XML.

    Serve como autoteste local (o Portal Nacional refaz essa conferencia).
    """
    from cryptography import x509 as _x509

    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False,
                             no_network=True)
    raiz = etree.fromstring(xml, parser=parser)

    assinatura = raiz.find(f"{{{NS_DSIG}}}Signature")
    if assinatura is None:
        raise ErroDeAssinatura("O XML nao possui assinatura.")

    info_assinada = assinatura.find(f"{{{NS_DSIG}}}SignedInfo")
    referencia = info_assinada.find(f"{{{NS_DSIG}}}Reference")
    uri = referencia.get("URI", "")
    alvo = _localizar_por_id(raiz, uri.lstrip("#"))

    esperado = referencia.find(f"{{{NS_DSIG}}}DigestValue").text
    if _sha1_b64(_c14n(alvo)) != esperado:
        raise ErroDeAssinatura(
            "O conteudo assinado foi alterado depois da assinatura (digest nao confere).")

    certificado_b64 = assinatura.find(
        f".//{{{NS_DSIG}}}X509Certificate").text
    certificado = _x509.load_der_x509_certificate(base64.b64decode(certificado_b64))
    valor = base64.b64decode(assinatura.find(f"{{{NS_DSIG}}}SignatureValue").text)
    try:
        certificado.public_key().verify(
            valor, _c14n(info_assinada), padding.PKCS1v15(), hashes.SHA1())
    except InvalidSignature as exc:
        raise ErroDeAssinatura("A assinatura digital nao confere.") from exc
    return True
