#!/usr/bin/env python3
"""Gerador de NFS-e - Portal Nacional. Versao de linha de comando.

Use quando nao houver interface grafica ou para automatizar a rotina.

Exemplos:
    python nfse_cli.py empresas listar
    python nfse_cli.py empresas adicionar "CONTABIL NGF" --cnpj 11222333000181 \
        --municipio 3550308 --im 987654
    python nfse_cli.py certificado "CONTABIL NGF" --arquivo cert.pfx
    python nfse_cli.py modelo --saida modelos/modelo_nfse.xlsx
    python nfse_cli.py emitir notas.xlsx --simular
    python nfse_cli.py emitir notas.xlsx --empresa "CONTABIL NGF" --danfse
    python nfse_cli.py consultar "CONTABIL NGF" 3525...
    python nfse_cli.py cancelar "CONTABIL NGF" 3525... --codigo 1 \
        --motivo "Valor digitado errado na nota"
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nfse import modelo_planilha, tabelas, util                      # noqa: E402
from nfse.api import ErroDaApi                                       # noqa: E402
from nfse.certificado import ErroDeCertificado, ler_certificado      # noqa: E402
from nfse.config import Configuracao, Empresa, ErroDeConfiguracao    # noqa: E402
from nfse.emissor import Emissor                                     # noqa: E402
from nfse.planilha import ErroDePlanilha                             # noqa: E402
from nfse.util import ErroDeValidacao                                # noqa: E402

RAIZ = Path(__file__).resolve().parent


def escrever(mensagem: str = "") -> None:
    print(mensagem, flush=True)


def carregar(args) -> Configuracao:
    return Configuracao.carregar(args.dados)


# --------------------------------------------------------------------------- #
# empresas
# --------------------------------------------------------------------------- #
def cmd_empresas_listar(args) -> int:
    config = carregar(args)
    if not config.empresas:
        escrever("Nenhuma empresa cadastrada. Use: nfse_cli.py empresas adicionar \"NOME\"")
        return 0
    escrever(f"{len(config.empresas)} empresa(s) cadastrada(s):\n")
    for empresa in config.empresas:
        problemas = empresa.validar()
        marca = "OK " if not problemas else "!! "
        escrever(f"{marca}{empresa.nome}")
        escrever(f"     Razao social : {empresa.razao_social or '-'}")
        escrever(f"     CNPJ/CPF     : {util.formatar_documento(empresa.cnpj) or '-'}")
        escrever(f"     Municipio    : {empresa.codigo_municipio or '-'}"
                 f"   Insc. municipal: {empresa.inscricao_municipal or '-'}")
        escrever(f"     Ambiente     : {tabelas.ambiente(empresa.ambiente)['rotulo']}")
        escrever(f"     Layout DPS   : {tabelas.LAYOUTS[empresa.layout_efetivo()]}"
                 f" ({tabelas.LAYOUTS.get(empresa.layout, empresa.layout).split(' (')[0]})")
        escrever(f"     Serie/proximo: {empresa.serie_padrao} / {empresa.proximo_numero}")
        certificado = (f"{empresa.certificado_titular} (vence em {empresa.certificado_validade})"
                       if empresa.tem_certificado() else "nao cadastrado")
        escrever(f"     Certificado  : {certificado}")
        for problema in problemas:
            escrever(f"     -> falta: {problema}")
        escrever()
    return 0


def cmd_empresas_adicionar(args) -> int:
    config = carregar(args)
    empresa = Empresa(
        nome=util.texto(args.nome)[:31],
        razao_social=util.texto(args.razao or args.nome),
        cnpj=util.so_alfanumerico(args.cnpj or ""),
        inscricao_municipal=util.texto(args.im or ""),
        codigo_municipio=util.so_digitos(args.municipio or ""),
        optante_simples=args.simples,
        regime_apuracao_sn=args.regime_sn or "",
        regime_especial=args.regime_especial,
        ambiente=args.ambiente,
        layout=args.layout,
        serie_padrao=util.texto(args.serie),
        proximo_numero=max(1, args.proximo),
        email=util.texto(args.email or ""),
        telefone=util.texto(args.telefone or ""),
    )
    try:
        config.adicionar(empresa)
    except ErroDeConfiguracao as exc:
        escrever(f"ERRO: {exc}")
        return 1
    config.salvar()
    escrever(f"Empresa '{empresa.nome}' cadastrada.")
    for problema in empresa.validar():
        escrever(f"  -> ainda falta: {problema}")
    return 0


def cmd_empresas_editar(args) -> int:
    config = carregar(args)
    try:
        empresa = config.exigir(args.nome)
    except ErroDeConfiguracao as exc:
        escrever(f"ERRO: {exc}")
        return 1

    alteracoes = {
        "razao_social": args.razao, "cnpj": util.so_alfanumerico(args.cnpj) if args.cnpj else None,
        "inscricao_municipal": args.im,
        "codigo_municipio": util.so_digitos(args.municipio) if args.municipio else None,
        "optante_simples": args.simples, "regime_apuracao_sn": args.regime_sn,
        "regime_especial": args.regime_especial, "ambiente": args.ambiente,
        "layout": args.layout,
        "serie_padrao": args.serie, "email": args.email, "telefone": args.telefone,
    }
    for campo, valor in alteracoes.items():
        if valor is not None:
            setattr(empresa, campo, valor)
    if args.proximo is not None:
        empresa.proximo_numero = max(1, args.proximo)
    config.salvar()
    escrever(f"Empresa '{empresa.nome}' atualizada.")
    for problema in empresa.validar():
        escrever(f"  -> ainda falta: {problema}")
    return 0


def cmd_empresas_remover(args) -> int:
    config = carregar(args)
    try:
        config.remover(args.nome, apagar_certificado=args.apagar_certificado)
    except ErroDeConfiguracao as exc:
        escrever(f"ERRO: {exc}")
        return 1
    config.salvar()
    escrever(f"Empresa '{args.nome}' removida.")
    return 0


# --------------------------------------------------------------------------- #
def cmd_certificado(args) -> int:
    config = carregar(args)
    try:
        empresa = config.exigir(args.nome)
    except ErroDeConfiguracao as exc:
        escrever(f"ERRO: {exc}")
        return 1

    if args.arquivo:
        senha = args.senha or getpass.getpass("Senha do certificado: ")
        try:
            config.guardar_certificado(empresa, args.arquivo, senha)
        except (ErroDeCertificado, ErroDeConfiguracao) as exc:
            escrever(f"ERRO: {exc}")
            return 1
        config.salvar()
        escrever("Certificado guardado e senha cifrada.")

    if not empresa.tem_certificado():
        escrever("Nenhum certificado cadastrado para esta empresa.")
        return 1

    try:
        info = ler_certificado(empresa.certificado_arquivo,
                               config.senha_do_certificado(empresa))
    except ErroDeCertificado as exc:
        escrever(f"ERRO: {exc}")
        return 1
    escrever(f"Arquivo : {empresa.certificado_arquivo}")
    escrever(f"Titular : {info.titular}")
    escrever(f"Documento: {util.formatar_documento(info.documento)}")
    escrever(f"Emissor : {info.emissor}")
    escrever(f"Validade: {info.validade_inicio:%d/%m/%Y} ate {info.validade_fim:%d/%m/%Y}")
    escrever(f"Situacao: {'VENCIDO' if info.vencido else f'ok ({info.dias_para_vencer} dias)'}")
    return 0 if not info.vencido else 1


def cmd_modelo(args) -> int:
    config = carregar(args)
    nomes = [args.empresa] if args.empresa else (config.nomes() or ["EMPRESA EXEMPLO"])
    destino = Path(args.saida)
    caminho = modelo_planilha.gerar(destino, nomes, com_exemplo=not args.sem_exemplo)
    escrever(f"Planilha modelo gerada em: {caminho}")
    escrever(f"Abas criadas: {', '.join(nomes)}")
    return 0


def cmd_emitir(args) -> int:
    config = carregar(args)
    emissor = Emissor(config, diretorio_saida=args.saida, simular=args.simular,
                      progresso=escrever)
    try:
        lote = emissor.emitir_planilha(
            args.planilha,
            abas=[args.empresa] if args.empresa else None,
            somente_pendentes=not args.reenviar,
            gravar_na_planilha=not args.nao_gravar,
            baixar_danfse=args.danfse)
    except (ErroDePlanilha, ErroDeConfiguracao) as exc:
        escrever(f"ERRO: {exc}")
        return 1

    escrever("")
    escrever("=" * 72)
    escrever(f"RESULTADO: {lote.resumo()}")
    for aviso in lote.avisos:
        escrever(f"  aviso: {aviso}")
    for resultado in lote.erros:
        escrever(f"  ERRO  aba {resultado.aba}, linha {resultado.linha}: {resultado.mensagem}")
    for resultado in lote.emitidas:
        escrever(f"  OK    linha {resultado.linha}: NFS-e {resultado.numero_nfse} "
                 f"chave {resultado.chave_acesso}")
    escrever("=" * 72)
    return 1 if lote.erros else 0


def _empresa_ou_sai(config: Configuracao, nome: str) -> Empresa:
    try:
        return config.exigir(nome)
    except ErroDeConfiguracao as exc:
        escrever(f"ERRO: {exc}")
        raise SystemExit(1) from exc


def cmd_consultar(args) -> int:
    config = carregar(args)
    emissor = Emissor(config, diretorio_saida=args.saida, progresso=escrever)
    try:
        resposta = emissor.consultar(_empresa_ou_sai(config, args.empresa), args.chave)
    except (ErroDaApi, ErroDeCertificado) as exc:
        escrever(f"ERRO: {exc}")
        return 1
    escrever(str(resposta))
    return 0


def cmd_danfse(args) -> int:
    config = carregar(args)
    emissor = Emissor(config, diretorio_saida=args.saida, progresso=escrever)
    try:
        arquivo = emissor.baixar_danfse(_empresa_ou_sai(config, args.empresa),
                                        args.chave, args.destino)
    except (ErroDaApi, ErroDeCertificado) as exc:
        escrever(f"ERRO: {exc}")
        return 1
    escrever(f"DANFSe salva em: {arquivo}")
    return 0


def cmd_cancelar(args) -> int:
    config = carregar(args)
    empresa = _empresa_ou_sai(config, args.empresa)
    if not args.sim:
        escrever(f"Cancelar a NFS-e {args.chave} da empresa {empresa.nome}?")
        escrever(f"Motivo: {tabelas.descrever(tabelas.MOTIVO_CANCELAMENTO, args.codigo)} "
                 f"- {args.motivo}")
        if input("Digite SIM para confirmar: ").strip().upper() != "SIM":
            escrever("Cancelamento abortado.")
            return 1

    emissor = Emissor(config, diretorio_saida=args.saida, simular=args.simular,
                      progresso=escrever)
    try:
        resposta = emissor.cancelar(empresa, args.chave, args.codigo, args.motivo)
    except (ErroDaApi, ErroDeCertificado, ErroDeValidacao) as exc:
        escrever(f"ERRO: {exc}")
        return 1
    escrever(str(resposta))
    return 0


# --------------------------------------------------------------------------- #
def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nfse_cli.py",
        description="Gerador de NFS-e pelo Portal Nacional (uma aba da planilha por empresa).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    parser.add_argument("--dados", default=str(RAIZ / "dados"),
                        help="pasta do cadastro e dos certificados (padrao: ./dados)")
    parser.add_argument("--saida", default=str(RAIZ / "saida"),
                        help="pasta dos XML/PDF gerados (padrao: ./saida)")
    sub = parser.add_subparsers(dest="comando", required=True)

    # empresas
    empresas = sub.add_parser("empresas", help="cadastro das empresas")
    acoes = empresas.add_subparsers(dest="acao", required=True)

    acoes.add_parser("listar", help="mostra as empresas cadastradas").set_defaults(
        func=cmd_empresas_listar)

    def campos_comuns(p, obrigatorio_nome=True):
        p.add_argument("nome", help="nome da empresa (igual ao nome da aba da planilha)")
        p.add_argument("--razao", help="razao social")
        p.add_argument("--cnpj", help="CNPJ ou CPF do prestador")
        p.add_argument("--im", help="inscricao municipal")
        p.add_argument("--municipio", help="codigo IBGE do municipio (7 digitos)")
        p.add_argument("--simples", choices=sorted(tabelas.OPCAO_SIMPLES_NACIONAL),
                       help="1 nao optante, 2 MEI, 3 ME/EPP")
        p.add_argument("--regime-sn", choices=sorted(tabelas.REGIME_APURACAO_SN),
                       help="regime de apuracao (so para optante 3)")
        p.add_argument("--regime-especial", choices=sorted(tabelas.REGIME_ESPECIAL),
                       help="regime especial de tributacao")
        p.add_argument("--ambiente", choices=("homologacao", "producao"))
        p.add_argument("--layout", choices=sorted(tabelas.LAYOUTS),
                       help="layout da DPS (padrao: automatico, pelo ambiente e pela data)")
        p.add_argument("--serie", help="serie padrao da DPS")
        p.add_argument("--email")
        p.add_argument("--telefone")

    adicionar = acoes.add_parser("adicionar", help="cadastra uma nova empresa")
    campos_comuns(adicionar)
    adicionar.set_defaults(func=cmd_empresas_adicionar, simples="1", regime_especial="0",
                           ambiente=tabelas.AMBIENTE_PADRAO, serie="1", proximo=1,
                           layout=tabelas.LAYOUT_AUTOMATICO)
    adicionar.add_argument("--proximo", type=int, default=1,
                           help="proximo numero de DPS (padrao: 1)")

    editar = acoes.add_parser("editar", help="altera dados de uma empresa")
    campos_comuns(editar)
    editar.add_argument("--proximo", type=int, help="proximo numero de DPS")
    editar.set_defaults(func=cmd_empresas_editar)

    remover = acoes.add_parser("remover", help="remove uma empresa do cadastro")
    remover.add_argument("nome")
    remover.add_argument("--apagar-certificado", action="store_true",
                         help="apaga tambem a copia do .pfx guardada pelo sistema")
    remover.set_defaults(func=cmd_empresas_remover)

    # certificado
    certificado = sub.add_parser("certificado",
                                 help="cadastra ou confere o certificado A1 da empresa")
    certificado.add_argument("nome")
    certificado.add_argument("--arquivo", help="caminho do .pfx/.p12 a cadastrar")
    certificado.add_argument("--senha", help="senha (se omitida, e pedida sem aparecer na tela)")
    certificado.set_defaults(func=cmd_certificado)

    # modelo
    modelo = sub.add_parser("modelo", help="gera a planilha modelo")
    modelo.add_argument("--saida", dest="saida", default=str(RAIZ / "modelos" / "modelo_nfse.xlsx"),
                        help="arquivo .xlsx a gerar")
    modelo.add_argument("--empresa", help="gera apenas a aba desta empresa")
    modelo.add_argument("--sem-exemplo", action="store_true",
                        help="nao inclui a linha de demonstracao")
    modelo.set_defaults(func=cmd_modelo)

    # emitir
    emitir = sub.add_parser("emitir", help="emite as notas da planilha")
    emitir.add_argument("planilha", help="arquivo .xlsx com as notas")
    emitir.add_argument("--empresa", help="emite apenas a aba desta empresa")
    emitir.add_argument("--simular", action="store_true",
                        help="gera e assina o XML sem enviar ao Portal")
    emitir.add_argument("--danfse", action="store_true", help="baixa o PDF de cada nota")
    emitir.add_argument("--reenviar", action="store_true",
                        help="reprocessa tambem as linhas que ja tem chave de acesso")
    emitir.add_argument("--nao-gravar", action="store_true",
                        help="nao escreve o resultado de volta na planilha")
    emitir.set_defaults(func=cmd_emitir)

    # consultar / danfse / cancelar
    consultar = sub.add_parser("consultar", help="consulta uma NFS-e pela chave")
    consultar.add_argument("empresa")
    consultar.add_argument("chave")
    consultar.set_defaults(func=cmd_consultar)

    danfse = sub.add_parser("danfse", help="baixa o PDF de uma NFS-e")
    danfse.add_argument("empresa")
    danfse.add_argument("chave")
    danfse.add_argument("--destino", help="caminho do PDF a gravar")
    danfse.set_defaults(func=cmd_danfse)

    cancelar = sub.add_parser("cancelar", help="cancela uma NFS-e autorizada")
    cancelar.add_argument("empresa")
    cancelar.add_argument("chave")
    cancelar.add_argument("--codigo", default="1", choices=sorted(tabelas.MOTIVO_CANCELAMENTO),
                          help="1 erro na emissao, 2 servico nao prestado, 9 outros")
    cancelar.add_argument("--motivo", required=True,
                          help="descricao do motivo (minimo de 15 caracteres)")
    cancelar.add_argument("--simular", action="store_true",
                          help="gera e assina o evento sem enviar")
    cancelar.add_argument("--sim", action="store_true", help="nao pede confirmacao")
    cancelar.set_defaults(func=cmd_cancelar)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        escrever("\nInterrompido pelo usuario.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
