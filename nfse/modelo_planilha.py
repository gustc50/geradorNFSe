"""Geracao da planilha modelo.

Estrutura do arquivo gerado:

  LEIA-ME              instrucoes de preenchimento
  TABELAS              listas usadas nas validacoes das celulas
  <NOME DA EMPRESA>    uma aba por empresa; cada linha e uma nota fiscal

Na aba da empresa:
  linha 1  faixa com o nome do grupo de colunas
  linha 2  titulos das colunas (com comentario de ajuda)
  linha 3  exemplo preenchido - nunca e emitido (Status = EXEMPLO)
  linha 4+ suas notas
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from . import tabelas, util
from .planilha import COLUNAS, COLUNAS_RESULTADO, Coluna

ABA_LEIAME = "LEIA-ME"
ABA_TABELAS = "TABELAS"
LINHA_GRUPOS = 1
LINHA_TITULOS = 2
LINHA_EXEMPLO = 3
LINHAS_COM_VALIDACAO = 500

CORES_GRUPO = {
    "IDENTIFICACAO": "1F3864",
    "TOMADOR": "2E5E4E",
    "ENDERECO DO TOMADOR": "3C6E58",
    "TOMADOR NO EXTERIOR": "6B5B2E",
    "SERVICO": "7A3E1D",
    "VALORES": "8C1D40",
    "ISSQN": "5B2C6F",
    "TRIBUTOS FEDERAIS": "1F4E79",
    "TRIBUTOS APROXIMADOS": "555555",
    "RESULTADO (preenchido pelo sistema)": "3F3F3F",
}

AZUL_ESCURO = "1F3864"
CINZA_CLARO = "F2F2F2"
AMARELO_CLARO = "FFF2CC"
BRANCO = "FFFFFF"

FORMATO_MOEDA = 'R$ #,##0.00'
FORMATO_PERCENTUAL = '0.0000'
CAMPOS_MOEDA = {
    "valor_servico", "desconto_incondicionado", "desconto_condicionado", "valor_deducoes",
    "valor_iss_retido", "base_pis_cofins", "valor_pis", "valor_cofins",
    "valor_inss", "valor_irrf", "valor_csll",
    "tributos_federais", "tributos_estaduais", "tributos_municipais",
}
CAMPOS_PERCENTUAL = {"aliquota_iss", "aliquota_pis", "aliquota_cofins", "percentual_simples"}
CAMPOS_TEXTO = {
    "tomador_documento", "tomador_cep", "tomador_codigo_municipio",
    "codigo_municipio_prestacao", "codigo_tributacao_nacional",
    "codigo_tributacao_municipal", "codigo_nbs", "tomador_telefone",
    "tomador_inscricao_municipal", "serie", "cst_pis_cofins",
}

BORDA_FINA = Border(*(Side(style="thin", color="BFBFBF"),) * 4)


# --------------------------------------------------------------------------- #
# Aba TABELAS
# --------------------------------------------------------------------------- #
def _dominios_usados() -> list[tuple[str, dict]]:
    vistos: list[tuple[str, dict]] = []
    for coluna in COLUNAS:
        if coluna.dominio and all(coluna.dominio is not d for _, d in vistos):
            vistos.append((coluna.titulo, coluna.dominio))
    return vistos


def _montar_aba_tabelas(livro: Workbook) -> dict[int, str]:
    """Cria a aba TABELAS e devolve {id da tabela: referencia da faixa}."""
    aba = livro.create_sheet(ABA_TABELAS)
    aba.sheet_properties.tabColor = "808080"
    aba["A1"] = "Listas usadas nas validacoes. Nao apague esta aba."
    aba["A1"].font = Font(bold=True, size=11, color=AZUL_ESCURO)

    referencias: dict[int, str] = {}
    coluna_atual = 1
    for titulo, dominio in _dominios_usados():
        letra = get_column_letter(coluna_atual)
        cabecalho = aba.cell(row=2, column=coluna_atual, value=titulo)
        cabecalho.font = Font(bold=True, color=BRANCO)
        cabecalho.fill = PatternFill("solid", fgColor=AZUL_ESCURO)
        aba.column_dimensions[letra].width = max(len(titulo) + 2, 24)
        for deslocamento, opcao in enumerate(tabelas.opcoes(dominio)):
            aba.cell(row=3 + deslocamento, column=coluna_atual, value=opcao)
        fim = 2 + len(dominio)
        # Sem "=" na frente: e assim que o proprio Excel grava a faixa da lista.
        referencias[id(dominio)] = f"{ABA_TABELAS}!${letra}$3:${letra}${fim}"
        coluna_atual += 1

    aba.sheet_state = "visible"
    return referencias


# --------------------------------------------------------------------------- #
# Aba LEIA-ME
# --------------------------------------------------------------------------- #
LINHAS_LEIAME = [
    ("titulo", "GERADOR DE NFS-e - PADRAO NACIONAL"),
    ("sub", "Como usar esta planilha"),
    ("", ""),
    ("passo", "1. Uma aba por empresa"),
    ("texto", "O nome da aba deve ser igual ao nome da empresa cadastrada no sistema."),
    ("texto", "Para incluir outra empresa, use o menu Planilha > Adicionar aba de empresa."),
    ("", ""),
    ("passo", "2. Uma linha por nota fiscal"),
    ("texto", "Preencha suas notas a partir da linha 4. A linha 3 (cinza) e so um exemplo e NUNCA e emitida."),
    ("texto", "Quer usar a linha 3 para uma nota de verdade? Apague a palavra EXEMPLO da coluna Status "
              f"(coluna {get_column_letter([c.campo for c in COLUNAS + COLUNAS_RESULTADO].index('status') + 1)})."),
    ("texto", "Linhas totalmente vazias sao ignoradas."),
    ("", ""),
    ("passo", "3. Colunas obrigatorias"),
    ("texto", "Os titulos em amarelo sao obrigatorios. Passe o mouse sobre o titulo para ver a ajuda."),
    ("texto", "Numero DPS vazio = o sistema numera sozinho, seguindo o contador da empresa."),
    ("", ""),
    ("passo", "4. Valores e datas"),
    ("texto", "Valores em reais: 1000,00 ou 1000.00. Aliquotas em percentual: 2 significa 2%."),
    ("texto", "Datas no formato dd/mm/aaaa. Competencia aceita mm/aaaa."),
    ("", ""),
    ("passo", "5. Depois da emissao"),
    ("texto", "O sistema grava nesta planilha as colunas Status, Chave de acesso, Nro. NFS-e e Mensagem."),
    ("texto", "Linhas com chave de acesso preenchida NAO sao reenviadas - isso evita nota duplicada."),
    ("texto", "Os XML autorizados e os PDF (DANFSe) ficam na pasta 'saida', separados por empresa."),
    ("", ""),
    ("passo", "6. Antes de emitir de verdade"),
    ("texto", "Teste no ambiente de homologacao (producao restrita). So mude para producao quando conferir o resultado."),
    ("", ""),
    ("aviso", "Nao apague as abas LEIA-ME e TABELAS: elas alimentam as listas de selecao."),
]


def _montar_aba_leiame(livro: Workbook) -> None:
    aba = livro.create_sheet(ABA_LEIAME, 0)
    aba.sheet_properties.tabColor = AZUL_ESCURO
    aba.column_dimensions["A"].width = 118
    aba.sheet_view.showGridLines = False

    estilos = {
        "titulo": (Font(bold=True, size=18, color=AZUL_ESCURO), None),
        "sub": (Font(bold=True, size=12, color="555555"), None),
        "passo": (Font(bold=True, size=12, color=BRANCO),
                  PatternFill("solid", fgColor=AZUL_ESCURO)),
        "texto": (Font(size=11), None),
        "aviso": (Font(bold=True, size=11, color="8C1D40"),
                  PatternFill("solid", fgColor=AMARELO_CLARO)),
        "": (Font(size=11), None),
    }
    for indice, (tipo, texto) in enumerate(LINHAS_LEIAME, start=1):
        celula = aba.cell(row=indice, column=1, value=texto)
        fonte, preenchimento = estilos[tipo]
        celula.font = fonte
        if preenchimento:
            celula.fill = preenchimento
        celula.alignment = Alignment(vertical="center", indent=1 if tipo == "texto" else 0)
        aba.row_dimensions[indice].height = 26 if tipo in ("titulo", "passo") else 16


# --------------------------------------------------------------------------- #
# Aba de empresa
# --------------------------------------------------------------------------- #
def _aplicar_faixa_de_grupos(aba, colunas: tuple[Coluna, ...]) -> None:
    inicio = 1
    while inicio <= len(colunas):
        grupo = colunas[inicio - 1].grupo
        fim = inicio
        while fim < len(colunas) and colunas[fim].grupo == grupo:
            fim += 1
        celula = aba.cell(row=LINHA_GRUPOS, column=inicio, value=grupo)
        celula.font = Font(bold=True, size=10, color=BRANCO)
        celula.fill = PatternFill("solid", fgColor=CORES_GRUPO.get(grupo, "444444"))
        celula.alignment = Alignment(horizontal="center", vertical="center")
        if fim > inicio:
            aba.merge_cells(start_row=LINHA_GRUPOS, start_column=inicio,
                            end_row=LINHA_GRUPOS, end_column=fim)
        for indice in range(inicio, fim + 1):
            destino = aba.cell(row=LINHA_GRUPOS, column=indice)
            destino.fill = PatternFill("solid", fgColor=CORES_GRUPO.get(grupo, "444444"))
        inicio = fim + 1


def montar_aba_empresa(livro: Workbook, nome: str,
                       referencias: dict[int, str] | None = None,
                       com_exemplo: bool = True):
    """Cria (ou recria) a aba de uma empresa com cabecalho, ajuda e validacoes."""
    titulo = nome[:31] or "EMPRESA"
    if titulo in livro.sheetnames:
        del livro[titulo]
    aba = livro.create_sheet(titulo)
    aba.sheet_properties.tabColor = "2E5E4E"

    colunas = COLUNAS + COLUNAS_RESULTADO
    _aplicar_faixa_de_grupos(aba, colunas)

    for indice, coluna in enumerate(colunas, start=1):
        letra = get_column_letter(indice)
        celula = aba.cell(row=LINHA_TITULOS, column=indice, value=coluna.titulo)
        obrigatoria = coluna.obrigatorio
        celula.font = Font(bold=True, size=10,
                           color="8C1D40" if obrigatoria else "1F3864")
        celula.fill = PatternFill("solid",
                                  fgColor=AMARELO_CLARO if obrigatoria else CINZA_CLARO)
        celula.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        celula.border = BORDA_FINA
        aba.column_dimensions[letra].width = coluna.largura

        ajuda = coluna.ajuda or ""
        if coluna.dominio:
            ajuda = (ajuda + "\n" if ajuda else "") + "\n".join(tabelas.opcoes(coluna.dominio))
        if obrigatoria:
            ajuda = "CAMPO OBRIGATORIO\n" + ajuda
        if ajuda:
            celula.comment = Comment(ajuda, "Gerador NFS-e", width=320, height=150)

        # Formato das celulas de dados
        primeira, ultima = LINHA_EXEMPLO, LINHA_EXEMPLO + LINHAS_COM_VALIDACAO
        if coluna.campo in CAMPOS_MOEDA:
            formato = FORMATO_MOEDA
        elif coluna.campo in CAMPOS_PERCENTUAL:
            formato = FORMATO_PERCENTUAL
        elif coluna.campo in CAMPOS_TEXTO:
            formato = "@"
        else:
            formato = None
        if formato:
            for linha in range(primeira, ultima + 1):
                aba.cell(row=linha, column=indice).number_format = formato

        if coluna.dominio and referencias and id(coluna.dominio) in referencias:
            # errorStyle "warning": avisa sobre valor fora da lista, mas deixa
            # digitar so o codigo (ex.: 1), que o sistema tambem entende.
            validacao = DataValidation(
                type="list", formula1=referencias[id(coluna.dominio)],
                allow_blank=True, showDropDown=False,
                showErrorMessage=True, showInputMessage=True, errorStyle="warning")
            validacao.error = ("Escolha um item da lista. O sistema usa apenas o codigo "
                               "antes do tracinho.")
            validacao.errorTitle = "Valor invalido"
            validacao.prompt = coluna.ajuda or "Escolha um item da lista."
            validacao.promptTitle = coluna.titulo
            aba.add_data_validation(validacao)
            validacao.add(f"{letra}{primeira}:{letra}{ultima}")

    if com_exemplo:
        exemplos = {
            "tomador_tipo_documento": "CNPJ - Pessoa juridica brasileira",
            "tributacao_issqn": "1 - Operacao tributavel",
            "iss_retido": "1 - Nao retido",
            # Trava de seguranca: o sistema nunca emite uma linha marcada assim.
            "status": "EXEMPLO - apague esta linha",
        }
        for indice, coluna in enumerate(colunas, start=1):
            valor = exemplos.get(coluna.campo, coluna.exemplo)
            if not valor:
                continue
            celula = aba.cell(row=LINHA_EXEMPLO, column=indice)
            if coluna.campo in CAMPOS_MOEDA or coluna.campo in CAMPOS_PERCENTUAL:
                celula.value = float(util.decimal(valor))
            else:
                celula.value = valor
            celula.font = Font(italic=True, color="7F7F7F")
        for indice in range(1, len(colunas) + 1):   # faixa cinza: e so exemplo
            aba.cell(row=LINHA_EXEMPLO, column=indice).fill = PatternFill(
                "solid", fgColor="E7E6E6")
        aba.cell(row=LINHA_EXEMPLO, column=1).comment = Comment(
            "Linha de exemplo. O sistema NAO emite esta linha porque a coluna "
            "Status esta marcada como EXEMPLO. Apague a linha ou limpe a coluna "
            "Status para usa-la como nota de verdade.",
            "Gerador NFS-e", width=300, height=110)

    aba.freeze_panes = aba.cell(row=LINHA_EXEMPLO, column=5)
    aba.auto_filter.ref = (f"A{LINHA_TITULOS}:"
                           f"{get_column_letter(len(colunas))}{LINHA_TITULOS}")
    aba.row_dimensions[LINHA_TITULOS].height = 34
    return aba


def gerar(destino: str | Path, empresas: list[str] | None = None,
          com_exemplo: bool = True) -> Path:
    """Gera a planilha modelo com uma aba para cada empresa informada."""
    caminho = Path(destino).expanduser()
    caminho.parent.mkdir(parents=True, exist_ok=True)

    livro = Workbook()
    livro.remove(livro.active)
    _montar_aba_leiame(livro)
    referencias = _montar_aba_tabelas(livro)

    for nome in (empresas or ["EMPRESA EXEMPLO"]):
        montar_aba_empresa(livro, nome, referencias, com_exemplo=com_exemplo)

    livro.active = 0
    livro.save(caminho)
    return caminho


def adicionar_empresa(arquivo: str | Path, nome: str, com_exemplo: bool = True) -> Path:
    """Acrescenta a aba de uma empresa a uma planilha que ja existe."""
    caminho = Path(arquivo).expanduser()
    if not caminho.exists():
        return gerar(caminho, [nome], com_exemplo=com_exemplo)

    livro = load_workbook(caminho)
    try:
        if ABA_TABELAS in livro.sheetnames:
            del livro[ABA_TABELAS]
        referencias = _montar_aba_tabelas(livro)
        montar_aba_empresa(livro, nome, referencias, com_exemplo=com_exemplo)
        livro.save(caminho)
    finally:
        livro.close()
    return caminho
