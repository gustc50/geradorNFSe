"""Cadastro das empresas emitentes.

Cada empresa corresponde a uma aba do sistema e a uma aba da planilha.
Os dados ficam em ``dados/empresas.json``; o certificado digital e copiado para
``dados/certificados/`` e a senha e gravada cifrada pelo modulo ``cofre``.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from pathlib import Path

from . import tabelas, util
from .cofre import Cofre

DIRETORIO_PADRAO = Path(os.environ.get("NFSE_DIR_DADOS", "dados"))
ARQUIVO_EMPRESAS = "empresas.json"
PASTA_CERTIFICADOS = "certificados"


class ErroDeConfiguracao(Exception):
    """Dados da empresa incompletos ou invalidos."""


@dataclass
class Empresa:
    """Dados fixos do prestador - o que nao muda de uma nota para outra."""

    nome: str = ""                      # nome da aba (identifica a empresa)
    razao_social: str = ""
    cnpj: str = ""
    inscricao_municipal: str = ""
    codigo_municipio: str = ""          # codigo IBGE de 7 digitos do emitente
    optante_simples: str = "1"          # 1 nao optante, 2 MEI, 3 ME/EPP
    regime_apuracao_sn: str = ""        # obrigatorio quando optante_simples = 3
    percentual_simples: str = ""        # % aproximado dos tributos do SN (ME/EPP)
    regime_especial: str = "0"
    tipo_emitente: str = "1"            # 1 prestador, 2 tomador, 3 intermediario
    ambiente: str = tabelas.AMBIENTE_PADRAO
    layout: str = tabelas.LAYOUT_AUTOMATICO   # automatico | anterior | nt009
    serie_padrao: str = "1"
    proximo_numero: int = 1
    certificado_arquivo: str = ""       # caminho do .pfx dentro de dados/
    certificado_senha: str = ""         # senha cifrada (nunca em texto puro)
    certificado_validade: str = ""      # somente informativo
    certificado_titular: str = ""       # somente informativo
    email: str = ""
    telefone: str = ""
    observacoes: str = ""

    # ------------------------------------------------------------------ #
    @property
    def cnpj_limpo(self) -> str:
        return util.so_alfanumerico(self.cnpj)

    @property
    def rotulo(self) -> str:
        nome = self.razao_social or self.nome
        return f"{nome} ({util.formatar_cnpj(self.cnpj_limpo)})" if self.cnpj_limpo else nome

    def url_api(self) -> str:
        return tabelas.ambiente(self.ambiente)["api"]

    def codigo_ambiente(self) -> str:
        return tabelas.ambiente(self.ambiente)["codigo"]

    def layout_efetivo(self) -> str:
        return tabelas.layout_para(self.ambiente, self.layout)

    def _layout_seguro(self) -> str:
        try:
            return self.layout_efetivo()
        except ValueError:
            return tabelas.LAYOUT_ANTERIOR

    def tem_certificado(self) -> bool:
        return bool(self.certificado_arquivo) and Path(self.certificado_arquivo).exists()

    # ------------------------------------------------------------------ #
    def validar(self) -> list[str]:
        """Devolve a lista de problemas encontrados (vazia quando esta ok)."""
        erros: list[str] = []
        if not util.texto(self.nome):
            erros.append("Nome da empresa (aba) nao informado.")
        if not self.cnpj_limpo:
            erros.append("CNPJ do prestador nao informado.")
        elif len(self.cnpj_limpo) == 14:
            if not util.cnpj_valido(self.cnpj_limpo):
                erros.append(f"CNPJ invalido: {util.formatar_cnpj(self.cnpj_limpo)}")
            elif (util.cnpj_alfanumerico(self.cnpj_limpo)
                  and self._layout_seguro() == tabelas.LAYOUT_ANTERIOR):
                erros.append("CNPJ alfanumerico so e aceito pelo Portal no layout da NT 009 "
                             "(producao a partir de 01/12/2026).")
        elif len(self.cnpj_limpo) == 11:
            if not util.cpf_valido(self.cnpj_limpo):
                erros.append(f"CPF invalido: {util.formatar_cpf(self.cnpj_limpo)}")
        else:
            erros.append("CNPJ/CPF do prestador deve ter 14 ou 11 digitos.")

        municipio = util.so_digitos(self.codigo_municipio)
        if len(municipio) != 7:
            erros.append("Codigo do municipio do emitente deve ter 7 digitos (IBGE).")

        for campo, tabela, rotulo in (
            (self.optante_simples, tabelas.OPCAO_SIMPLES_NACIONAL, "Optante pelo Simples"),
            (self.regime_especial, tabelas.REGIME_ESPECIAL, "Regime especial"),
            (self.tipo_emitente, tabelas.TIPO_EMITENTE, "Tipo de emitente"),
        ):
            try:
                tabelas.validar(tabela, campo, rotulo)
            except ValueError as exc:
                erros.append(str(exc))

        if str(self.optante_simples).strip() == "3" and util.texto(self.percentual_simples):
            try:
                percentual = util.decimal(self.percentual_simples)
                if not Decimal("0") <= percentual < Decimal("100"):
                    raise util.ErroDeValidacao("fora da faixa")
            except util.ErroDeValidacao:
                erros.append("% tributos do Simples deve ser um percentual de 0 a 99,99 "
                             f"(ex.: 6 para 6%): {self.percentual_simples!r}.")
        if str(self.optante_simples).strip() == "3":
            try:
                tabelas.validar(tabelas.REGIME_APURACAO_SN, self.regime_apuracao_sn,
                                "Regime de apuracao do Simples Nacional")
            except ValueError as exc:
                erros.append(str(exc))

        try:
            tabelas.ambiente(self.ambiente)
            tabelas.layout_para(self.ambiente, self.layout)
        except ValueError as exc:
            erros.append(str(exc))

        # Formatos exigidos pelo schema oficial
        if self.inscricao_municipal and len(util.so_digitos(self.inscricao_municipal)) > 15:
            erros.append("Inscricao municipal pode ter no maximo 15 digitos.")
        telefone = util.so_digitos(self.telefone)
        if telefone and not 6 <= len(telefone) <= 20:
            erros.append("Telefone da empresa deve ter de 6 a 20 digitos.")
        if self.email and ("@" not in self.email or len(self.email.strip()) > 80):
            erros.append(f"E-mail da empresa invalido: {self.email!r}.")
        serie = util.texto(self.serie_padrao)
        if serie and not (serie.isdigit() and len(serie) <= 5):
            erros.append(f"Serie padrao deve ter de 1 a 5 digitos: {serie!r}.")

        if not self.certificado_arquivo:
            erros.append("Certificado digital A1 (.pfx) nao cadastrado.")
        elif not Path(self.certificado_arquivo).exists():
            erros.append(f"Arquivo do certificado nao encontrado: {self.certificado_arquivo}")
        if not self.certificado_senha:
            erros.append("Senha do certificado nao cadastrada.")

        return erros


@dataclass
class Configuracao:
    """Conjunto de empresas cadastradas + acesso ao cofre de senhas."""

    diretorio: Path = field(default_factory=lambda: DIRETORIO_PADRAO)
    empresas: list[Empresa] = field(default_factory=list)
    senha_mestre: str | None = None

    def __post_init__(self) -> None:
        self.diretorio = Path(self.diretorio)
        self.diretorio.mkdir(parents=True, exist_ok=True)
        (self.diretorio / PASTA_CERTIFICADOS).mkdir(parents=True, exist_ok=True)
        self._cofre = Cofre(self.diretorio, senha_mestre=self.senha_mestre)

    # ------------------------------------------------------------------ #
    @property
    def arquivo(self) -> Path:
        return self.diretorio / ARQUIVO_EMPRESAS

    @property
    def cofre(self) -> Cofre:
        return self._cofre

    @classmethod
    def carregar(cls, diretorio: str | Path | None = None,
                 senha_mestre: str | None = None) -> "Configuracao":
        cfg = cls(diretorio=Path(diretorio or DIRETORIO_PADRAO), senha_mestre=senha_mestre)
        if cfg.arquivo.exists():
            try:
                bruto = json.loads(cfg.arquivo.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ErroDeConfiguracao(
                    f"O arquivo {cfg.arquivo} esta corrompido: {exc}") from exc
            campos = {f for f in Empresa.__dataclass_fields__}
            for item in bruto.get("empresas", []):
                cfg.empresas.append(Empresa(**{k: v for k, v in item.items() if k in campos}))
        return cfg

    def salvar(self) -> Path:
        dados = {"versao": 1, "empresas": [asdict(e) for e in self.empresas]}
        temporario = self.arquivo.with_suffix(".json.tmp")
        temporario.write_text(
            json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
        temporario.replace(self.arquivo)
        try:
            os.chmod(self.arquivo, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        return self.arquivo

    # ------------------------------------------------------------------ #
    def nomes(self) -> list[str]:
        return [e.nome for e in self.empresas]

    def obter(self, nome: str) -> Empresa | None:
        alvo = util.normalizar_chave(nome)
        for empresa in self.empresas:
            if util.normalizar_chave(empresa.nome) == alvo:
                return empresa
        return None

    def exigir(self, nome: str) -> Empresa:
        empresa = self.obter(nome)
        if empresa is None:
            disponiveis = ", ".join(self.nomes()) or "(nenhuma cadastrada)"
            raise ErroDeConfiguracao(
                f"Empresa {nome!r} nao esta cadastrada. Cadastradas: {disponiveis}")
        return empresa

    def adicionar(self, empresa: Empresa) -> Empresa:
        if self.obter(empresa.nome) is not None:
            raise ErroDeConfiguracao(f"Ja existe uma empresa chamada {empresa.nome!r}.")
        self.empresas.append(empresa)
        return empresa

    def remover(self, nome: str, apagar_certificado: bool = False) -> None:
        empresa = self.exigir(nome)
        if apagar_certificado and empresa.certificado_arquivo:
            caminho = Path(empresa.certificado_arquivo)
            pasta_do_sistema = (self.diretorio / PASTA_CERTIFICADOS).resolve()
            # So apaga a copia que o proprio sistema fez - nunca o arquivo original.
            if caminho.exists() and caminho.resolve().parent == pasta_do_sistema:
                caminho.unlink()
        self.empresas.remove(empresa)

    # ------------------------------------------------------------------ #
    def guardar_certificado(self, empresa: Empresa, arquivo_origem: str | Path,
                            senha: str) -> Empresa:
        """Copia o .pfx para dados/certificados/ e grava a senha cifrada."""
        origem = Path(arquivo_origem).expanduser()
        if not origem.exists():
            raise ErroDeConfiguracao(f"Certificado nao encontrado: {origem}")

        # Confere a senha antes de guardar - evita cadastrar algo que nao abre.
        from .certificado import ler_certificado  # import tardio: evita ciclo
        info = ler_certificado(origem, senha)

        destino = (self.diretorio / PASTA_CERTIFICADOS /
                   f"{util.nome_arquivo_seguro(empresa.nome, 'empresa')}{origem.suffix.lower()}")
        if origem.resolve() != destino.resolve():
            shutil.copy2(origem, destino)
        try:
            os.chmod(destino, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

        empresa.certificado_arquivo = str(destino)
        empresa.certificado_senha = self._cofre.cifrar(senha)
        empresa.certificado_validade = info.validade_fim.strftime("%d/%m/%Y")
        empresa.certificado_titular = info.titular
        if not empresa.cnpj and info.documento:
            empresa.cnpj = info.documento
        if not empresa.razao_social:
            empresa.razao_social = info.titular
        return empresa

    def senha_do_certificado(self, empresa: Empresa) -> str:
        return self._cofre.decifrar(empresa.certificado_senha)

    def proximo_numero_dps(self, empresa: Empresa, consumir: bool = True) -> int:
        numero = max(1, int(empresa.proximo_numero or 1))
        if consumir:
            empresa.proximo_numero = numero + 1
        return numero

    def registrar_numero_usado(self, empresa: Empresa, numero: int) -> None:
        """Mantem o contador sempre a frente do maior numero ja emitido."""
        if numero >= int(empresa.proximo_numero or 1):
            empresa.proximo_numero = numero + 1
