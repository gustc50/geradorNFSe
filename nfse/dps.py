"""Montagem do XML da DPS (Declaracao de Prestacao de Servicos) - layout nacional 1.01.

Uma linha da planilha vira uma instancia de :class:`Nota`; :func:`montar_xml`
transforma a nota + os dados da empresa no XML que sera assinado e enviado.

A ordem dos elementos segue o schema oficial (``schemas/DPS_v1.01.xsd``). Blocos
opcionais so aparecem quando ha informacao para eles.
"""

from __future__ import annotations

import re

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from lxml import etree

from . import tabelas, util
from .config import Empresa
from .util import ErroDeValidacao

NS_NFSE = "http://www.sped.fazenda.gov.br/nfse"
VERSAO_LAYOUT = "1.01"   # mesma versao dos XSD em schemas/
VERSAO_APLICATIVO = "GeradorNFSe1.0"


@dataclass
class Nota:
    """Uma nota fiscal - corresponde a uma linha da planilha."""

    # --- identificacao ---------------------------------------------------
    serie: str = ""
    numero: int | None = None
    data_emissao: datetime | None = None
    competencia: date | None = None

    # --- tomador ---------------------------------------------------------
    tomador_tipo_documento: str = ""        # CNPJ | CPF | NIF | SEM
    tomador_documento: str = ""
    tomador_nome: str = ""
    tomador_inscricao_municipal: str = ""
    tomador_email: str = ""
    tomador_telefone: str = ""
    tomador_cep: str = ""
    tomador_codigo_municipio: str = ""
    tomador_logradouro: str = ""
    tomador_numero: str = ""
    tomador_complemento: str = ""
    tomador_bairro: str = ""
    tomador_codigo_pais: str = ""           # exterior (ex.: US)
    tomador_cidade_exterior: str = ""
    tomador_estado_exterior: str = ""
    tomador_cep_exterior: str = ""

    # --- servico ---------------------------------------------------------
    codigo_municipio_prestacao: str = ""
    codigo_pais_prestacao: str = ""
    codigo_tributacao_nacional: str = ""    # cTribNac (6 digitos)
    codigo_tributacao_municipal: str = ""
    descricao_servico: str = ""
    codigo_nbs: str = ""
    numero_interno: str = ""                # cIntContrib - seu controle interno
    informacoes_complementares: str = ""

    # --- valores ---------------------------------------------------------
    valor_servico: Decimal | None = None
    desconto_incondicionado: Decimal | None = None
    desconto_condicionado: Decimal | None = None
    valor_deducoes: Decimal | None = None

    # --- ISSQN -----------------------------------------------------------
    tributacao_issqn: str = "1"
    aliquota_iss: Decimal | None = None
    iss_retido: str = "1"
    valor_iss_retido: Decimal | None = None
    tipo_imunidade: str = ""
    codigo_pais_resultado: str = ""

    # --- tributos federais ----------------------------------------------
    cst_pis_cofins: str = ""
    base_pis_cofins: Decimal | None = None
    aliquota_pis: Decimal | None = None
    aliquota_cofins: Decimal | None = None
    valor_pis: Decimal | None = None
    valor_cofins: Decimal | None = None
    retencao_pis_cofins: str = ""
    valor_inss: Decimal | None = None       # vRetCP
    valor_irrf: Decimal | None = None
    valor_csll: Decimal | None = None

    # --- totais aproximados de tributos (Lei 12.741/2012) ----------------
    tributos_federais: Decimal | None = None
    tributos_estaduais: Decimal | None = None
    tributos_municipais: Decimal | None = None

    # --- controle --------------------------------------------------------
    linha: int = 0
    aba: str = ""
    dados_originais: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    @property
    def valor_liquido(self) -> Decimal:
        """Valor do servico menos descontos e retencoes."""
        zero = Decimal("0")
        total = util.decimal(self.valor_servico, zero)
        for desconto in (self.desconto_incondicionado, self.desconto_condicionado):
            total -= util.decimal(desconto, zero)
        for retencao in (self.valor_pis, self.valor_cofins, self.valor_inss,
                         self.valor_irrf, self.valor_csll):
            total -= util.decimal(retencao, zero)
        if str(self.iss_retido).strip() in ("2", "3"):
            total -= util.decimal(self.valor_iss_retido, self._iss_calculado())
        return util.arredondar(total)

    def _iss_calculado(self) -> Decimal:
        base = util.decimal(self.valor_servico, Decimal("0"))
        base -= util.decimal(self.desconto_incondicionado, Decimal("0"))
        base -= util.decimal(self.valor_deducoes, Decimal("0"))
        aliquota = util.decimal(self.aliquota_iss, Decimal("0"))
        return util.arredondar(base * aliquota / Decimal("100"))

    def identificacao(self) -> str:
        return f"aba {self.aba!r}, linha {self.linha}"


