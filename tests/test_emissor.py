"""Emissao em lote: numeracao, tratamento de erro e gravacao do resultado."""

from unittest.mock import patch

from openpyxl import load_workbook

from nfse import modelo_planilha
from nfse.api import RespostaEmissao
from nfse.assinatura import verificar_assinatura
from nfse.config import Configuracao, Empresa
from nfse.emissor import STATUS_EMITIDA, STATUS_ERRO, Emissor

CHAVE = "35503082" + "2" + "11222333000181" + "0" * 27   # estrutura de chave real

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
NOTA_INVALIDA = dict(NOTA_VALIDA, **{"Descricao do servico": "", "Valor do servico": 0})


def preencher(caminho, linhas: dict, aba="EMPRESA EXEMPLO"):
    livro = load_workbook(caminho)
    folha = livro[aba]
    mapa = {c.value: c.column for c in folha[modelo_planilha.LINHA_TITULOS]}
    for numero_linha, valores in linhas.items():
        for titulo, valor in valores.items():
            folha.cell(row=numero_linha, column=mapa[titulo]).value = valor
    livro.save(caminho)


def resposta_ok(indice=0):
    return RespostaEmissao(chave_acesso=CHAVE, numero_nfse=str(45 + indice),
                           data_processamento="2026-01-15T10:00:00-03:00",
                           xml_nfse=b"<NFSe/>")


# --------------------------------------------------------------------------- #
def test_simulacao_gera_xml_assinado_sem_enviar(config, planilha_modelo, tmp_path):
    preencher(planilha_modelo, {4: NOTA_VALIDA})
    emissor = Emissor(config, diretorio_saida=tmp_path / "saida", simular=True)

    with patch("nfse.api.requests.request") as chamada:
        lote = emissor.emitir_planilha(planilha_modelo)

    chamada.assert_not_called()
    assert len(lote.simuladas) == 1
    xml = open(lote.simuladas[0].arquivo_dps, "rb").read()
    assert verificar_assinatura(xml) is True


def test_emissao_grava_resultado_na_planilha(config, planilha_modelo, tmp_path):
    preencher(planilha_modelo, {4: NOTA_VALIDA})
    emissor = Emissor(config, diretorio_saida=tmp_path / "saida")

    with patch("nfse.emissor.ClienteNFSe") as cliente:
        cliente.return_value.emitir.return_value = resposta_ok()
        lote = emissor.emitir_planilha(planilha_modelo)

    assert len(lote.emitidas) == 1
    folha = load_workbook(planilha_modelo)["EMPRESA EXEMPLO"]
    mapa = {c.value: c.column for c in folha[modelo_planilha.LINHA_TITULOS]}
    assert folha.cell(row=4, column=mapa["Status"]).value == STATUS_EMITIDA
    assert folha.cell(row=4, column=mapa["Chave de acesso"]).value == CHAVE
    assert folha.cell(row=4, column=mapa["Nro. NFS-e"]).value == "45"


def test_uma_linha_ruim_nao_interrompe_o_lote(config, planilha_modelo, tmp_path):
    preencher(planilha_modelo, {4: NOTA_VALIDA, 5: NOTA_INVALIDA, 6: NOTA_VALIDA})
    emissor = Emissor(config, diretorio_saida=tmp_path / "saida")

    with patch("nfse.emissor.ClienteNFSe") as cliente:
        cliente.return_value.emitir.side_effect = [resposta_ok(0), resposta_ok(1)]
        lote = emissor.emitir_planilha(planilha_modelo)

    assert [r.status for r in lote.resultados] == [STATUS_EMITIDA, STATUS_ERRO, STATUS_EMITIDA]
    assert "Descricao do servico" in lote.erros[0].mensagem


def test_numeracao_automatica_e_sequencial(config, planilha_modelo, tmp_path):
    empresa = config.obter("EMPRESA EXEMPLO")
    empresa.proximo_numero = 10
    preencher(planilha_modelo, {4: NOTA_VALIDA, 5: NOTA_VALIDA})
    emissor = Emissor(config, diretorio_saida=tmp_path / "saida")

    with patch("nfse.emissor.ClienteNFSe") as cliente:
        cliente.return_value.emitir.side_effect = [resposta_ok(0), resposta_ok(1)]
        lote = emissor.emitir_planilha(planilha_modelo)
    assert [r.numero_dps for r in lote.resultados] == [10, 11]
    assert config.obter("EMPRESA EXEMPLO").proximo_numero == 12
    # o contador sobrevive ao fechamento do programa
    assert Configuracao.carregar(config.diretorio).obter("EMPRESA EXEMPLO").proximo_numero == 12


