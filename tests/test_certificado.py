"""Leitura do certificado A1 e exportacao para o mTLS."""

from pathlib import Path

import pytest

from nfse.certificado import ErroDeCertificado, ler_certificado, par_pem_temporario
from tests.apoio import gerar_pfx
from tests.conftest import SENHA_TESTE


def test_le_titular_documento_e_validade(certificado):
    assert certificado.titular == "EMPRESA MODELO LTDA"
    assert certificado.documento == "11222333000181"
    assert not certificado.vencido
    assert certificado.dias_para_vencer > 300
    assert "11.222.333/0001-81" in certificado.resumo()


def test_senha_errada_tem_mensagem_clara(pfx):
    with pytest.raises(ErroDeCertificado, match="Senha incorreta"):
        ler_certificado(pfx, "senha-errada")


def test_arquivo_inexistente(tmp_path):
    with pytest.raises(ErroDeCertificado, match="nao encontrado"):
        ler_certificado(tmp_path / "nao_existe.pfx", SENHA_TESTE)


def test_certificado_vencido_e_identificado(tmp_path):
    arquivo = gerar_pfx(tmp_path / "velho.pfx", senha=SENHA_TESTE, dias_validade=-2)
    assert ler_certificado(arquivo, SENHA_TESTE).vencido


def test_par_pem_temporario_cria_e_apaga_os_arquivos(certificado):
    with par_pem_temporario(certificado) as (arquivo_cert, arquivo_chave):
        assert Path(arquivo_cert).read_text().startswith("-----BEGIN CERTIFICATE-----")
        assert "PRIVATE KEY" in Path(arquivo_chave).read_text()
        assert oct(Path(arquivo_chave).stat().st_mode)[-3:] == "600"
        guardados = (arquivo_cert, arquivo_chave)
    for caminho in guardados:
        assert not Path(caminho).exists(), "a chave privada nao pode sobrar no disco"
