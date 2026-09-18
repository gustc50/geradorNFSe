"""Cliente HTTP da API do Portal Nacional da NFS-e (Sefin Nacional).

A autenticacao e feita por mTLS: o mesmo certificado A1 que assina o XML e
usado no handshake TLS. O XML vai comprimido em gzip e codificado em base64.

Rotas usadas:
    POST   {base}/nfse                        emite a NFS-e a partir da DPS
    GET    {base}/nfse/{chave}                consulta a NFS-e pela chave
    GET    {base}/danfse/{chave}              baixa o PDF da DANFSe
    POST   {base}/nfse/{chave}/eventos        registra evento (ex.: cancelamento)

Atencao: uma emissao **nunca** e repetida automaticamente. Se a resposta se
perder no meio do caminho, consulte antes de reenviar - assim nao nasce nota
duplicada.
"""

from __future__ import annotations

import base64
import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path

import requests

from .certificado import InfoCertificado, par_pem_temporario
from .config import Empresa

TEMPO_LIMITE = (15, 120)   # (conexao, leitura) em segundos
CABECALHOS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "GeradorNFSe/1.0 (Python)",
}


class ErroDaApi(Exception):
    """Erro devolvido pelo Portal Nacional ou falha de comunicacao."""

    def __init__(self, mensagem: str, *, status: int | None = None,
                 erros: list[dict] | None = None, corpo: str = ""):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status
        self.erros = erros or []
        self.corpo = corpo

    def detalhado(self) -> str:
        partes = [self.mensagem]
        for erro in self.erros:
            codigo = erro.get("codigo") or erro.get("Codigo") or ""
            descricao = (erro.get("descricao") or erro.get("Descricao")
                         or erro.get("mensagem") or "")
            complemento = erro.get("complemento") or erro.get("Complemento") or ""
            linha = " ".join(p for p in (f"[{codigo}]" if codigo else "",
                                         descricao, complemento) if p)
            if linha:
                partes.append(linha.strip())
        return " | ".join(partes)


@dataclass
class RespostaEmissao:
    """Resposta da emissao de uma NFS-e."""

    chave_acesso: str = ""
    numero_nfse: str = ""
    id_dps: str = ""
    data_processamento: str = ""
    xml_nfse: bytes = b""
    bruto: dict = field(default_factory=dict)

    @property
    def autorizada(self) -> bool:
        return bool(self.chave_acesso)


def compactar(xml: bytes) -> str:
    """gzip + base64, como a API espera."""
    return base64.b64encode(gzip.compress(xml)).decode("ascii")


def descompactar(conteudo: str) -> bytes:
    """Desfaz base64 + gzip (aceita conteudo nao compactado)."""
    if not conteudo:
        return b""
    bruto = base64.b64decode(conteudo)
    try:
        return gzip.decompress(bruto)
    except (OSError, EOFError):
        return bruto


def _numero_da_nfse(chave: str) -> str:
    """Extrai o numero sequencial da NFS-e da chave de acesso de 50 digitos."""
    return chave[31:44].lstrip("0") if len(chave) == 50 else ""