# --------------------------------------------------------------------------- #
# Validacao
# --------------------------------------------------------------------------- #
def validar(nota: Nota, empresa: Empresa) -> list[str]:
    """Confere a nota antes de gerar o XML. Devolve a lista de problemas."""
    erros: list[str] = []

    def exigir(condicao: bool, mensagem: str) -> None:
        if not condicao:
            erros.append(mensagem)

    # Tomador
    tipo = util.texto(nota.tomador_tipo_documento).upper() or "SEM"
    if tipo not in tabelas.TIPO_DOCUMENTO_TOMADOR:
        erros.append(f"Tipo de documento do tomador invalido: {tipo!r} "
                     f"(use {', '.join(tabelas.TIPO_DOCUMENTO_TOMADOR)}).")
    documento = util.so_digitos(nota.tomador_documento)
    if tipo == "CNPJ":
        exigir(len(documento) == 14 and util.cnpj_valido(documento),
               f"CNPJ do tomador invalido: {nota.tomador_documento!r}.")
    elif tipo == "CPF":
        exigir(len(documento) == 11 and util.cpf_valido(documento),
               f"CPF do tomador invalido: {nota.tomador_documento!r}.")
    elif tipo == "NIF":
        exigir(bool(util.texto(nota.tomador_documento)),
               "NIF do tomador nao informado.")
        exigir(len(util.texto(nota.tomador_documento)) <= 40,
               "NIF do tomador pode ter no maximo 40 caracteres.")
        exigir(bool(util.texto(nota.tomador_codigo_pais)),
               "Codigo do pais do tomador e obrigatorio quando o documento e NIF.")

    if tipo != "SEM":
        exigir(bool(util.texto(nota.tomador_nome)), "Nome/razao social do tomador nao informado.")

    # Endereco nacional: se qualquer campo foi preenchido, exige o conjunto minimo.
    tem_endereco = any(util.texto(v) for v in (
        nota.tomador_logradouro, nota.tomador_numero, nota.tomador_bairro,
        nota.tomador_cep, nota.tomador_codigo_municipio))
    tem_exterior = any(util.texto(v) for v in (
        nota.tomador_cidade_exterior, nota.tomador_cep_exterior, nota.tomador_estado_exterior))
    if tem_exterior:
        # O schema exige o endereco no exterior completo.
        exigir(bool(util.texto(nota.tomador_codigo_pais)), "Pais do tomador nao informado.")
        exigir(bool(util.texto(nota.tomador_cidade_exterior)), "Cidade (exterior) nao informada.")
        exigir(bool(util.texto(nota.tomador_estado_exterior)),
               "Estado/Provincia (exterior) nao informado.")
        exigir(bool(util.texto(nota.tomador_cep_exterior)),
               "Codigo postal (exterior) nao informado.")
        exigir(len(util.texto(nota.tomador_cep_exterior)) <= 11,
               "Codigo postal (exterior) pode ter no maximo 11 caracteres.")
        exigir(bool(util.texto(nota.tomador_logradouro)), "Logradouro do tomador nao informado.")
        exigir(bool(util.texto(nota.tomador_bairro)),
               "Bairro do tomador nao informado (no exterior, use o distrito/regiao).")
    elif tem_endereco and tipo != "NIF":
        exigir(len(util.so_digitos(nota.tomador_codigo_municipio)) == 7,
               "Codigo do municipio do tomador deve ter 7 digitos (IBGE).")
        exigir(len(util.so_digitos(nota.tomador_cep)) == 8,
               "CEP do tomador deve ter 8 digitos.")
        exigir(bool(util.texto(nota.tomador_logradouro)), "Logradouro do tomador nao informado.")
        exigir(bool(util.texto(nota.tomador_numero)), "Numero do endereco do tomador nao informado.")
        exigir(bool(util.texto(nota.tomador_bairro)), "Bairro do tomador nao informado.")

    for campo, rotulo in ((nota.tomador_codigo_pais, "Pais do tomador"),
                          (nota.codigo_pais_prestacao, "Pais da prestacao"),
                          (nota.codigo_pais_resultado, "Pais de resultado")):
        if util.texto(campo):
            exigir(re.fullmatch(r"[A-Za-z]{2}", util.texto(campo)) is not None,
                   f"{rotulo} deve ser o codigo ISO de 2 letras (ex.: US, PT): {campo!r}.")

    telefone = util.so_digitos(nota.tomador_telefone)
    if telefone:
        exigir(6 <= len(telefone) <= 20, "Telefone do tomador deve ter de 6 a 20 digitos.")
    if util.texto(nota.tomador_email):
        exigir("@" in util.texto(nota.tomador_email) and len(util.texto(nota.tomador_email)) <= 80,
               f"E-mail do tomador invalido: {nota.tomador_email!r}.")
    if util.texto(nota.tomador_inscricao_municipal):
        exigir(len(util.so_digitos(nota.tomador_inscricao_municipal)) <= 15,
               "Inscricao municipal do tomador pode ter no maximo 15 digitos.")

    # Servico
    exigir(bool(util.texto_fiscal(nota.descricao_servico)), "Descricao do servico nao informada.")
    if util.texto(nota.codigo_tributacao_municipal):
        exigir(len(util.so_digitos(nota.codigo_tributacao_municipal)) == 3,
               "Codigo de tributacao municipal deve ter 3 digitos: "
               f"{nota.codigo_tributacao_municipal!r}.")
    if util.texto(nota.codigo_nbs):
        exigir(len(util.so_digitos(nota.codigo_nbs)) == 9,
               f"Codigo NBS deve ter 9 digitos: {nota.codigo_nbs!r}.")
    codigo = util.so_digitos(nota.codigo_tributacao_nacional)
    exigir(len(codigo) == 6,
           f"Codigo de tributacao nacional deve ter 6 digitos: {nota.codigo_tributacao_nacional!r}.")
    local = util.so_digitos(nota.codigo_municipio_prestacao) or util.so_digitos(empresa.codigo_municipio)
    if not util.texto(nota.codigo_pais_prestacao):
        exigir(len(local) == 7,
               "Codigo do municipio de prestacao deve ter 7 digitos (IBGE).")

    # Valores
    valor = util.decimal(nota.valor_servico)
    exigir(valor is not None and valor > 0,
           f"Valor do servico deve ser maior que zero: {nota.valor_servico!r}.")

    for campo, tabela, rotulo, obrigatorio in (
        (nota.tributacao_issqn, tabelas.TRIBUTACAO_ISSQN, "Tributacao do ISSQN", True),
        (nota.iss_retido, tabelas.RETENCAO_ISSQN, "Retencao do ISSQN", True),
        (nota.cst_pis_cofins, tabelas.CST_PIS_COFINS, "CST de PIS/COFINS", False),
        (nota.retencao_pis_cofins, tabelas.RETENCAO_PIS_COFINS, "Retencao de PIS/COFINS", False),
        (nota.tipo_imunidade, tabelas.TIPO_IMUNIDADE, "Tipo de imunidade", False),
    ):
        try:
            tabelas.validar(tabela, campo, rotulo, obrigatorio=obrigatorio)
        except ValueError as exc:
            erros.append(str(exc))

    if util.texto(nota.tributacao_issqn) == "4":
        exigir(bool(util.texto(nota.tipo_imunidade)),
               "Tipo de imunidade e obrigatorio quando a tributacao do ISSQN e 4 (imunidade).")
    if util.texto(nota.tributacao_issqn) == "2":
        exigir(bool(util.texto(nota.codigo_pais_resultado)),
               "Codigo do pais de resultado e obrigatorio na exportacao de servico.")

    if util.texto(nota.retencao_pis_cofins) and not util.texto(nota.cst_pis_cofins):
        erros.append("Informe o CST de PIS/COFINS junto com a retencao de PIS/COFINS.")

    # Formatos numericos exigidos pelo schema
    for valor_campo, rotulo in (
        (nota.valor_servico, "Valor do servico"),
        (nota.desconto_incondicionado, "Desconto incondicionado"),
        (nota.desconto_condicionado, "Desconto condicionado"),
        (nota.valor_deducoes, "Deducoes"),
        (nota.base_pis_cofins, "Base PIS/COFINS"),
        (nota.valor_pis, "Valor PIS"), (nota.valor_cofins, "Valor COFINS"),
        (nota.valor_inss, "Valor INSS"), (nota.valor_irrf, "Valor IRRF"),
        (nota.valor_csll, "Valor CSLL"),
        (nota.tributos_federais, "Tributos federais"),
        (nota.tributos_estaduais, "Tributos estaduais"),
        (nota.tributos_municipais, "Tributos municipais"),
    ):
        d = util.decimal(valor_campo)
        if d is not None and d < 0:
            erros.append(f"{rotulo} nao pode ser negativo.")
    aliquota = util.decimal(nota.aliquota_iss)
    if aliquota is not None:
        exigir(Decimal("0") <= aliquota < Decimal("10"),
               f"Aliquota do ISS deve ser informada em percentual, de 0 a 9,99 "
               f"(ex.: 2 para 2%): {nota.aliquota_iss!r}.")
    for valor_campo, rotulo in ((nota.aliquota_pis, "Aliquota PIS"),
                                (nota.aliquota_cofins, "Aliquota COFINS")):
        d = util.decimal(valor_campo)
        if d is not None:
            exigir(Decimal("0") <= d < Decimal("100"),
                   f"{rotulo} deve estar entre 0 e 99,99 (em percentual).")

    # Identificacao
    if util.texto(nota.serie):
        exigir(re.fullmatch(r"\d{1,5}", util.texto(nota.serie)) is not None,
               f"Serie deve ter de 1 a 5 digitos: {nota.serie!r}.")
    if nota.numero is not None:
        exigir(len(str(int(nota.numero))) <= 15, "Numero da DPS pode ter no maximo 15 digitos.")
    if nota.data_emissao and nota.data_emissao > util.agora() + timedelta(minutes=5):
        erros.append(f"Data de emissao no futuro: {nota.data_emissao:%d/%m/%Y %H:%M}. "
                     "O Portal so aceita notas com data ate o momento do envio.")
    if nota.competencia and nota.data_emissao:
        exigir(nota.competencia <= nota.data_emissao.date(),
               "A competencia nao pode ser posterior a data de emissao.")

    descontos = (util.decimal(nota.desconto_incondicionado, Decimal("0"))
                 + util.decimal(nota.desconto_condicionado, Decimal("0")))
    if valor is not None and descontos > valor:
        erros.append("A soma dos descontos e maior que o valor do servico.")

    if nota.numero is not None and int(nota.numero) <= 0:
        erros.append("Numero da DPS deve ser maior que zero.")

    return erros


