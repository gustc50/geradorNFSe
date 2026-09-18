"""Tabelas de dominio, enderecos dos ambientes e textos de ajuda.

As listas alimentam as validacoes da planilha modelo e as mensagens de erro.
Os codigos seguem o layout nacional da NFS-e (DPS versao 1.00).
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
    "1": "Retido",
    "2": "Nao retido",
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

# CST de PIS/COFINS mais usados na prestacao de servicos.
CST_PIS_COFINS = {
    "00": "Nenhum",
    "01": "Operacao tributavel com aliquota basica",
    "02": "Operacao tributavel com aliquota diferenciada",
    "04": "Operacao tributavel monofasica - revenda a aliquota zero",
    "05": "Operacao tributavel por substituicao tributaria",
    "06": "Operacao tributavel a aliquota zero",
    "07": "Operacao isenta da contribuicao",
    "08": "Operacao sem incidencia da contribuicao",
    "09": "Operacao com suspensao da contribuicao",
}

# Motivos de cancelamento do evento e101101.
MOTIVO_CANCELAMENTO = {
    "1": "Erro na emissao",
    "2": "Servico nao prestado",
    "3": "Erro de assinatura",
    "4": "Duplicidade da nota",
    "5": "Erro de processamento",
}

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
