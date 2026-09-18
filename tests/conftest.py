"""Fixtures compartilhadas pelos testes."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nfse import dps, modelo_planilha                      # noqa: E402
from nfse.certificado import ler_certificado               # noqa: E402
from nfse.config import Configuracao, Empresa              # noqa: E402
from tests.apoio import gerar_pfx                          # noqa: E402

SENHA_TESTE = "teste123"


@pytest.fixture
def pfx(tmp_path) -> Path:
    return gerar_pfx(tmp_path / "certificado.pfx", senha=SENHA_TESTE)


@pytest.fixture
def certificado(pfx):
    return ler_certificado(pfx, SENHA_TESTE)


@pytest.fixture
def config(tmp_path, pfx) -> Configuracao:
    cfg = Configuracao.carregar(tmp_path / "dados")
    empresa = Empresa(
        nome="EMPRESA EXEMPLO",
        razao_social="EMPRESA EXEMPLO LTDA",
        cnpj="11222333000181",
        inscricao_municipal="987654",
        codigo_municipio="3550308",
        ambiente="homologacao",
        serie_padrao="1",
        proximo_numero=1,
    )
    cfg.adicionar(empresa)
    cfg.guardar_certificado(empresa, pfx, SENHA_TESTE)
    cfg.salvar()
    return cfg


@pytest.fixture
def empresa(config) -> Empresa:
    return config.obter("EMPRESA EXEMPLO")


@pytest.fixture
def nota() -> dps.Nota:
    return dps.Nota(
        numero=1,
        tomador_tipo_documento="CNPJ",
        tomador_documento="11.444.777/0001-61",
        tomador_nome="CLIENTE ALFA LTDA",
        tomador_cep="01310-100",
        tomador_codigo_municipio="3550308",
        tomador_logradouro="Avenida Paulista",
        tomador_numero="1000",
        tomador_bairro="Bela Vista",
        codigo_tributacao_nacional="010701",
        descricao_servico="Honorarios contabeis referentes a 01/2026",
        valor_servico=Decimal("1500.00"),
        aliquota_iss=Decimal("2"),
        tributacao_issqn="1",
        iss_retido="1",
        aba="EMPRESA EXEMPLO",
        linha=4,
    )


@pytest.fixture
def planilha_modelo(tmp_path) -> Path:
    return modelo_planilha.gerar(tmp_path / "notas.xlsx", ["EMPRESA EXEMPLO"])