# --------------------------------------------------------------------------- #
# Identificador da DPS
# --------------------------------------------------------------------------- #
def montar_id(empresa: Empresa, serie: str, numero: int) -> str:
    """Id = 'DPS' + municipio(7) + tipo inscricao(1) + inscricao(14) + serie(5) + numero(15)."""
    municipio = util.so_digitos(empresa.codigo_municipio).zfill(7)[:7]
    inscricao = util.so_digitos(empresa.cnpj)
    tipo_inscricao = "2" if len(inscricao) == 14 else "1"
    return (f"DPS{municipio}{tipo_inscricao}{inscricao.zfill(14)[:14]}"
            f"{util.so_digitos(serie).zfill(5)[:5]}{str(int(numero)).zfill(15)[:15]}")


# --------------------------------------------------------------------------- #
# Montagem do XML
# --------------------------------------------------------------------------- #
def _elemento(pai, nome: str, valor=None):
    filho = etree.SubElement(pai, f"{{{NS_NFSE}}}{nome}")
    if valor is not None:
        filho.text = str(valor)
    return filho


def _opcional(pai, nome: str, valor) -> None:
    """Cria o elemento apenas quando ha conteudo."""
    conteudo = util.texto_fiscal(valor)
    if conteudo:
        _elemento(pai, nome, conteudo)


