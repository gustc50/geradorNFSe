"""Escolha do layout da DPS e reenvio automatico quando o Portal pede o outro."""

from datetime import date
from unittest.mock import patch

import pytest
from openpyxl import load_workbook

from nfse import modelo_planilha, tabelas
from nfse.api import ErroDaApi, RespostaEmissao
from nfse.emissor import STATUS_EMITIDA, STATUS_ERRO, Emissor

CHAVE = "35503082" + "2" + "11222333000181" + "0" * 27

# Texto EXATO devolvido pelo Portal em homologacao (nov/2026) ao receber o
# layout anterior.
RECUSA_LAYOUT = ErroDaApi(
    "Emissao recusada pelo Portal Nacional (HTTP 400).", status=400,
    erros=[{"codigo": "E1235", "descricao": (
        "Falha no esquema XML do DF-e. The element 'infDPS' in namespace "
        "'http://www.sped.fazenda.gov.br/nfse' has invalid child element 'cLocEmi' in "
        "namespace 'http://www.sped.fazenda.gov.br/nfse'. List of possible elements "
        "expected: 'cMotivoEmisTI, finNFSe' in namespace "
        "'http://www.sped.fazenda.gov.br/nfse'.")}])

RECUSA_DE_DADO = ErroDaApi(
    "Emissao recusada pelo Portal Nacional (HTTP 400).", status=400,
    erros=[{"codigo": "E1235", "descricao": "Falha no esquema XML do DF-e. pAliq invalido."}])

NOTA = {
    "Tipo doc. tomador": "CNPJ", "CNPJ/CPF do tomador": "11444777000161",
    "Nome/Razao social do tomador": "CLIENTE ALFA LTDA", "Cod. tributacao nacional": "010701",
    "Descricao do servico": "Exame admissional", "Valor do servico": 350,
    "Tributacao do ISSQN": "1", "Retencao do ISSQN": "1", "Aliquota ISS (%)": 2,
}


def preencher(caminho, linhas):
    livro = load_workbook(caminho)
    folha = livro["EMPRESA EXEMPLO"]
    mapa = {c.value: c.column for c in folha[modelo_planilha.LINHA_TITULOS]}
    for numero, valores in linhas.items():
        for titulo, valor in valores.items():
            folha.cell(row=numero, column=mapa[titulo]).value = valor
    livro.save(caminho)


# --------------------------------------------------------------------------- #
# Escolha automatica
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ambiente,hoje,esperado", [
    ("homologacao", date(2026, 11, 5), "nt009"),
    ("homologacao", date(2026, 12, 15), "nt009"),
    ("producao", date(2026, 11, 5), "anterior"),
    ("producao", date(2026, 11, 30), "anterior"),
    ("producao", date(2026, 12, 1), "nt009"),
])
def test_layout_automatico(ambiente, hoje, esperado):
    assert tabelas.layout_para(ambiente, "automatico", hoje) == esperado


def test_layout_fixo_vence_o_automatico():
    assert tabelas.layout_para("homologacao", "anterior") == "anterior"
    assert tabelas.layout_para("producao", "nt009", date(2026, 1, 1)) == "nt009"


def test_layout_invalido():
    with pytest.raises(ValueError):
        tabelas.layout_para("producao", "xyz")


# --------------------------------------------------------------------------- #
# Reenvio quando o Portal pede o outro layout
# --------------------------------------------------------------------------- #
def _layouts_enviados(cliente):
    return ["nt009" if b"<finNFSe>" in chamada.args[0] else "anterior"
            for chamada in cliente.return_value.emitir.call_args_list]


def test_recusa_de_layout_reenvia_no_outro_e_lembra(config, planilha_modelo, tmp_path):
    empresa = config.obter("EMPRESA EXEMPLO")
    empresa.layout = "automatico"
    preencher(planilha_modelo, {4: NOTA, 5: NOTA})
    emissor = Emissor(config, diretorio_saida=tmp_path / "saida")

    with patch.object(tabelas, "layout_para", return_value="anterior"), \
         patch("nfse.emissor.ClienteNFSe") as cliente:
        cliente.return_value.emitir.side_effect = [
            RECUSA_LAYOUT,                                       # 1a nota, layout antigo
            RespostaEmissao(chave_acesso=CHAVE, numero_nfse="1"),  # reenvio NT 009
            RespostaEmissao(chave_acesso=CHAVE, numero_nfse="2"),  # 2a nota ja em NT 009
        ]
        lote = emissor.emitir_planilha(planilha_modelo)

    assert [r.status for r in lote.resultados] == [STATUS_EMITIDA, STATUS_EMITIDA]
    assert _layouts_enviados(cliente) == ["anterior", "nt009", "nt009"]
    # o reenvio usa o MESMO numero de DPS (a primeira tentativa foi recusada)
    assert [r.numero_dps for r in lote.resultados] == [1, 2]


def test_recusa_que_nao_e_de_layout_nao_reenvia(config, planilha_modelo, tmp_path):
    preencher(planilha_modelo, {4: NOTA})
    with patch("nfse.emissor.ClienteNFSe") as cliente:
        cliente.return_value.emitir.side_effect = RECUSA_DE_DADO
        lote = Emissor(config, diretorio_saida=tmp_path / "saida").emitir_planilha(planilha_modelo)
    assert cliente.return_value.emitir.call_count == 1
    assert lote.resultados[0].status == STATUS_ERRO


def test_layout_fixado_pelo_usuario_nao_e_trocado(config, planilha_modelo, tmp_path):
    config.obter("EMPRESA EXEMPLO").layout = "anterior"
    preencher(planilha_modelo, {4: NOTA})
    with patch("nfse.emissor.ClienteNFSe") as cliente:
        cliente.return_value.emitir.side_effect = RECUSA_LAYOUT
        Emissor(config, diretorio_saida=tmp_path / "saida").emitir_planilha(planilha_modelo)
    assert cliente.return_value.emitir.call_count == 1


def test_se_os_dois_layouts_falham_mostra_os_dois_erros(config, planilha_modelo, tmp_path):
    preencher(planilha_modelo, {4: NOTA})
    with patch("nfse.emissor.ClienteNFSe") as cliente:
        cliente.return_value.emitir.side_effect = [RECUSA_LAYOUT, RECUSA_DE_DADO]
        lote = Emissor(config, diretorio_saida=tmp_path / "saida").emitir_planilha(planilha_modelo)
    assert cliente.return_value.emitir.call_count == 2
    mensagem = lote.resultados[0].mensagem
    assert "pAliq" in mensagem and "finNFSe" in mensagem


def test_homologacao_hoje_ja_sai_no_layout_nt009(config, planilha_modelo, tmp_path):
    """O caso real: em homologacao a primeira tentativa ja deve ir no layout novo."""
    preencher(planilha_modelo, {4: NOTA})
    with patch("nfse.emissor.ClienteNFSe") as cliente:
        cliente.return_value.emitir.return_value = RespostaEmissao(chave_acesso=CHAVE)
        Emissor(config, diretorio_saida=tmp_path / "saida").emitir_planilha(planilha_modelo)
    assert _layouts_enviados(cliente) == ["nt009"]
