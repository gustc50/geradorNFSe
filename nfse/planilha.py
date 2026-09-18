"""Leitura da planilha de notas.

Regras:
  * cada **aba** da planilha e uma empresa (o nome da aba deve bater com o nome
    cadastrado no sistema);
  * cada **linha** e uma nota fiscal;
  * abas de apoio (LEIA-ME, TABELAS) sao ignoradas;
  * linhas ja emitidas (com chave de acesso preenchida) sao puladas.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from . import tabelas, util
from .dps import Nota

ABAS_DE_APOIO = {"leia_me", "leiame", "instrucoes", "tabelas", "ajuda", "modelo_de_uso"}
MAX_LINHAS_CABECALHO = 12

# Status que indicam nota ja processada - a linha nao e reenviada.
STATUS_JA_PROCESSADO = {"EMITIDA", "OK", "AUTORIZADA", "CANCELADA"}
# Marca da linha de demonstracao da planilha modelo.
MARCA_EXEMPLO = "EXEMPLO"


@dataclass(frozen=True)
class Coluna:
    """Uma coluna da planilha ligada a um campo da nota."""

    campo: str                      # atributo de Nota
    titulo: str                     # texto que aparece na planilha
    grupo: str = ""
    obrigatorio: bool = False
    largura: int = 18
    exemplo: str = ""
    ajuda: str = ""
    dominio: dict | None = None     # tabela de dominio para a validacao
    apelidos: tuple[str, ...] = ()

    @property
    def chave(self) -> str:
        return util.normalizar_chave(self.titulo)


G_ID = "IDENTIFICACAO"
G_TOM = "TOMADOR"
G_END = "ENDERECO DO TOMADOR"
G_EXT = "TOMADOR NO EXTERIOR"
G_SRV = "SERVICO"
G_VAL = "VALORES"
G_ISS = "ISSQN"
G_FED = "TRIBUTOS FEDERAIS"
G_TOT = "TRIBUTOS APROXIMADOS"

COLUNAS: tuple[Coluna, ...] = (
    # ---------------- identificacao ----------------
    Coluna("numero", "Numero DPS", G_ID, False, 12, "",
           "Deixe vazio para o sistema numerar automaticamente.",
           apelidos=("numero", "n_dps", "numero_da_dps", "nro_dps")),
    Coluna("serie", "Serie", G_ID, False, 8, "1",
           "Vazio usa a serie padrao cadastrada na empresa."),
    Coluna("data_emissao", "Data de emissao", G_ID, False, 16, "15/01/2026",
           "dd/mm/aaaa. Vazio usa a data/hora atual.",
           apelidos=("data", "emissao", "dt_emissao")),
    Coluna("competencia", "Competencia", G_ID, False, 14, "01/2026",
           "mm/aaaa ou dd/mm/aaaa. Vazio usa a data de emissao."),

    # ---------------- tomador ----------------
    Coluna("tomador_tipo_documento", "Tipo doc. tomador", G_TOM, True, 18, "CNPJ",
           "CNPJ, CPF, NIF (exterior) ou SEM (nao identificado).",
           dominio=tabelas.TIPO_DOCUMENTO_TOMADOR,
           apelidos=("tipo_documento", "tipo_doc", "tipo_tomador")),
    Coluna("tomador_documento", "CNPJ/CPF do tomador", G_TOM, True, 20,
           "11.444.777/0001-61", "Pode digitar com ou sem pontuacao.",
           apelidos=("cnpj_tomador", "cpf_tomador", "documento_tomador", "cnpj_cpf")),
    Coluna("tomador_nome", "Nome/Razao social do tomador", G_TOM, True, 38,
           "CLIENTE EXEMPLO LTDA", "",
           apelidos=("tomador", "nome_tomador", "razao_social_tomador", "cliente")),
    Coluna("tomador_inscricao_municipal", "Insc. municipal do tomador", G_TOM, False, 20, "",
           "Opcional."),
    Coluna("tomador_email", "E-mail do tomador", G_TOM, False, 28,
           "financeiro@cliente.com.br", "Usado pelo portal para enviar a nota.",
           apelidos=("email", "email_tomador")),
    Coluna("tomador_telefone", "Telefone do tomador", G_TOM, False, 16, "1133334444",
           "Somente numeros, com DDD.", apelidos=("telefone", "fone")),

    # ---------------- endereco ----------------
    Coluna("tomador_cep", "CEP", G_END, False, 12, "01310-100", "8 digitos."),
    Coluna("tomador_codigo_municipio", "Cod. municipio do tomador", G_END, False, 22,
           "3550308", "Codigo IBGE de 7 digitos (Sao Paulo = 3550308).",
           apelidos=("municipio_tomador", "codigo_municipio_tomador", "cod_mun_tomador")),
    Coluna("tomador_logradouro", "Logradouro", G_END, False, 34, "Avenida Paulista",
           "", apelidos=("endereco", "rua")),
    Coluna("tomador_numero", "Numero", G_END, False, 10, "1000",
           "Use S/N quando nao houver.", apelidos=("nro", "numero_endereco")),
    Coluna("tomador_complemento", "Complemento", G_END, False, 20, "Sala 12"),
    Coluna("tomador_bairro", "Bairro", G_END, False, 22, "Bela Vista"),

    # ---------------- exterior ----------------
    Coluna("tomador_codigo_pais", "Pais do tomador", G_EXT, False, 16, "",
           "Somente para tomador no exterior. Codigo ISO de 2 letras (ex.: US).",
           apelidos=("pais_tomador", "cod_pais_tomador")),
    Coluna("tomador_cidade_exterior", "Cidade (exterior)", G_EXT, False, 20),
    Coluna("tomador_estado_exterior", "Estado/Provincia (exterior)", G_EXT, False, 22),
    Coluna("tomador_cep_exterior", "Codigo postal (exterior)", G_EXT, False, 20),

    # ---------------- servico ----------------
    Coluna("codigo_municipio_prestacao", "Cod. municipio da prestacao", G_SRV, False, 24,
           "3550308", "Vazio usa o municipio do emitente.",
           apelidos=("municipio_prestacao", "local_prestacao", "cod_mun_prestacao")),
    Coluna("codigo_pais_prestacao", "Pais da prestacao", G_SRV, False, 16, "",
           "Preencha apenas quando o servico for prestado fora do Brasil."),
    Coluna("codigo_tributacao_nacional", "Cod. tributacao nacional", G_SRV, True, 24,
           "010701", "6 digitos da tabela nacional de servicos (item + subitem).",
           apelidos=("ctribnac", "codigo_servico", "cod_servico", "item_lista_servico")),
    Coluna("codigo_tributacao_municipal", "Cod. tributacao municipal", G_SRV, False, 24, "",
           "Opcional - exigido por alguns municipios.",
           apelidos=("ctribmun", "codigo_municipal")),
    Coluna("descricao_servico", "Descricao do servico", G_SRV, True, 50,
           "Servicos de assessoria contabil referentes a 01/2026",
           "Ate 2000 caracteres.",
           apelidos=("discriminacao", "descricao", "servico")),
    Coluna("codigo_nbs", "Codigo NBS", G_SRV, False, 14, "",
           "Obrigatorio em algumas operacoes com o exterior."),
    Coluna("numero_interno", "Nro. controle interno", G_SRV, False, 18, "",
           "Seu numero de pedido/contrato. Nao vai para a numeracao fiscal.",
           apelidos=("controle_interno", "pedido", "cintcontrib")),
    Coluna("informacoes_complementares", "Informacoes complementares", G_SRV, False, 40, "",
           "Texto livre impresso na nota.",
           apelidos=("obs", "observacoes", "info_complementares")),

    # ---------------- valores ----------------
    Coluna("valor_servico", "Valor do servico", G_VAL, True, 16, "1000,00",
           "Valor bruto da nota.",
           apelidos=("valor", "vlr_servico", "valor_total", "vserv")),
    Coluna("desconto_incondicionado", "Desconto incondicionado", G_VAL, False, 22, "",
           "Reduz a base de calculo do ISS."),
    Coluna("desconto_condicionado", "Desconto condicionado", G_VAL, False, 20, "",
           "Nao reduz a base de calculo do ISS."),
    Coluna("valor_deducoes", "Deducoes", G_VAL, False, 14, "",
           "Materiais/subempreitadas permitidos pelo municipio."),

    # ---------------- ISSQN ----------------
    Coluna("tributacao_issqn", "Tributacao do ISSQN", G_ISS, True, 22, "1",
           "1 tributavel, 2 exportacao, 3 nao incidencia, 4 imunidade.",
           dominio=tabelas.TRIBUTACAO_ISSQN,
           apelidos=("tribissqn", "tributacao_iss")),
    Coluna("aliquota_iss", "Aliquota ISS (%)", G_ISS, False, 16, "2,00",
           "Em percentual: 2 significa 2%.",
           apelidos=("aliquota", "aliq_iss", "paliq")),
    Coluna("iss_retido", "Retencao do ISSQN", G_ISS, True, 22, "1",
           "1 nao retido, 2 retido pelo tomador, 3 retido pelo intermediario.",
           dominio=tabelas.RETENCAO_ISSQN,
           apelidos=("iss_retido", "retencao_iss", "tpretissqn")),
    Coluna("valor_iss_retido", "Valor ISS retido", G_ISS, False, 16, "",
           "Informe quando houver retencao e o valor for diferente do calculado."),
    Coluna("tipo_imunidade", "Tipo de imunidade", G_ISS, False, 20, "",
           "Obrigatorio quando a tributacao do ISSQN for 4.",
           dominio=tabelas.TIPO_IMUNIDADE),
    Coluna("codigo_pais_resultado", "Pais de resultado", G_ISS, False, 18, "",
           "Obrigatorio na exportacao de servico (tributacao 2)."),

    # ---------------- tributos federais ----------------
    Coluna("cst_pis_cofins", "CST PIS/COFINS", G_FED, False, 18, "",
           "Preencha junto com a retencao de PIS/COFINS.",
           dominio=tabelas.CST_PIS_COFINS),
    Coluna("base_pis_cofins", "Base PIS/COFINS", G_FED, False, 18),
    Coluna("aliquota_pis", "Aliquota PIS (%)", G_FED, False, 16, "", "Ex.: 0,65"),
    Coluna("aliquota_cofins", "Aliquota COFINS (%)", G_FED, False, 18, "", "Ex.: 3,00"),
    Coluna("valor_pis", "Valor PIS", G_FED, False, 14, "", apelidos=("pis",)),
    Coluna("valor_cofins", "Valor COFINS", G_FED, False, 16, "", apelidos=("cofins",)),
    Coluna("retencao_pis_cofins", "Retencao PIS/COFINS", G_FED, False, 22, "",
           "1 retido, 2 nao retido.", dominio=tabelas.RETENCAO_PIS_COFINS),
    Coluna("valor_inss", "Valor INSS retido", G_FED, False, 18, "",
           "Retencao previdenciaria (vRetCP).", apelidos=("inss", "vretcp")),
    Coluna("valor_irrf", "Valor IRRF retido", G_FED, False, 18, "", apelidos=("irrf", "ir")),
    Coluna("valor_csll", "Valor CSLL retido", G_FED, False, 18, "", apelidos=("csll",)),

    # ---------------- tributos aproximados ----------------
    Coluna("tributos_federais", "Tributos federais aprox.", G_TOT, False, 22, "",
           "Lei 12.741/2012. Deixe as tres colunas vazias para nao informar."),
    Coluna("tributos_estaduais", "Tributos estaduais aprox.", G_TOT, False, 22),
    Coluna("tributos_municipais", "Tributos municipais aprox.", G_TOT, False, 22),
)

# Colunas preenchidas pelo sistema depois da emissao.
G_RES = "RESULTADO (preenchido pelo sistema)"
COLUNAS_RESULTADO: tuple[Coluna, ...] = (
    Coluna("status", "Status", G_RES, False, 14),
    Coluna("chave_acesso", "Chave de acesso", G_RES, False, 54),
    Coluna("numero_nfse", "Nro. NFS-e", G_RES, False, 14),
    Coluna("processado_em", "Processado em", G_RES, False, 20),
    Coluna("mensagem", "Mensagem", G_RES, False, 60),
)

CAMPOS_DECIMAIS = {
    "valor_servico", "desconto_incondicionado", "desconto_condicionado", "valor_deducoes",
    "aliquota_iss", "valor_iss_retido", "base_pis_cofins", "aliquota_pis", "aliquota_cofins",
    "valor_pis", "valor_cofins", "valor_inss", "valor_irrf", "valor_csll",
    "tributos_federais", "tributos_estaduais", "tributos_municipais",
}
CAMPOS_DOMINIO = {c.campo for c in COLUNAS if c.dominio}


def _indice_de_colunas() -> dict[str, Coluna]:
    indice: dict[str, Coluna] = {}
    for coluna in COLUNAS + COLUNAS_RESULTADO:
        indice[coluna.chave] = coluna
        indice[util.normalizar_chave(coluna.campo)] = coluna
        for apelido in coluna.apelidos:
            indice.setdefault(util.normalizar_chave(apelido), coluna)
    return indice


INDICE_COLUNAS = _indice_de_colunas()


class ErroDePlanilha(Exception):
    """Planilha fora do formato esperado."""


@dataclass
class AbaLida:
    """Resultado da leitura de uma aba."""

    nome: str
    linha_cabecalho: int
    colunas: dict[str, int]          # campo -> indice da coluna (base 1)
    notas: list[Nota]
    ignoradas: list[tuple[int, str]]  # (linha, motivo)
    erros: list[str]


def aba_de_apoio(nome: str) -> bool:
    return util.normalizar_chave(nome) in ABAS_DE_APOIO


def _localizar_cabecalho(planilha) -> tuple[int, dict[str, int]]:
    """Acha a linha de titulos e mapeia campo -> coluna."""
    melhor_linha, melhor_mapa = 0, {}
    limite = min(planilha.max_row or 1, MAX_LINHAS_CABECALHO)
    for numero_linha in range(1, limite + 1):
        mapa: dict[str, int] = {}
        for indice, celula in enumerate(planilha[numero_linha], start=1):
            coluna = INDICE_COLUNAS.get(util.normalizar_chave(celula.value))
            if coluna is not None and coluna.campo not in mapa:
                mapa[coluna.campo] = indice
        if len(mapa) > len(melhor_mapa):
            melhor_linha, melhor_mapa = numero_linha, mapa
    if len(melhor_mapa) < 3:
        raise ErroDePlanilha(
            f"Nao encontrei a linha de titulos na aba {planilha.title!r}. "
            "Use a planilha modelo gerada pelo sistema (menu Planilha > Gerar modelo).")
    return melhor_linha, melhor_mapa


def _converter(coluna: Coluna, valor):
    campo = coluna.campo
    if campo in CAMPOS_DECIMAIS:
        return util.decimal(valor)
    if campo == "numero":
        return util.inteiro(valor)
    if campo == "data_emissao":
        return util.para_datahora(valor)
    if campo == "competencia":
        return util.para_data(valor)
    if campo in CAMPOS_DOMINIO:
        bruto = tabelas.codigo_da_opcao(valor)
        return bruto.upper() if campo == "tomador_tipo_documento" else bruto
    return util.texto(valor)


def ler_aba(planilha, somente_pendentes: bool = True) -> AbaLida:
    """Le uma aba e devolve as notas encontradas."""
    linha_cabecalho, mapa = _localizar_cabecalho(planilha)
    notas: list[Nota] = []
    ignoradas: list[tuple[int, str]] = []
    erros: list[str] = []

    for linha in planilha.iter_rows(min_row=linha_cabecalho + 1, values_only=False):
        numero_linha = linha[0].row if linha else 0
        valores = {}
        for campo, indice in mapa.items():
            celula = linha[indice - 1] if indice - 1 < len(linha) else None
            valores[campo] = celula.value if celula is not None else None

        campos_nota = {k: v for k, v in valores.items()
                       if k in Nota.__dataclass_fields__}
        if all(util.vazio(v) for v in campos_nota.values()):
            continue

        chave = util.texto(valores.get("chave_acesso"))
        status = util.texto(valores.get("status")).upper()

        # A linha de demonstracao da planilha modelo nunca e enviada.
        if status.startswith(MARCA_EXEMPLO):
            ignoradas.append((numero_linha, "linha de exemplo da planilha modelo"))
            continue
        if somente_pendentes and (chave or status in STATUS_JA_PROCESSADO):
            ignoradas.append((numero_linha, f"ja emitida (chave {chave or status})"))
            continue

        nota = Nota(linha=numero_linha, aba=planilha.title)
        nota.dados_originais = {k: v for k, v in valores.items()}
        for campo, bruto in campos_nota.items():
            coluna = next((c for c in COLUNAS if c.campo == campo), None)
            if coluna is None:
                continue
            try:
                setattr(nota, campo, _converter(coluna, bruto))
            except util.ErroDeValidacao as exc:
                erros.append(f"Linha {numero_linha}, coluna {coluna.titulo!r}: {exc}")
        notas.append(nota)

    return AbaLida(nome=planilha.title, linha_cabecalho=linha_cabecalho, colunas=mapa,
                   notas=notas, ignoradas=ignoradas, erros=erros)


def ler(caminho: str | Path, abas: list[str] | None = None,
        somente_pendentes: bool = True) -> dict[str, AbaLida]:
    """Le a planilha inteira. Devolve {nome da aba: AbaLida}."""
    arquivo = Path(caminho).expanduser()
    if not arquivo.exists():
        raise ErroDePlanilha(f"Planilha nao encontrada: {arquivo}")

    livro = load_workbook(arquivo, data_only=True, read_only=False)
    try:
        resultado: dict[str, AbaLida] = {}
        alvos = {util.normalizar_chave(a) for a in abas} if abas else None
        for nome in livro.sheetnames:
            if aba_de_apoio(nome):
                continue
            if alvos is not None and util.normalizar_chave(nome) not in alvos:
                continue
            resultado[nome] = ler_aba(livro[nome], somente_pendentes=somente_pendentes)
        if not resultado:
            raise ErroDePlanilha(
                "Nenhuma aba de empresa encontrada na planilha. "
                "Cada aba deve ter o nome da empresa cadastrada no sistema.")
        return resultado
    finally:
        livro.close()


def gravar_resultados(caminho: str | Path, resultados_por_aba: dict[str, dict[int, dict]]) -> Path:
    """Escreve status/chave/mensagem de volta na planilha de origem.

    ``resultados_por_aba`` = {nome da aba: {numero da linha: {campo: valor}}}
    """
    arquivo = Path(caminho).expanduser()
    livro = load_workbook(arquivo)
    try:
        for nome_aba, linhas in resultados_por_aba.items():
            if nome_aba not in livro.sheetnames or not linhas:
                continue
            planilha = livro[nome_aba]
            linha_cabecalho, mapa = _localizar_cabecalho(planilha)
            proxima_coluna = max(mapa.values()) + 1 if mapa else 1

            for coluna in COLUNAS_RESULTADO:
                if coluna.campo not in mapa:
                    celula = planilha.cell(row=linha_cabecalho, column=proxima_coluna)
                    celula.value = coluna.titulo
                    planilha.column_dimensions[
                        get_column_letter(proxima_coluna)].width = coluna.largura
                    mapa[coluna.campo] = proxima_coluna
                    proxima_coluna += 1

            for numero_linha, dados in linhas.items():
                for campo, valor in dados.items():
                    if campo in mapa:
                        planilha.cell(row=numero_linha, column=mapa[campo]).value = valor
        livro.save(arquivo)
    finally:
        livro.close()
    return arquivo