def _documento_do_tomador(pai, nota: Nota) -> None:
    tipo = util.texto(nota.tomador_tipo_documento).upper() or "SEM"
    if tipo == "SEM":
        return
    if tipo == "NIF":
        _elemento(pai, "NIF", util.texto_fiscal(nota.tomador_documento, 40))
    else:
        _elemento(pai, tipo, util.so_digitos(nota.tomador_documento))


def _endereco_do_tomador(pai, nota: Nota) -> None:
    tem_nacional = any(util.texto(v) for v in (
        nota.tomador_logradouro, nota.tomador_cep, nota.tomador_codigo_municipio))
    tem_exterior = any(util.texto(v) for v in (
        nota.tomador_cidade_exterior, nota.tomador_cep_exterior))
    if not (tem_nacional or tem_exterior):
        return

    endereco = _elemento(pai, "end")
    if tem_exterior and util.texto(nota.tomador_codigo_pais):
        exterior = _elemento(endereco, "endExt")
        _elemento(exterior, "cPais", util.texto(nota.tomador_codigo_pais).upper())
        _elemento(exterior, "cEndPost", util.texto_fiscal(nota.tomador_cep_exterior, 11))
        _elemento(exterior, "xCidade", util.texto_fiscal(nota.tomador_cidade_exterior, 60))
        _elemento(exterior, "xEstProvReg", util.texto_fiscal(nota.tomador_estado_exterior, 60))
    else:
        nacional = _elemento(endereco, "endNac")
        _elemento(nacional, "cMun", util.so_digitos(nota.tomador_codigo_municipio).zfill(7))
        _elemento(nacional, "CEP", util.so_digitos(nota.tomador_cep).zfill(8))

    _elemento(endereco, "xLgr", util.texto_fiscal(nota.tomador_logradouro, 255))
    _elemento(endereco, "nro", util.texto_fiscal(nota.tomador_numero, 60) or "S/N")
    _opcional(endereco, "xCpl", util.texto_fiscal(nota.tomador_complemento, 156))
    _elemento(endereco, "xBairro", util.texto_fiscal(nota.tomador_bairro, 60))


