"""Planilha modelo, leitura das notas e gravacao dos resultados."""

from decimal import Decimal

import pytest
from openpyxl import load_workbook

from nfse import modelo_planilha, planilha


def titulos(caminho, aba="EMPRESA EXEMPLO"):
    livro = load_workbook(caminho)
    return {c.value: c.column for c in livro[aba][modelo_planilha.LINHA_TITULOS]}


def preencher(caminho, linha: int, valores: dict, aba="EMPRESA EXEMPLO"):
    livro = load_workbook(caminho)
    folha = livro[aba]
    mapa = {c.value: c.column for c in folha[modelo_planilha.LINHA_TITULOS]}
    for titulo, valor in valores.items():
        folha.cell(row=linha, column=mapa[titulo]).value = valor
    livro.save(caminho)


NOTA_VALIDA = {
    "Tipo doc. tomador": "CNPJ",
    "CNPJ/CPF do tomador": "11444777000161",
    "Nome/Razao social do tomador": "CLIENTE ALFA LTDA",
    "Cod. tributacao nacional": "010701",
    "Descricao do servico": "Honorarios contabeis",
    "Valor do servico": 1500,
    "Tributacao do ISSQN": "1 - Operacao tributavel",
    "Retencao do ISSQN": "1 - Nao retido",
    "Aliquota ISS (%)": 2,
}


def test_modelo_tem_as_abas_de_apoio(tmp_path):
    caminho = modelo_planilha.gerar(tmp_path / "m.xlsx", ["EMPRESA A", "EMPRESA B"])
    nomes = load_workbook(caminho).sheetnames
    assert modelo_planilha.ABA_LEIAME in nomes
    assert modelo_planilha.ABA_TABELAS in nomes
    assert "EMPRESA A" in nomes and "EMPRESA B" in nomes


def test_todas_as_colunas_aparecem_no_modelo(planilha_modelo):
    mapa = titulos(planilha_modelo)
    for coluna in planilha.COLUNAS + planilha.COLUNAS_RESULTADO:
        assert coluna.titulo in mapa, f"coluna ausente no modelo: {coluna.titulo}"


def test_linha_de_exemplo_nunca_e_emitida(planilha_modelo):
    aba = planilha.ler(planilha_modelo)["EMPRESA EXEMPLO"]
    assert aba.notas == []
    assert aba.ignoradas and "exemplo" in aba.ignoradas[0][1]


def test_le_uma_nota_preenchida(planilha_modelo):
    preencher(planilha_modelo, 4, NOTA_VALIDA)
    nota = planilha.ler(planilha_modelo)["EMPRESA EXEMPLO"].notas[0]
    assert nota.linha == 4
    assert nota.tomador_nome == "CLIENTE ALFA LTDA"
    assert nota.tomador_documento == "11444777000161"
    assert nota.valor_servico == Decimal("1500")
    assert nota.aliquota_iss == Decimal("2")
    assert nota.tributacao_issqn == "1"      # so o codigo, sem a descricao
    assert nota.iss_retido == "1"
    assert nota.tomador_tipo_documento == "CNPJ"


def test_valor_em_formato_brasileiro(planilha_modelo):
    preencher(planilha_modelo, 4, dict(NOTA_VALIDA, **{"Valor do servico": "2.350,75"}))
    nota = planilha.ler(planilha_modelo)["EMPRESA EXEMPLO"].notas[0]
    assert nota.valor_servico == Decimal("2350.75")


def test_linha_vazia_e_ignorada(planilha_modelo):
    preencher(planilha_modelo, 6, NOTA_VALIDA)      # deixa a 4 e a 5 em branco
    notas = planilha.ler(planilha_modelo)["EMPRESA EXEMPLO"].notas
    assert [n.linha for n in notas] == [6]


def test_nota_ja_emitida_nao_volta(planilha_modelo):
    preencher(planilha_modelo, 4, dict(NOTA_VALIDA,
                                       **{"Status": "EMITIDA", "Chave de acesso": "3" * 50}))
    aba = planilha.ler(planilha_modelo)["EMPRESA EXEMPLO"]
    assert aba.notas == []
    assert any("ja emitida" in motivo for _linha, motivo in aba.ignoradas)


def test_reprocessamento_forcado(planilha_modelo):
    preencher(planilha_modelo, 4, dict(NOTA_VALIDA,
                                       **{"Status": "EMITIDA", "Chave de acesso": "3" * 50}))
    aba = planilha.ler(planilha_modelo, somente_pendentes=False)["EMPRESA EXEMPLO"]
    assert [n.linha for n in aba.notas] == [4]


def test_abas_de_apoio_nao_sao_lidas(planilha_modelo):
    assert set(planilha.ler(planilha_modelo)) == {"EMPRESA EXEMPLO"}


def test_filtra_por_aba(tmp_path):
    caminho = modelo_planilha.gerar(tmp_path / "m.xlsx", ["EMPRESA A", "EMPRESA B"])
    assert set(planilha.ler(caminho, abas=["EMPRESA B"])) == {"EMPRESA B"}


def test_planilha_sem_cabecalho_reconhecivel(tmp_path):
    from openpyxl import Workbook
    livro = Workbook()
    livro.active.title = "EMPRESA X"
    livro.active["A1"] = "qualquer coisa"
    livro.save(tmp_path / "ruim.xlsx")
    with pytest.raises(planilha.ErroDePlanilha, match="linha de titulos"):
        planilha.ler(tmp_path / "ruim.xlsx")


def test_arquivo_inexistente(tmp_path):
    with pytest.raises(planilha.ErroDePlanilha, match="nao encontrada"):
        planilha.ler(tmp_path / "sumiu.xlsx")


def test_grava_resultado_de_volta(planilha_modelo):
    preencher(planilha_modelo, 4, NOTA_VALIDA)
    planilha.gravar_resultados(planilha_modelo, {"EMPRESA EXEMPLO": {4: {
        "status": "EMITIDA", "chave_acesso": "3" * 50, "numero_nfse": "45",
        "processado_em": "15/01/2026 10:00:00", "mensagem": "NFS-e autorizada."}}})
    mapa = titulos(planilha_modelo)
    folha = load_workbook(planilha_modelo)["EMPRESA EXEMPLO"]
    assert folha.cell(row=4, column=mapa["Status"]).value == "EMITIDA"
    assert folha.cell(row=4, column=mapa["Chave de acesso"]).value == "3" * 50
    # e a linha volta a ser ignorada na proxima leitura
    assert planilha.ler(planilha_modelo)["EMPRESA EXEMPLO"].notas == []


def test_adicionar_aba_de_empresa(planilha_modelo):
    modelo_planilha.adicionar_empresa(planilha_modelo, "EMPRESA NOVA")
    assert "EMPRESA NOVA" in load_workbook(planilha_modelo).sheetnames
    assert "EMPRESA EXEMPLO" in load_workbook(planilha_modelo).sheetnames