class ClienteNFSe:
    """Conversa com a API do Portal Nacional usando o certificado da empresa."""

    def __init__(self, empresa: Empresa, certificado: InfoCertificado,
                 tempo_limite=TEMPO_LIMITE, verificar_tls: bool = True):
        self.empresa = empresa
        self.certificado = certificado
        self.tempo_limite = tempo_limite
        self.verificar_tls = verificar_tls
        self.base = empresa.url_api().rstrip("/")

    # ------------------------------------------------------------------ #
    def _requisitar(self, metodo: str, caminho: str, *, json_corpo: dict | None = None,
                    aceitar: str = "application/json") -> requests.Response:
        url = f"{self.base}/{caminho.lstrip('/')}"
        cabecalhos = dict(CABECALHOS, Accept=aceitar)
        with par_pem_temporario(self.certificado) as (arquivo_cert, arquivo_chave):
            try:
                resposta = requests.request(
                    metodo, url,
                    json=json_corpo,
                    headers=cabecalhos,
                    cert=(arquivo_cert, arquivo_chave),
                    timeout=self.tempo_limite,
                    verify=self.verificar_tls,
                )
            except requests.exceptions.SSLError as exc:
                raise ErroDaApi(
                    "Falha no handshake TLS com o Portal Nacional. Verifique se o "
                    "certificado A1 esta valido e habilitado para autenticacao: "
                    f"{exc}") from exc
            except requests.exceptions.ConnectTimeout as exc:
                raise ErroDaApi(f"Tempo esgotado ao conectar em {url}.") from exc
            except requests.exceptions.ReadTimeout as exc:
                raise ErroDaApi(
                    f"O Portal Nacional nao respondeu a tempo ({url}). "
                    "Consulte a nota antes de reenviar.") from exc
            except requests.exceptions.RequestException as exc:
                raise ErroDaApi(f"Falha de comunicacao com {url}: {exc}") from exc
        return resposta

    @staticmethod
    def _corpo_json(resposta: requests.Response) -> dict:
        try:
            return resposta.json()
        except (ValueError, json.JSONDecodeError):
            return {}

    def _conferir(self, resposta: requests.Response, acao: str) -> dict:
        corpo = self._corpo_json(resposta)
        if resposta.ok:
            return corpo
        erros = corpo.get("erros") or corpo.get("Erros") or []
        if not erros and corpo:
            erros = [corpo]
        raise ErroDaApi(
            f"{acao} recusada pelo Portal Nacional (HTTP {resposta.status_code}).",
            status=resposta.status_code, erros=erros, corpo=resposta.text[:2000])

    # ------------------------------------------------------------------ #
    def emitir(self, xml_dps_assinado: bytes) -> RespostaEmissao:
        """Envia a DPS assinada e devolve a NFS-e autorizada."""
        resposta = self._requisitar(
            "POST", "/nfse", json_corpo={"dpsXmlGZipB64": compactar(xml_dps_assinado)})
        corpo = self._conferir(resposta, "Emissao")

        chave = (corpo.get("chaveAcesso") or corpo.get("chaveAcessoNFSe")
                 or corpo.get("ChaveAcesso") or "")
        return RespostaEmissao(
            chave_acesso=chave,
            numero_nfse=corpo.get("nNFSe") or _numero_da_nfse(chave),
            id_dps=corpo.get("idDps") or corpo.get("idDPS") or "",
            data_processamento=corpo.get("dataHoraProcessamento", ""),
            xml_nfse=descompactar(corpo.get("nfseXmlGZipB64", "")),
            bruto=corpo,
        )

    def consultar(self, chave_acesso: str) -> RespostaEmissao:
        """Consulta uma NFS-e ja emitida pela chave de acesso."""
        resposta = self._requisitar("GET", f"/nfse/{chave_acesso}")
        corpo = self._conferir(resposta, "Consulta")
        return RespostaEmissao(
            chave_acesso=chave_acesso,
            numero_nfse=corpo.get("nNFSe") or _numero_da_nfse(chave_acesso),
            data_processamento=corpo.get("dataHoraProcessamento", ""),
            xml_nfse=descompactar(corpo.get("nfseXmlGZipB64", "")),
            bruto=corpo,
        )

    def baixar_danfse(self, chave_acesso: str, destino: str | Path) -> Path:
        """Baixa o PDF da DANFSe e grava no caminho informado."""
        resposta = self._requisitar("GET", f"/danfse/{chave_acesso}",
                                    aceitar="application/pdf")
        if not resposta.ok:
            self._conferir(resposta, "Download da DANFSe")
        arquivo = Path(destino)
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_bytes(resposta.content)
        return arquivo

    def registrar_evento(self, chave_acesso: str, xml_evento_assinado: bytes) -> dict:
        """Registra um evento (cancelamento, por exemplo) na NFS-e."""
        resposta = self._requisitar(
            "POST", f"/nfse/{chave_acesso}/eventos",
            json_corpo={"pedidoRegistroEventoXmlGZipB64": compactar(xml_evento_assinado)})
        return self._conferir(resposta, "Registro de evento")
