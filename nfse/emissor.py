"""Orquestracao da emissao em lote.

Fluxo de cada linha da planilha:

    1. validar os dados               (nfse.dps.validar)
    2. montar o XML da DPS            (nfse.dps.montar_xml)
    3. assinar com o certificado A1   (nfse.assinatura)
    4. enviar ao Portal Nacional      (nfse.api)
    5. guardar XML/DANFSe e anotar o resultado na planilha

Notas ja emitidas (com chave de acesso na planilha) sao puladas.
"""

from __future__ import annotations

import csv
import json
import traceback
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable

from . import assinatura, dps, esquema, planilha as mod_planilha, tabelas, util
from .api import ClienteNFSe, ErroDaApi
from .certificado import ErroDeCertificado, InfoCertificado, ler_certificado
from .config import Configuracao, Empresa
from .util import ErroDeValidacao

STATUS_EMITIDA = "EMITIDA"
STATUS_ERRO = "ERRO"
STATUS_SIMULADA = "SIMULADA"

# Elementos que mudaram de lugar entre o layout anterior e a NT 009. Uma recusa
# de schema (E1235) citando um deles indica que o Portal espera o OUTRO layout.
ELEMENTOS_DE_LAYOUT = ("finNFSe", "cMotivoEmisTI", "chNFSeRej", "xDescServ", "cNBS",
                       "cIntContrib", "vDedRed", "vAjusteBC", "cLocEmi")

Progresso = Callable[[str], None]


@dataclass
class ResultadoNota:
    """O que aconteceu com uma linha da planilha."""

    aba: str
    linha: int
    status: str = ""
    numero_dps: int | None = None
    chave_acesso: str = ""
    numero_nfse: str = ""
    mensagem: str = ""
    processado_em: str = ""
    arquivo_dps: str = ""
    arquivo_nfse: str = ""
    arquivo_danfse: str = ""
    tomador: str = ""
    valor: str = ""

    @property
    def sucesso(self) -> bool:
        return self.status in (STATUS_EMITIDA, STATUS_SIMULADA)


