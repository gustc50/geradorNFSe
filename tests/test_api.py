"""Cliente da API do Portal Nacional (com respostas simuladas)."""

import gzip
import json
from unittest.mock import patch

import pytest
import requests

from nfse.api import ClienteNFSe, ErroDaApi, compactar, descompactar

CHAVE = "3" * 50


class RespostaFalsa:
    def __init__(self, status=200, corpo=None, conteudo=b""):
        self.status_code = status
        self._corpo = corpo
        self.content = conteudo
        self.text = json.dumps(corpo) if corpo is not None else ""

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        if self._corpo is None:
            raise ValueError("sem json")
        return self._corpo


def test_compactar_e_descompactar():
    xml = b"<DPS>conteudo</DPS>"
    empacotado = compactar(xml)
    assert descompactar(empacotado) == xml
    assert gzip.decompress(__import__("base64").b64decode(empacotado)) == xml


def test_descompactar_aceita_conteudo_sem_gzip():
    import base64
    assert descompactar(base64.b64encode(b"puro").decode()) == b"puro"


def test_emissao_bem_sucedida(empresa, certificado):
    corpo = {
        "chaveAcesso": CHAVE,
        "idDps": "DPS123",
        "dataHoraProcessamento": "2026-01-15T10:00:00-03:00",
        "nfseXmlGZipB64": compactar(b"<NFSe>ok</NFSe>"),
    }
    cliente = ClienteNFSe(empresa, certificado)
    with patch("nfse.api.requests.request", return_value=RespostaFalsa(201, corpo)) as chamada:
        resposta = cliente.emitir(b"<DPS/>")

    assert resposta.autorizada
    assert resposta.chave_acesso == CHAVE
    assert resposta.xml_nfse == b"<NFSe>ok</NFSe>"

    metodo, url = chamada.call_args[0]
    assert metodo == "POST"
    assert url.endswith("/nfse")
    enviado = chamada.call_args[1]["json"]
    assert descompactar(enviado["dpsXmlGZipB64"]) == b"<DPS/>"
    assert chamada.call_args[1]["cert"], "a chamada precisa usar o certificado (mTLS)"


def test_ambiente_de_homologacao_usa_a_url_de_producao_restrita(empresa, certificado):
    assert "producaorestrita" in ClienteNFSe(empresa, certificado).base


def test_ambiente_de_producao(empresa, certificado):
    empresa.ambiente = "producao"
    assert ClienteNFSe(empresa, certificado).base == "https://sefin.nfse.gov.br/sefinnacional"


def test_erro_do_portal_vira_mensagem_legivel(empresa, certificado):
    corpo = {"erros": [{"codigo": "E0123", "descricao": "Aliquota invalida",
                        "complemento": "campo pAliq"}]}
    cliente = ClienteNFSe(empresa, certificado)
    with patch("nfse.api.requests.request", return_value=RespostaFalsa(400, corpo)):
        with pytest.raises(ErroDaApi) as excecao:
            cliente.emitir(b"<DPS/>")
    detalhe = excecao.value.detalhado()
    assert "E0123" in detalhe and "Aliquota invalida" in detalhe and "pAliq" in detalhe
    assert excecao.value.status == 400


def test_falha_de_rede_vira_erro_da_api(empresa, certificado):
    cliente = ClienteNFSe(empresa, certificado)
    with patch("nfse.api.requests.request",
               side_effect=requests.exceptions.ConnectionError("sem rede")):
        with pytest.raises(ErroDaApi, match="Falha de comunicacao"):
            cliente.emitir(b"<DPS/>")


def test_timeout_orienta_a_consultar_antes_de_reenviar(empresa, certificado):
    cliente = ClienteNFSe(empresa, certificado)
    with patch("nfse.api.requests.request", side_effect=requests.exceptions.ReadTimeout()):
        with pytest.raises(ErroDaApi, match="Consulte a nota antes de reenviar"):
            cliente.emitir(b"<DPS/>")


def test_consulta_por_chave(empresa, certificado):
    corpo = {"nfseXmlGZipB64": compactar(b"<NFSe/>")}
    cliente = ClienteNFSe(empresa, certificado)
    with patch("nfse.api.requests.request", return_value=RespostaFalsa(200, corpo)) as chamada:
        resposta = cliente.consultar(CHAVE)
    assert resposta.xml_nfse == b"<NFSe/>"
    assert chamada.call_args[0][1].endswith(f"/nfse/{CHAVE}")


def test_download_da_danfse(empresa, certificado, tmp_path):
    cliente = ClienteNFSe(empresa, certificado)
    with patch("nfse.api.requests.request",
               return_value=RespostaFalsa(200, None, b"%PDF-1.4 conteudo")) as chamada:
        arquivo = cliente.baixar_danfse(CHAVE, tmp_path / "nota.pdf")
    assert arquivo.read_bytes().startswith(b"%PDF")
    assert chamada.call_args[0][1].endswith(f"/danfse/{CHAVE}")


def test_registro_de_evento(empresa, certificado):
    cliente = ClienteNFSe(empresa, certificado)
    with patch("nfse.api.requests.request",
               return_value=RespostaFalsa(200, {"status": "registrado"})) as chamada:
        assert cliente.registrar_evento(CHAVE, b"<evento/>") == {"status": "registrado"}
    assert chamada.call_args[0][1].endswith(f"/nfse/{CHAVE}/eventos")
    assert "pedidoRegistroEventoXmlGZipB64" in chamada.call_args[1]["json"]