def _bloco_prestador(pai, empresa: Empresa) -> None:
    prestador = _elemento(pai, "prest")
    inscricao = util.so_digitos(empresa.cnpj)
    _elemento(prestador, "CNPJ" if len(inscricao) == 14 else "CPF", inscricao)
    _opcional(prestador, "IM", util.so_digitos(empresa.inscricao_municipal))
    _opcional(prestador, "fone", util.so_digitos(empresa.telefone))
    _opcional(prestador, "email", util.texto_fiscal(empresa.email, 80))

    regime = _elemento(prestador, "regTrib")
    _elemento(regime, "opSimpNac", util.texto(empresa.optante_simples) or "1")
    if util.texto(empresa.optante_simples) == "3":
        _elemento(regime, "regApTribSN", util.texto(empresa.regime_apuracao_sn))
    _elemento(regime, "regEspTrib", util.texto(empresa.regime_especial) or "0")


def _bloco_tomador(pai, nota: Nota) -> None:
    tipo = util.texto(nota.tomador_tipo_documento).upper() or "SEM"
    if tipo == "SEM":
        # Tomador nao identificado: o grupo <toma> nao pode existir sem documento.
        return
    tomador = _elemento(pai, "toma")
    _documento_do_tomador(tomador, nota)
    _opcional(tomador, "IM", util.so_digitos(nota.tomador_inscricao_municipal))
    _opcional(tomador, "xNome", util.texto_fiscal(nota.tomador_nome, 300))
    _endereco_do_tomador(tomador, nota)
    _opcional(tomador, "fone", util.so_digitos(nota.tomador_telefone))
    _opcional(tomador, "email", util.texto_fiscal(nota.tomador_email, 80))