@dataclass
class ResultadoLote:
    """Resumo da execucao completa."""

    resultados: list[ResultadoNota] = field(default_factory=list)
    ignoradas: list[tuple[str, int, str]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    planilha: str = ""

    @property
    def emitidas(self) -> list[ResultadoNota]:
        return [r for r in self.resultados if r.status == STATUS_EMITIDA]

    @property
    def simuladas(self) -> list[ResultadoNota]:
        return [r for r in self.resultados if r.status == STATUS_SIMULADA]

    @property
    def erros(self) -> list[ResultadoNota]:
        return [r for r in self.resultados if r.status == STATUS_ERRO]

    def resumo(self) -> str:
        partes = [f"{len(self.emitidas)} emitida(s)"]
        if self.simuladas:
            partes.append(f"{len(self.simuladas)} simulada(s)")
        if self.erros:
            partes.append(f"{len(self.erros)} com erro")
        if self.ignoradas:
            partes.append(f"{len(self.ignoradas)} ignorada(s)")
        return ", ".join(partes)


class Emissor:
    """Emite as notas de uma planilha, empresa por empresa."""

    def __init__(self, config: Configuracao, diretorio_saida: str | Path = "saida",
                 simular: bool = False, progresso: Progresso | None = None):
        self.config = config
        self.diretorio_saida = Path(diretorio_saida)
        self.diretorio_saida.mkdir(parents=True, exist_ok=True)
        self.simular = simular
        self.progresso = progresso or (lambda _: None)
        # Layout que o Portal ja aceitou nesta execucao, por (empresa, ambiente).
        self._layout_confirmado: dict[tuple[str, str], str] = {}

    # ------------------------------------------------------------------ #
    def _avisar(self, mensagem: str) -> None:
        self.progresso(mensagem)

    def _pasta_da_empresa(self, empresa: Empresa) -> Path:
        pasta = self.diretorio_saida / util.nome_arquivo_seguro(empresa.nome, "empresa")
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta

    def _registrar_log(self, empresa: Empresa, registro: dict) -> None:
        arquivo = self._pasta_da_empresa(empresa) / "historico.jsonl"
        registro = dict(registro, momento=util.agora().isoformat())
        with arquivo.open("a", encoding="utf-8") as saida:
            saida.write(json.dumps(registro, ensure_ascii=False, default=str) + "\n")

    def abrir_certificado(self, empresa: Empresa) -> InfoCertificado:
        """Abre o certificado da empresa usando a senha guardada no cofre."""
        senha = self.config.senha_do_certificado(empresa)
        info = ler_certificado(empresa.certificado_arquivo, senha)
        if info.vencido:
            raise ErroDeCertificado(
                f"O certificado de {empresa.nome} venceu em "
                f"{info.validade_fim:%d/%m/%Y}. Cadastre o certificado novo.")
        if info.dias_para_vencer <= 30:
            self._avisar(
                f"[aviso] O certificado de {empresa.nome} vence em "
                f"{info.dias_para_vencer} dia(s).")
        return info

    # ------------------------------------------------------------------ #
    def layout_da_empresa(self, empresa: Empresa) -> str:
        chave = (empresa.nome, empresa.ambiente)
        return self._layout_confirmado.get(chave) or empresa.layout_efetivo()

    @staticmethod
    def _recusa_por_layout(exc: ErroDaApi) -> bool:
        """O Portal recusou o schema por causa de um campo que mudou na NT 009?"""
        texto = exc.detalhado()
        return (exc.status == 400 and "E1235" in texto
                and any(elemento in texto for elemento in ELEMENTOS_DE_LAYOUT))

    @staticmethod
    def _preparar_xml(nota: dps.Nota, empresa: Empresa, certificado: InfoCertificado,
                      layout: str) -> tuple[bytes, str]:
        """Monta, assina, confere a assinatura e valida no XSD do layout."""
        xml_dps, id_dps = dps.montar_xml(nota, empresa, layout=layout)
        xml_assinado = assinatura.assinar_xml(xml_dps, id_dps, certificado)
        assinatura.verificar_assinatura(xml_assinado)   # autoteste antes de enviar
        problemas_xsd = esquema.validar(xml_assinado, "DPS", layout=layout)
        if problemas_xsd:
            raise ErroDeValidacao(
                "O XML nao bate com o schema oficial: " + "; ".join(problemas_xsd))
        return xml_assinado, id_dps

    def emitir_nota(self, empresa: Empresa, certificado: InfoCertificado,
                    nota: dps.Nota, cliente: ClienteNFSe | None = None) -> ResultadoNota:
        """Emite uma unica nota. Nunca levanta excecao: devolve o resultado."""
        resultado = ResultadoNota(aba=nota.aba or empresa.nome, linha=nota.linha,
                                  tomador=util.texto(nota.tomador_nome),
                                  valor=util.moeda(nota.valor_servico))
        numero_automatico = nota.numero is None
        if numero_automatico:
            nota.numero = self.config.proximo_numero_dps(empresa, consumir=True)
        resultado.numero_dps = nota.numero

        pasta = self._pasta_da_empresa(empresa)
        try:
            layout = self.layout_da_empresa(empresa)
            xml_assinado, id_dps = self._preparar_xml(nota, empresa, certificado, layout)

            arquivo_dps = pasta / f"DPS-{id_dps}.xml"
            arquivo_dps.write_bytes(xml_assinado)
            resultado.arquivo_dps = str(arquivo_dps)

            if self.simular:
                resultado.status = STATUS_SIMULADA
                resultado.mensagem = "Simulacao: XML gerado e assinado, nada foi enviado."
                resultado.processado_em = util.agora().strftime("%d/%m/%Y %H:%M:%S")
                self._avisar(f"  [simulado] linha {nota.linha}: DPS {nota.numero} gerada.")
                self._registrar_log(empresa, {"acao": "simulacao", **asdict(resultado)})
                return resultado

            cliente = cliente or ClienteNFSe(empresa, certificado)
            try:
                resposta = cliente.emitir(xml_assinado)
            except ErroDaApi as exc:
                # Recusa de schema por layout: a DPS NAO foi aceita, entao e seguro
                # reenviar uma unica vez no outro layout, com o mesmo numero.
                automatico = (empresa.layout or tabelas.LAYOUT_AUTOMATICO) == \
                    tabelas.LAYOUT_AUTOMATICO
                if not (automatico and self._recusa_por_layout(exc)):
                    raise
                novo = tabelas.outro_layout(layout)
                self._avisar(
                    f"  [aviso] linha {nota.linha}: o Portal recusou o layout "
                    f"'{tabelas.LAYOUTS[layout]}'. Reenviando no layout "
                    f"'{tabelas.LAYOUTS[novo]}'.")
                xml_assinado, id_dps = self._preparar_xml(nota, empresa, certificado, novo)
                arquivo_dps.write_bytes(xml_assinado)
                try:
                    resposta = cliente.emitir(xml_assinado)
                except ErroDaApi as exc2:
                    raise ErroDaApi(
                        f"{exc2.detalhado()} || Antes, no layout '{tabelas.LAYOUTS[layout]}': "
                        f"{exc.detalhado()}", status=exc2.status) from exc2
                self._layout_confirmado[(empresa.nome, empresa.ambiente)] = novo

            resultado.status = STATUS_EMITIDA
            resultado.chave_acesso = resposta.chave_acesso
            resultado.numero_nfse = resposta.numero_nfse
            resultado.processado_em = (resposta.data_processamento
                                       or util.agora().strftime("%d/%m/%Y %H:%M:%S"))
            resultado.mensagem = "NFS-e autorizada."

            if resposta.xml_nfse:
                arquivo_nfse = pasta / f"NFSE-{resposta.chave_acesso}.xml"
                arquivo_nfse.write_bytes(resposta.xml_nfse)
                resultado.arquivo_nfse = str(arquivo_nfse)

            self.config.registrar_numero_usado(empresa, int(nota.numero))
            self._avisar(f"  [ok] linha {nota.linha}: NFS-e {resultado.numero_nfse or ''} "
                         f"chave {resposta.chave_acesso}")
            self._registrar_log(empresa, {"acao": "emissao", **asdict(resultado)})
            return resultado

        except ErroDeValidacao as exc:
            if numero_automatico:          # nao gastou numero: devolve ao contador
                empresa.proximo_numero = max(1, int(empresa.proximo_numero) - 1)
            resultado.status = STATUS_ERRO
            resultado.mensagem = " | ".join(
                parte.strip(" -") for parte in str(exc).splitlines() if parte.strip(" -"))
        except ErroDaApi as exc:
            # O numero permanece consumido: a nota pode ter chegado ao Portal.
            self.config.registrar_numero_usado(empresa, int(nota.numero))
            resultado.status = STATUS_ERRO
            resultado.mensagem = exc.detalhado()
        except (ErroDeCertificado, assinatura.ErroDeAssinatura) as exc:
            if numero_automatico:
                empresa.proximo_numero = max(1, int(empresa.proximo_numero) - 1)
            resultado.status = STATUS_ERRO
            resultado.mensagem = str(exc)
        except Exception as exc:  # noqa: BLE001 - uma linha ruim nao para o lote
            resultado.status = STATUS_ERRO
            resultado.mensagem = f"Erro inesperado: {exc}"
            self._registrar_log(empresa, {"acao": "erro_inesperado", "linha": nota.linha,
                                          "traceback": traceback.format_exc()})

        resultado.processado_em = util.agora().strftime("%d/%m/%Y %H:%M:%S")
        self._avisar(f"  [erro] linha {nota.linha}: {resultado.mensagem}")
        self._registrar_log(empresa, {"acao": "falha", **asdict(resultado)})
        return resultado

    # ------------------------------------------------------------------ #
    def emitir_planilha(self, caminho: str | Path, abas: list[str] | None = None,
                        somente_pendentes: bool = True,
                        gravar_na_planilha: bool = True,
                        baixar_danfse: bool = False) -> ResultadoLote:
        """Le a planilha e emite as notas de todas as abas (ou das abas pedidas)."""
        lote = ResultadoLote(planilha=str(caminho))
        leitura = mod_planilha.ler(caminho, abas=abas, somente_pendentes=somente_pendentes)

        for nome_aba, aba in leitura.items():
            lote.ignoradas.extend((nome_aba, linha, motivo) for linha, motivo in aba.ignoradas)
            lote.avisos.extend(f"[{nome_aba}] {e}" for e in aba.erros)
            for linha in aba.exemplos_editados or []:
                aviso = (f"[{nome_aba}] A linha {linha} foi preenchida com uma nota, mas continua "
                         "marcada como EXEMPLO na coluna Status e NAO foi emitida. Apague a "
                         "palavra EXEMPLO da coluna Status dessa linha e emita de novo.")
                lote.avisos.append(aviso)

            empresa = self.config.obter(nome_aba)
            if empresa is None:
                aviso = (f"A aba {nome_aba!r} nao tem empresa cadastrada com esse nome. "
                         f"Cadastre a empresa ou renomeie a aba. "
                         f"Cadastradas: {', '.join(self.config.nomes()) or 'nenhuma'}.")
                lote.avisos.append(aviso)
                self._avisar(f"[pulada] {aviso}")
                continue

            problemas = empresa.validar()
            if problemas:
                aviso = f"Empresa {empresa.nome!r} com cadastro incompleto: " + "; ".join(problemas)
                lote.avisos.append(aviso)
                self._avisar(f"[pulada] {aviso}")
                continue

            if not aba.notas:
                self._avisar(f"[{nome_aba}] nenhuma nota pendente.")
                continue

            self._avisar(f"[{nome_aba}] {len(aba.notas)} nota(s) a emitir "
                         f"({empresa.ambiente}, layout "
                         f"{tabelas.LAYOUTS[self.layout_da_empresa(empresa)]}).")
            try:
                certificado = self.abrir_certificado(empresa)
            except ErroDeCertificado as exc:
                lote.avisos.append(f"[{nome_aba}] {exc}")
                self._avisar(f"[pulada] {exc}")
                continue

            cliente = None if self.simular else ClienteNFSe(empresa, certificado)
            # Na simulacao as notas recebem a numeracao que TERIAM, mas o contador
            # volta ao valor original no final: conferir nao gasta numero de DPS.
            numero_antes_da_simulacao = empresa.proximo_numero
            for nota in aba.notas:
                resultado = self.emitir_nota(empresa, certificado, nota, cliente=cliente)
                if (baixar_danfse and resultado.status == STATUS_EMITIDA
                        and resultado.chave_acesso and cliente is not None):
                    try:
                        destino = (self._pasta_da_empresa(empresa)
                                   / f"DANFSE-{resultado.chave_acesso}.pdf")
                        resultado.arquivo_danfse = str(
                            cliente.baixar_danfse(resultado.chave_acesso, destino))
                    except ErroDaApi as exc:
                        resultado.mensagem += f" (DANFSe nao baixada: {exc.mensagem})"
                lote.resultados.append(resultado)

            if self.simular:
                empresa.proximo_numero = numero_antes_da_simulacao
            self.config.salvar()   # mantem o contador de numeracao atualizado

        if gravar_na_planilha and lote.resultados:
            try:
                self.gravar_resultados(caminho, lote)
            except (OSError, PermissionError) as exc:
                # As notas ja foram emitidas: as chaves nao podem se perder
                # porque a planilha estava aberta no Excel.
                alternativa = self.salvar_resultados_avulsos(lote)
                aviso = (f"Nao consegui escrever na planilha ({exc}). "
                         f"Feche o arquivo no Excel e confira o resultado em "
                         f"{alternativa}.")
                lote.avisos.append(aviso)
                self._avisar(f"[aviso] {aviso}")
        return lote

    def salvar_resultados_avulsos(self, lote: "ResultadoLote") -> Path:
        """Grava o resultado num CSV a parte quando a planilha esta bloqueada."""
        destino = (self.diretorio_saida
                   / f"resultados-{util.agora():%Y%m%d-%H%M%S}.csv")
        colunas = ("aba", "linha", "status", "numero_dps", "numero_nfse",
                   "chave_acesso", "processado_em", "mensagem")
        with destino.open("w", encoding="utf-8-sig", newline="") as saida:
            escritor = csv.writer(saida, delimiter=";")
            escritor.writerow(colunas)
            for resultado in lote.resultados:
                escritor.writerow([getattr(resultado, coluna, "") for coluna in colunas])
        return destino

    # ------------------------------------------------------------------ #
    @staticmethod
    def gravar_resultados(caminho: str | Path, lote: ResultadoLote) -> None:
        """Escreve status, chave e mensagem de volta na planilha de origem."""
        por_aba: dict[str, dict[int, dict]] = {}
        for resultado in lote.resultados:
            por_aba.setdefault(resultado.aba, {})[resultado.linha] = {
                "status": resultado.status,
                "chave_acesso": resultado.chave_acesso,
                "numero_nfse": resultado.numero_nfse,
                "processado_em": resultado.processado_em,
                "mensagem": resultado.mensagem[:500],
            }
        mod_planilha.gravar_resultados(caminho, por_aba)

    # ------------------------------------------------------------------ #
    def cancelar(self, empresa: Empresa, chave_acesso: str, codigo_motivo: str,
                 motivo: str) -> dict:
        """Cancela uma NFS-e ja autorizada (evento e101101)."""
        certificado = self.abrir_certificado(empresa)
        xml_evento, id_evento = dps.montar_evento_cancelamento(
            empresa, chave_acesso, codigo_motivo, motivo)
        xml_assinado = assinatura.assinar_xml(xml_evento, id_evento, certificado)
        problemas_xsd = esquema.validar(xml_assinado, "pedRegEvento",
                                        layout=self.layout_da_empresa(empresa))
        if problemas_xsd:
            raise ErroDeValidacao(
                "O evento nao bate com o schema oficial: " + "; ".join(problemas_xsd))

        pasta = self._pasta_da_empresa(empresa)
        (pasta / f"EVENTO-{id_evento}.xml").write_bytes(xml_assinado)

        if self.simular:
            self._avisar(f"[simulado] evento de cancelamento {id_evento} gerado.")
            return {"simulado": True, "id_evento": id_evento}

        cliente = ClienteNFSe(empresa, certificado)
        resposta = cliente.registrar_evento(chave_acesso, xml_assinado)
        self._registrar_log(empresa, {"acao": "cancelamento", "chave": chave_acesso,
                                      "motivo": motivo, "resposta": resposta})
        self._avisar(f"[ok] cancelamento registrado para {chave_acesso}.")
        return resposta

    def consultar(self, empresa: Empresa, chave_acesso: str) -> dict:
        """Consulta uma NFS-e e guarda o XML devolvido."""
        certificado = self.abrir_certificado(empresa)
        resposta = ClienteNFSe(empresa, certificado).consultar(chave_acesso)
        if resposta.xml_nfse:
            destino = self._pasta_da_empresa(empresa) / f"NFSE-{chave_acesso}.xml"
            destino.write_bytes(resposta.xml_nfse)
        return resposta.bruto

    def baixar_danfse(self, empresa: Empresa, chave_acesso: str,
                      destino: str | Path | None = None) -> Path:
        """Baixa o PDF da DANFSe de uma nota autorizada."""
        certificado = self.abrir_certificado(empresa)
        caminho = Path(destino) if destino else (
            self._pasta_da_empresa(empresa) / f"DANFSE-{chave_acesso}.pdf")
        return ClienteNFSe(empresa, certificado).baixar_danfse(chave_acesso, caminho)