def test_simulacao_mostra_a_numeracao_mas_nao_a_consome(config, planilha_modelo, tmp_path):
    empresa = config.obter("EMPRESA EXEMPLO")
    empresa.proximo_numero = 10
    preencher(planilha_modelo, {4: NOTA_VALIDA, 5: NOTA_VALIDA})
    lote = Emissor(config, diretorio_saida=tmp_path / "saida",
                   simular=True).emitir_planilha(planilha_modelo)
    assert [r.numero_dps for r in lote.resultados] == [10, 11]
    assert config.obter("EMPRESA EXEMPLO").proximo_numero == 10
    assert Configuracao.carregar(config.diretorio).obter("EMPRESA EXEMPLO").proximo_numero == 10


def test_numero_da_planilha_tem_prioridade(config, planilha_modelo, tmp_path):
    preencher(planilha_modelo, {4: dict(NOTA_VALIDA, **{"Numero DPS": 500})})
    emissor = Emissor(config, diretorio_saida=tmp_path / "saida", simular=True)
    lote = emissor.emitir_planilha(planilha_modelo)
    assert lote.resultados[0].numero_dps == 500
    assert config.obter("EMPRESA EXEMPLO").proximo_numero == 1


def test_erro_de_validacao_nao_consome_numeracao(config, planilha_modelo, tmp_path):
    preencher(planilha_modelo, {4: NOTA_INVALIDA})
    emissor = Emissor(config, diretorio_saida=tmp_path / "saida", simular=True)
    emissor.emitir_planilha(planilha_modelo)
    assert config.obter("EMPRESA EXEMPLO").proximo_numero == 1


def test_erro_do_portal_consome_a_numeracao(config, planilha_modelo, tmp_path):
    """A nota pode ter chegado ao Portal: reusar o numero arriscaria duplicidade."""
    from nfse.api import ErroDaApi
    preencher(planilha_modelo, {4: NOTA_VALIDA})
    emissor = Emissor(config, diretorio_saida=tmp_path / "saida")

    with patch("nfse.emissor.ClienteNFSe") as cliente:
        cliente.return_value.emitir.side_effect = ErroDaApi("tempo esgotado")
        lote = emissor.emitir_planilha(planilha_modelo)

    assert lote.erros
    assert config.obter("EMPRESA EXEMPLO").proximo_numero == 2


def test_aba_sem_empresa_cadastrada_vira_aviso(config, tmp_path):
    caminho = modelo_planilha.gerar(tmp_path / "m.xlsx", ["EMPRESA DESCONHECIDA"])
    preencher(caminho, {4: NOTA_VALIDA}, aba="EMPRESA DESCONHECIDA")
    lote = Emissor(config, diretorio_saida=tmp_path / "saida",
                   simular=True).emitir_planilha(caminho)
    assert lote.resultados == []
    assert any("nao tem empresa cadastrada" in aviso for aviso in lote.avisos)


def test_empresa_sem_certificado_vira_aviso(tmp_path, planilha_modelo):
    config = Configuracao.carregar(tmp_path / "dados2")
    config.adicionar(Empresa(nome="EMPRESA EXEMPLO", cnpj="11222333000181",
                             codigo_municipio="3550308"))
    preencher(planilha_modelo, {4: NOTA_VALIDA})
    lote = Emissor(config, diretorio_saida=tmp_path / "saida",
                   simular=True).emitir_planilha(planilha_modelo)
    assert lote.resultados == []
    assert any("cadastro incompleto" in aviso for aviso in lote.avisos)


def test_nota_ja_emitida_nao_e_reenviada(config, planilha_modelo, tmp_path):
    preencher(planilha_modelo, {4: dict(NOTA_VALIDA, **{"Status": "EMITIDA",
                                                        "Chave de acesso": CHAVE})})
    emissor = Emissor(config, diretorio_saida=tmp_path / "saida")
    with patch("nfse.emissor.ClienteNFSe") as cliente:
        lote = emissor.emitir_planilha(planilha_modelo)
    cliente.return_value.emitir.assert_not_called()
    assert lote.resultados == []


