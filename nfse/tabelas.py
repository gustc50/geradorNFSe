"""Tabelas de dominio, enderecos dos ambientes e textos de ajuda.

As listas alimentam as validacoes da planilha modelo e as mensagens de erro.
Os codigos foram conferidos contra os schemas oficiais do layout nacional
(tiposSimples_v1.01.xsd, incluido na pasta schemas/).
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Ambientes da API do Portal Nacional (Sefin Nacional)
# --------------------------------------------------------------------------- #
AMBIENTES = {
    "producao": {
        "codigo": "1",
        "rotulo": "Producao",
        "api": "https://sefin.nfse.gov.br/sefinnacional",
        "portal": "https://www.nfse.gov.br",
    },
    "homologacao": {
        "codigo": "2",
        "rotulo": "Homologacao (producao restrita)",
        "api": "https://sefin.producaorestrita.nfse.gov.br/SefinNacional",
        "portal": "https://www.producaorestrita.nfse.gov.br",
    },
}

AMBIENTE_PADRAO = "homologacao"


def ambiente(nome: str) -> dict:
    chave = (nome or AMBIENTE_PADRAO).strip().lower()
    if chave in ("1", "prod", "producao", "produção"):
        chave = "producao"
    if chave in ("2", "homolog", "homologacao", "homologação", "teste", "restrita"):
        chave = "homologacao"
    if chave not in AMBIENTES:
        raise ValueError(
            f"Ambiente invalido: {nome!r}. Use 'producao' ou 'homologacao'.")
    return dict(AMBIENTES[chave], chave=chave)


# --------------------------------------------------------------------------- #
# Dominios usados na DPS
# --------------------------------------------------------------------------- #
TIPO_EMITENTE = {
    "1": "Prestador do servico",
    "2": "Tomador do servico",
    "3": "Intermediario do servico",
}

OPCAO_SIMPLES_NACIONAL = {
    "1": "Nao optante",
    "2": "Optante - MEI",
    "3": "Optante - ME/EPP",
}

REGIME_APURACAO_SN = {
    "1": "Tributos federais e municipal pelo Simples Nacional",
    "2": "Tributos federais pelo SN e ISSQN por fora do SN",
    "3": "Tributos federais e municipal fora do SN (excesso de sublimite)",
}

REGIME_ESPECIAL = {
    "0": "Nenhum",
    "1": "Ato cooperado",
    "2": "Estimativa",
    "3": "Microempresa municipal",
    "4": "Notario ou registrador",
    "5": "Profissional autonomo",
    "6": "Sociedade de profissionais",
    "9": "Outros",
}

TRIBUTACAO_ISSQN = {
    "1": "Operacao tributavel",
    "2": "Exportacao de servico",
    "3": "Nao incidencia / nao tributavel",
    "4": "Imunidade",
}

RETENCAO_ISSQN = {
    "1": "Nao retido",
    "2": "Retido pelo tomador",
    "3": "Retido pelo intermediario",
}

RETENCAO_PIS_COFINS = {
    "0": "PIS/COFINS/CSLL nao retidos",
    "1": "PIS/COFINS retidos",
    "2": "PIS/COFINS nao retidos",
    "3": "PIS/COFINS/CSLL retidos",
    "4": "PIS/COFINS retidos, CSLL nao retido",
    "5": "PIS retido, COFINS/CSLL nao retidos",
    "6": "COFINS retido, PIS/CSLL nao retidos",
    "7": "PIS nao retido, COFINS/CSLL retidos",
    "8": "PIS/COFINS nao retidos, CSLL retido",
    "9": "COFINS nao retido, PIS/CSLL retidos",
}

TIPO_IMUNIDADE = {
    "0": "Imunidade (sem determinacao de subtipo)",
    "1": "Patrimonio, renda ou servicos de entes federados",
    "2": "Templos de qualquer culto",
    "3": "Partidos politicos e suas fundacoes, entidades sindicais",
    "4": "Livros, jornais, periodicos e o papel destinado a impressao",
    "5": "Fonogramas e videofonogramas musicais brasileiros",
}

TIPO_DOCUMENTO_TOMADOR = {
    "CNPJ": "Pessoa juridica brasileira",
    "CPF": "Pessoa fisica brasileira",
    "NIF": "Pessoa no exterior (Numero de Identificacao Fiscal)",
    "SEM": "Tomador nao identificado",
}

# CST de PIS/COFINS - lista completa do schema oficial (TSTipoCST).
CST_PIS_COFINS = {
    "00": "Nenhum",
    "01": "Tributavel com aliquota basica",
    "02": "Tributavel com aliquota diferenciada",
    "03": "Tributavel com aliquota por unidade de medida",
    "04": "Tributavel monofasica - revenda a aliquota zero",
    "05": "Tributavel por substituicao tributaria",
    "06": "Tributavel a aliquota zero",
    "07": "Isenta da contribuicao",
    "08": "Sem incidencia da contribuicao",
    "09": "Com suspensao da contribuicao",
    "49": "Outras operacoes de saida",
    "50": "Credito - receita tributada no mercado interno",
    "51": "Credito - receita nao tributada no mercado interno",
    "52": "Credito - receita de exportacao",
    "53": "Credito - receitas tributadas e nao tributadas no MI",
    "54": "Credito - receitas tributadas no MI e de exportacao",
    "55": "Credito - receitas nao tributadas no MI e de exportacao",
    "56": "Credito - receitas tributadas, nao tributadas e exportacao",
    "60": "Credito presumido - receita tributada no MI",
    "61": "Credito presumido - receita nao tributada no MI",
    "62": "Credito presumido - receita de exportacao",
    "63": "Credito presumido - receitas tributadas e nao tributadas no MI",
    "64": "Credito presumido - receitas tributadas no MI e exportacao",
    "65": "Credito presumido - receitas nao tributadas no MI e exportacao",
    "66": "Credito presumido - receitas tributadas, nao tributadas e exportacao",
    "67": "Credito presumido - outras operacoes",
    "70": "Aquisicao sem direito a credito",
    "71": "Aquisicao com isencao",
    "72": "Aquisicao com suspensao",
    "73": "Aquisicao a aliquota zero",
    "74": "Aquisicao sem incidencia da contribuicao",
    "75": "Aquisicao por substituicao tributaria",
    "98": "Outras operacoes de entrada",
    "99": "Outras operacoes",
}

# Motivos de cancelamento do evento e101101 (TSCodJustCanc do schema oficial).
MOTIVO_CANCELAMENTO = {
    "1": "Erro na emissao",
    "2": "Servico nao prestado",
    "9": "Outros",
}

# A descricao do motivo do cancelamento precisa ter de 15 a 255 caracteres.
MOTIVO_MINIMO = 15

SIM_NAO = {"S": "Sim", "N": "Nao"}

# Codigo do evento de cancelamento no layout nacional.
EVENTO_CANCELAMENTO = "101101"


def descrever(tabela: dict, codigo, padrao: str = "") -> str:
    return tabela.get(str(codigo).strip(), padrao)


def validar(tabela: dict, codigo, campo: str, obrigatorio: bool = True) -> str:
    """Valida um codigo contra a tabela de dominio e devolve o valor limpo."""
    valor = "" if codigo is None else str(codigo).strip()
    if not valor:
        if obrigatorio:
            raise ValueError(
                f"{campo} e obrigatorio. Valores aceitos: "
                + ", ".join(f"{k} ({v})" for k, v in tabela.items()))
        return ""
    if valor not in tabela:
        raise ValueError(
            f"{campo} invalido: {codigo!r}. Valores aceitos: "
            + ", ".join(f"{k} ({v})" for k, v in tabela.items()))
    return valor


def opcoes(tabela: dict) -> list[str]:
    """Lista 'codigo - descricao' para as validacoes da planilha."""
    return [f"{k} - {v}" for k, v in tabela.items()]


def codigo_da_opcao(valor) -> str:
    """Extrai o codigo de um texto no formato 'codigo - descricao'."""
    s = "" if valor is None else str(valor).strip()
    if " - " in s:
        s = s.split(" - ", 1)[0].strip()
    return s