def _bloco_servico(pai, nota: Nota, empresa: Empresa) -> None:
    servico = _elemento(pai, "serv")

    local = _elemento(servico, "locPrest")
    if util.texto(nota.codigo_pais_prestacao):
        _elemento(local, "cPaisPrestacao", util.texto(nota.codigo_pais_prestacao).upper())
    else:
        municipio = (util.so_digitos(nota.codigo_municipio_prestacao)
                     or util.so_digitos(empresa.codigo_municipio))
        _elemento(local, "cLocPrestacao", municipio.zfill(7))

    codigo = _elemento(servico, "cServ")
    _elemento(codigo, "cTribNac", util.so_digitos(nota.codigo_tributacao_nacional).zfill(6))
    _opcional(codigo, "cTribMun", util.so_digitos(nota.codigo_tributacao_municipal))
    _elemento(codigo, "xDescServ",
              util.texto_fiscal(nota.descricao_servico, 2000, quebras=True))
    _opcional(codigo, "cNBS", util.so_digitos(nota.codigo_nbs))
    # O schema so aceita letras e numeros aqui: "PED-77" vira "PED77".
    _opcional(codigo, "cIntContrib", re.sub(r"[^A-Za-z0-9]", "", util.texto(nota.numero_interno))[:20])

    informacoes = util.texto_fiscal(nota.informacoes_complementares, 2000)
    if informacoes:
        complemento = _elemento(servico, "infoCompl")
        _elemento(complemento, "xInfComp", informacoes)


def _bloco_issqn(pai, nota: Nota) -> None:
    municipal = _elemento(pai, "tribMun")
    tributacao = util.texto(nota.tributacao_issqn) or "1"
    _elemento(municipal, "tribISSQN", tributacao)
    _opcional(municipal, "cPaisResult", util.texto(nota.codigo_pais_resultado).upper())
    if tributacao == "4":
        _elemento(municipal, "tpImunidade", util.texto(nota.tipo_imunidade))
    # Ordem do schema: tpRetISSQN vem ANTES de pAliq.
    _elemento(municipal, "tpRetISSQN", util.texto(nota.iss_retido) or "1")
    if util.decimal(nota.aliquota_iss) is not None:
        _elemento(municipal, "pAliq", util.percentual(nota.aliquota_iss))