def test_historico_e_gravado(config, planilha_modelo, tmp_path):
    preencher(planilha_modelo, {4: NOTA_VALIDA})
    saida = tmp_path / "saida"
    Emissor(config, diretorio_saida=saida, simular=True).emitir_planilha(planilha_modelo)
    historico = saida / "empresa_exemplo" / "historico.jsonl"
    assert historico.exists() and "simulacao" in historico.read_text(encoding="utf-8")


def test_certificado_vencido_bloqueia_a_emissao(tmp_path, planilha_modelo):
    from tests.apoio import gerar_pfx
    config = Configuracao.carregar(tmp_path / "dados3")
    empresa = Empresa(nome="EMPRESA EXEMPLO", cnpj="11222333000181",
                      codigo_municipio="3550308")
    config.adicionar(empresa)
    config.guardar_certificado(
        empresa, gerar_pfx(tmp_path / "velho.pfx", dias_validade=-5), "teste123")
    preencher(planilha_modelo, {4: NOTA_VALIDA})

    lote = Emissor(config, diretorio_saida=tmp_path / "saida",
                   simular=True).emitir_planilha(planilha_modelo)
    assert lote.resultados == []
    assert any("venceu" in aviso for aviso in lote.avisos)


def test_cancelamento_simulado_gera_evento_assinado(config, tmp_path):
    empresa = config.obter("EMPRESA EXEMPLO")
    emissor = Emissor(config, diretorio_saida=tmp_path / "saida", simular=True)
    resposta = emissor.cancelar(empresa, CHAVE, "1", "Valor digitado errado na nota")
    assert resposta["simulado"] is True
    arquivo = next((tmp_path / "saida" / "empresa_exemplo").glob("EVENTO-*.xml"))
    assert verificar_assinatura(arquivo.read_bytes()) is True


def test_danfse_opcional_e_baixada(config, planilha_modelo, tmp_path):
    preencher(planilha_modelo, {4: NOTA_VALIDA})
    emissor = Emissor(config, diretorio_saida=tmp_path / "saida")
    with patch("nfse.emissor.ClienteNFSe") as cliente:
        cliente.return_value.emitir.return_value = resposta_ok()
        cliente.return_value.baixar_danfse.return_value = tmp_path / "nota.pdf"
        lote = emissor.emitir_planilha(planilha_modelo, baixar_danfse=True)
    cliente.return_value.baixar_danfse.assert_called_once()
    assert lote.emitidas[0].arquivo_danfse


def test_planilha_bloqueada_nao_perde_as_chaves(config, planilha_modelo, tmp_path):
    """Se o Excel estiver com o arquivo aberto, o resultado vai para um CSV."""
    preencher(planilha_modelo, {4: NOTA_VALIDA})
    saida = tmp_path / "saida"
    emissor = Emissor(config, diretorio_saida=saida)

    with patch("nfse.emissor.ClienteNFSe") as cliente, \
         patch("nfse.emissor.mod_planilha.gravar_resultados",
               side_effect=PermissionError("arquivo aberto no Excel")):
        cliente.return_value.emitir.return_value = resposta_ok()
        lote = emissor.emitir_planilha(planilha_modelo)

    assert len(lote.emitidas) == 1
    assert any("AUTORIZADAS" in aviso and "copie" in aviso for aviso in lote.avisos)
    csv_gerado = next(saida.glob("resultados-*.csv"))
    conteudo = csv_gerado.read_text(encoding="utf-8-sig")
    assert CHAVE in conteudo and "EMITIDA" in conteudo


# --------------------------------------------------------------------------- #
# Nota digitada por cima da linha de exemplo (linha 3)
# --------------------------------------------------------------------------- #
NOTA_REAL_NA_LINHA_3 = dict(NOTA_VALIDA, **{
    "CNPJ/CPF do tomador": "40.036.420/0001-42",
    "Nome/Razao social do tomador": "CLIENTE DE VERDADE LTDA",
    "Descricao do servico": "Exame admissional",
    "Valor do servico": 350,
})


def test_nota_na_linha_de_exemplo_nao_sai_mas_avisa_o_que_fazer(config, planilha_modelo,
                                                                 tmp_path):
    preencher(planilha_modelo, {3: NOTA_REAL_NA_LINHA_3})   # Status continua EXEMPLO
    with patch("nfse.emissor.ClienteNFSe") as cliente:
        lote = Emissor(config, diretorio_saida=tmp_path / "saida").emitir_planilha(planilha_modelo)
    cliente.return_value.emitir.assert_not_called()
    assert lote.resultados == []
    assert any("linha 3" in a and "EXEMPLO" in a for a in lote.avisos)
    from openpyxl.utils import get_column_letter
    from nfse.planilha import COLUNAS, COLUNAS_RESULTADO
    letra = get_column_letter([c.campo for c in COLUNAS + COLUNAS_RESULTADO].index("status") + 1)
    motivo = lote.ignoradas[0][2]
    assert f"{letra}3" in motivo and "apague" in motivo


def test_apagando_a_marca_exemplo_a_linha_3_e_emitida(config, planilha_modelo, tmp_path):
    preencher(planilha_modelo, {3: dict(NOTA_REAL_NA_LINHA_3, Status=None)})
    with patch("nfse.emissor.ClienteNFSe") as cliente:
        cliente.return_value.emitir.return_value = resposta_ok()
        lote = Emissor(config, diretorio_saida=tmp_path / "saida").emitir_planilha(planilha_modelo)
    assert [r.linha for r in lote.emitidas] == [3]


def test_exemplo_intocado_nao_gera_aviso(config, planilha_modelo, tmp_path):
    lote = Emissor(config, diretorio_saida=tmp_path / "saida",
                   simular=True).emitir_planilha(planilha_modelo)
    assert lote.avisos == []
    assert "linha 4" in lote.ignoradas[0][2]



# --------------------------------------------------------------------------- #
# Planilha aberta no Excel
# --------------------------------------------------------------------------- #
def test_emissao_nao_comeca_com_a_planilha_aberta_no_excel(config, planilha_modelo, tmp_path):
    """Sem poder gravar a chave, a nota seria emitida de novo na proxima vez."""
    import pytest
    from nfse.planilha import ErroDePlanilha
    preencher(planilha_modelo, {4: NOTA_VALIDA})
    with patch("nfse.emissor.mod_planilha.planilha_bloqueada", return_value=True), \
         patch("nfse.emissor.ClienteNFSe") as cliente:
        with pytest.raises(ErroDePlanilha, match="aberta no Excel"):
            Emissor(config, diretorio_saida=tmp_path / "saida").emitir_planilha(planilha_modelo)
    cliente.assert_not_called()


def test_simulacao_funciona_com_a_planilha_aberta(config, planilha_modelo, tmp_path):
    preencher(planilha_modelo, {4: NOTA_VALIDA})
    with patch("nfse.emissor.mod_planilha.planilha_bloqueada", return_value=True), \
         patch("nfse.emissor.mod_planilha.gravar_resultados", side_effect=PermissionError("aberta")):
        lote = Emissor(config, diretorio_saida=tmp_path / "saida",
                       simular=True).emitir_planilha(planilha_modelo)
    assert len(lote.simuladas) == 1
    assert any("nao ha risco" in aviso for aviso in lote.avisos)


def test_aviso_da_planilha_nao_sai_duplicado_no_log(config, planilha_modelo, tmp_path):
    preencher(planilha_modelo, {4: NOTA_VALIDA})
    log = []
    with patch("nfse.emissor.mod_planilha.gravar_resultados", side_effect=PermissionError("x")):
        lote = Emissor(config, diretorio_saida=tmp_path / "saida", simular=True,
                       progresso=log.append).emitir_planilha(planilha_modelo)
    # o aviso vai em lote.avisos (a tela mostra); o andamento nao repete
    assert lote.avisos and not any("nao foi gravado" in linha for linha in log)


def test_detecta_arquivo_bloqueado():
    from nfse.planilha import planilha_bloqueada
    with patch("builtins.open", side_effect=PermissionError(13, "Permission denied")):
        assert planilha_bloqueada("qualquer.xlsx") is True
    assert planilha_bloqueada(__file__) is False