def _bloco_tributos_federais(pai, nota: Nota) -> None:
    tem_piscofins = bool(util.texto(nota.cst_pis_cofins))
    retencoes = [nota.valor_inss, nota.valor_irrf, nota.valor_csll]
    tem_retencao = any(util.decimal(v) is not None for v in retencoes)
    if not (tem_piscofins or tem_retencao):
        return

    federal = _elemento(pai, "tribFed")
    if tem_piscofins:
        piscofins = _elemento(federal, "piscofins")
        _elemento(piscofins, "CST", util.texto(nota.cst_pis_cofins).zfill(2))
        if util.decimal(nota.base_pis_cofins) is not None:
            _elemento(piscofins, "vBCPisCofins", util.moeda(nota.base_pis_cofins))
        if util.decimal(nota.aliquota_pis) is not None:
            _elemento(piscofins, "pAliqPis", util.percentual(nota.aliquota_pis))
        if util.decimal(nota.aliquota_cofins) is not None:
            _elemento(piscofins, "pAliqCofins", util.percentual(nota.aliquota_cofins))
        if util.decimal(nota.valor_pis) is not None:
            _elemento(piscofins, "vPis", util.moeda(nota.valor_pis))
        if util.decimal(nota.valor_cofins) is not None:
            _elemento(piscofins, "vCofins", util.moeda(nota.valor_cofins))
        _opcional(piscofins, "tpRetPisCofins", util.texto(nota.retencao_pis_cofins))

    for nome, valor in (("vRetCP", nota.valor_inss),
                        ("vRetIRRF", nota.valor_irrf),
                        ("vRetCSLL", nota.valor_csll)):
        if util.decimal(valor) is not None:
            _elemento(federal, nome, util.moeda(valor))


def _bloco_total_tributos(pai, nota: Nota) -> None:
    total = _elemento(pai, "totTrib")
    valores = [nota.tributos_federais, nota.tributos_estaduais, nota.tributos_municipais]
    if any(util.decimal(v) is not None for v in valores):
        detalhe = _elemento(total, "vTotTrib")
        _elemento(detalhe, "vTotTribFed", util.moeda(nota.tributos_federais))
        _elemento(detalhe, "vTotTribEst", util.moeda(nota.tributos_estaduais))
        _elemento(detalhe, "vTotTribMun", util.moeda(nota.tributos_municipais))
    else:
        # 0 = nao informa os tributos aproximados nesta nota.
        _elemento(total, "indTotTrib", "0")


def _bloco_valores(pai, nota: Nota) -> None:
    valores = _elemento(pai, "valores")

    prestacao = _elemento(valores, "vServPrest")
    _elemento(prestacao, "vServ", util.moeda(nota.valor_servico))

    incondicionado = util.decimal(nota.desconto_incondicionado)
    condicionado = util.decimal(nota.desconto_condicionado)
    if incondicionado is not None or condicionado is not None:
        descontos = _elemento(valores, "vDescCondIncond")
        if incondicionado is not None:
            _elemento(descontos, "vDescIncond", util.moeda(incondicionado))
        if condicionado is not None:
            _elemento(descontos, "vDescCond", util.moeda(condicionado))

    deducoes = util.decimal(nota.valor_deducoes)
    if deducoes is not None and deducoes > 0:
        bloco = _elemento(valores, "vDedRed")
        _elemento(bloco, "vDR", util.moeda(deducoes))

    tributos = _elemento(valores, "trib")
    _bloco_issqn(tributos, nota)
    _bloco_tributos_federais(tributos, nota)
    _bloco_total_tributos(tributos, nota)


def montar_xml(nota: Nota, empresa: Empresa, *, validar_antes: bool = True) -> tuple[bytes, str]:
    """Monta o XML da DPS (ainda sem assinatura). Devolve (xml, id_dps)."""
    if validar_antes:
        problemas = validar(nota, empresa)
        if problemas:
            raise ErroDeValidacao(
                f"Nota da {nota.identificacao()} com problemas:\n  - "
                + "\n  - ".join(problemas))

    serie = util.texto(nota.serie) or util.texto(empresa.serie_padrao) or "1"
    numero = int(nota.numero or 1)
    emissao = nota.data_emissao or util.agora()
    competencia = nota.competencia or emissao.date()
    id_dps = montar_id(empresa, serie, numero)

    raiz = etree.Element(f"{{{NS_NFSE}}}DPS", nsmap={None: NS_NFSE}, versao=VERSAO_LAYOUT)
    info = etree.SubElement(raiz, f"{{{NS_NFSE}}}infDPS", Id=id_dps)

    _elemento(info, "tpAmb", empresa.codigo_ambiente())
    _elemento(info, "dhEmi", util.datahora_xml(emissao))
    _elemento(info, "verAplic", VERSAO_APLICATIVO)
    _elemento(info, "serie", util.so_digitos(serie).zfill(5))
    _elemento(info, "nDPS", str(numero))
    _elemento(info, "dCompet", util.data_xml(competencia))
    _elemento(info, "tpEmit", util.texto(empresa.tipo_emitente) or "1")
    _elemento(info, "cLocEmi", util.so_digitos(empresa.codigo_municipio).zfill(7))

    _bloco_prestador(info, empresa)
    _bloco_tomador(info, nota)
    _bloco_servico(info, nota, empresa)
    _bloco_valores(info, nota)

    return etree.tostring(raiz, encoding="UTF-8", xml_declaration=True), id_dps


# --------------------------------------------------------------------------- #
# Evento de cancelamento (e101101)
# --------------------------------------------------------------------------- #
def montar_evento_cancelamento(empresa: Empresa, chave_acesso: str,
                               codigo_motivo: str, motivo: str) -> tuple[bytes, str]:
    """Monta o XML do pedido de registro do evento de cancelamento."""
    chave = util.so_digitos(chave_acesso)
    if len(chave) != 50:
        raise ErroDeValidacao(
            f"Chave de acesso da NFS-e deve ter 50 digitos (recebida: {len(chave)}).")
    codigo = tabelas.validar(tabelas.MOTIVO_CANCELAMENTO, codigo_motivo, "Motivo do cancelamento")
    descricao = util.texto_fiscal(motivo, 255)
    if len(descricao) < tabelas.MOTIVO_MINIMO:
        raise ErroDeValidacao(
            f"Descreva o motivo do cancelamento com pelo menos {tabelas.MOTIVO_MINIMO} "
            f"caracteres (o Portal exige). Recebido: {descricao!r}.")

    # Id = "PRE" + chave de acesso (50) + codigo do evento (6) = 59 caracteres.
    id_evento = f"PRE{chave}{tabelas.EVENTO_CANCELAMENTO}"

    raiz = etree.Element(f"{{{NS_NFSE}}}pedRegEvento", nsmap={None: NS_NFSE},
                         versao=VERSAO_LAYOUT)
    info = etree.SubElement(raiz, f"{{{NS_NFSE}}}infPedReg", Id=id_evento)
    _elemento(info, "tpAmb", empresa.codigo_ambiente())
    _elemento(info, "verAplic", VERSAO_APLICATIVO)
    _elemento(info, "dhEvento", util.datahora_xml(util.agora()))
    inscricao = util.so_digitos(empresa.cnpj)
    _elemento(info, "CNPJAutor" if len(inscricao) == 14 else "CPFAutor", inscricao)
    _elemento(info, "chNFSe", chave)

    evento = _elemento(info, f"e{tabelas.EVENTO_CANCELAMENTO}")
    _elemento(evento, "xDesc", "Cancelamento de NFS-e")
    _elemento(evento, "cMotivo", codigo)
    _elemento(evento, "xMotivo", descricao)

    return etree.tostring(raiz, encoding="UTF-8", xml_declaration=True), id_evento
