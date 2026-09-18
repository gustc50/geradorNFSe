#!/usr/bin/env python3
"""Gerador de NFS-e - Portal Nacional. Interface grafica.

Cada aba da janela e uma empresa: dados do prestador, certificado digital
(gravado com a senha cifrada) e emissao das notas a partir da planilha.

Execute com:  python app.py
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import traceback
import webbrowser
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
except ImportError:  # pragma: no cover - ambiente sem interface grafica
    print("Este computador nao tem o Tkinter instalado.\n"
          "  Windows/macOS: reinstale o Python marcando 'tcl/tk and IDLE'.\n"
          "  Linux: sudo apt install python3-tk\n"
          "Enquanto isso, use a versao de linha de comando: python nfse_cli.py --ajuda")
    raise SystemExit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nfse import modelo_planilha, tabelas, util                      # noqa: E402
from nfse.certificado import ErroDeCertificado, ler_certificado      # noqa: E402
from nfse.config import Configuracao, Empresa, ErroDeConfiguracao    # noqa: E402
from nfse.emissor import Emissor                                     # noqa: E402

TITULO = "Gerador de NFS-e - Portal Nacional"
COR_FUNDO = "#F4F6F9"
COR_TITULO = "#1F3864"
COR_PRODUCAO = "#8C1D40"
COR_HOMOLOGACAO = "#2E5E4E"
SENHA_GUARDADA = "•" * 10        # placeholder de senha ja cadastrada


def abrir_no_sistema(caminho: Path) -> None:
    """Abre um arquivo ou pasta no gerenciador do sistema operacional."""
    caminho = Path(caminho)
    try:
        if sys.platform.startswith("win"):
            os.startfile(caminho)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(caminho)], check=False)
        else:
            subprocess.run(["xdg-open", str(caminho)], check=False)
    except Exception:  # noqa: BLE001 - abrir pasta nunca deve quebrar o app
        webbrowser.open(caminho.as_uri())


class CampoCombo(ttk.Combobox):
    """Combo que mostra 'codigo - descricao' e devolve so o codigo."""

    def __init__(self, pai, dominio: dict, **kwargs):
        self.dominio = dominio
        super().__init__(pai, values=tabelas.opcoes(dominio), state="readonly", **kwargs)

    def codigo(self) -> str:
        return tabelas.codigo_da_opcao(self.get())

    def definir(self, codigo: str) -> None:
        codigo = util.texto(codigo)
        for opcao in tabelas.opcoes(self.dominio):
            if tabelas.codigo_da_opcao(opcao) == codigo:
                self.set(opcao)
                return
        self.set(tabelas.opcoes(self.dominio)[0] if self.dominio else "")


class AbaEmpresa(ttk.Frame):
    """Uma aba = uma empresa."""

    def __init__(self, pai, app: "Aplicativo", empresa: Empresa):
        super().__init__(pai, padding=12)
        self.app = app
        self.empresa = empresa
        self.fila: queue.Queue[str] = queue.Queue()
        self.trabalhando = False
        self._montar()
        self._carregar_da_empresa()
        self.after(150, self._drenar_fila)

    # ------------------------------------------------------------------ #
    # Montagem da tela
    # ------------------------------------------------------------------ #
    def _montar(self) -> None:
        painel = ttk.Frame(self)
        painel.pack(fill="both", expand=True)
        painel.columnconfigure(0, weight=1)

        self._montar_dados(painel)
        self._montar_certificado(painel)
        self._montar_emissao(painel)
        self._montar_nota_emitida(painel)
        self._montar_log(painel)

    def _grupo(self, pai, titulo: str) -> ttk.LabelFrame:
        grupo = ttk.LabelFrame(pai, text=f" {titulo} ", padding=10)
        grupo.pack(fill="x", pady=(0, 10))
        return grupo

    def _montar_dados(self, pai) -> None:
        grupo = self._grupo(pai, "1. Dados da empresa (prestador)")
        for coluna in (1, 3, 5):
            grupo.columnconfigure(coluna, weight=1)

        def rotulo(texto, linha, coluna):
            ttk.Label(grupo, text=texto).grid(row=linha, column=coluna, sticky="w",
                                              padx=(0, 6), pady=3)

        self.var_razao = tk.StringVar()
        self.var_cnpj = tk.StringVar()
        self.var_im = tk.StringVar()
        self.var_municipio = tk.StringVar()
        self.var_serie = tk.StringVar()
        self.var_proximo = tk.StringVar()
        self.var_email = tk.StringVar()
        self.var_fone = tk.StringVar()
        self.var_ambiente = tk.StringVar(value=tabelas.AMBIENTE_PADRAO)

        rotulo("Razao social", 0, 0)
        ttk.Entry(grupo, textvariable=self.var_razao).grid(
            row=0, column=1, columnspan=3, sticky="ew", pady=3)
        rotulo("CNPJ/CPF *", 0, 4)
        ttk.Entry(grupo, textvariable=self.var_cnpj).grid(row=0, column=5, sticky="ew", pady=3)

        rotulo("Inscricao municipal", 1, 0)
        ttk.Entry(grupo, textvariable=self.var_im).grid(row=1, column=1, sticky="ew", pady=3)
        rotulo("Cod. municipio (IBGE) *", 1, 2)
        ttk.Entry(grupo, textvariable=self.var_municipio).grid(
            row=1, column=3, sticky="ew", pady=3)
        rotulo("Serie padrao", 1, 4)
        ttk.Entry(grupo, textvariable=self.var_serie).grid(row=1, column=5, sticky="ew", pady=3)

        rotulo("Simples Nacional", 2, 0)
        self.combo_simples = CampoCombo(grupo, tabelas.OPCAO_SIMPLES_NACIONAL)
        self.combo_simples.grid(row=2, column=1, sticky="ew", pady=3)
        self.combo_simples.bind("<<ComboboxSelected>>", lambda _e: self._alternar_regime_sn())

        rotulo("Regime de apuracao (SN)", 2, 2)
        self.combo_regime_sn = CampoCombo(grupo, tabelas.REGIME_APURACAO_SN)
        self.combo_regime_sn.grid(row=2, column=3, sticky="ew", pady=3)

        rotulo("Regime especial", 2, 4)
        self.combo_regime = CampoCombo(grupo, tabelas.REGIME_ESPECIAL)
        self.combo_regime.grid(row=2, column=5, sticky="ew", pady=3)

        rotulo("E-mail", 3, 0)
        ttk.Entry(grupo, textvariable=self.var_email).grid(row=3, column=1, sticky="ew", pady=3)
        rotulo("Telefone", 3, 2)
        ttk.Entry(grupo, textvariable=self.var_fone).grid(row=3, column=3, sticky="ew", pady=3)
        rotulo("Proximo nro. DPS", 3, 4)
        ttk.Entry(grupo, textvariable=self.var_proximo).grid(
            row=3, column=5, sticky="ew", pady=3)

        ambiente = ttk.Frame(grupo)
        ambiente.grid(row=4, column=0, columnspan=6, sticky="w", pady=(8, 0))
        ttk.Label(ambiente, text="Ambiente:").pack(side="left", padx=(0, 8))
        ttk.Radiobutton(ambiente, text="Homologacao (teste)", value="homologacao",
                        variable=self.var_ambiente,
                        command=self._atualizar_aviso_ambiente).pack(side="left")
        ttk.Radiobutton(ambiente, text="PRODUCAO (nota valendo)", value="producao",
                        variable=self.var_ambiente,
                        command=self._atualizar_aviso_ambiente).pack(side="left", padx=10)
        self.rotulo_ambiente = tk.Label(ambiente, text="", font=("Segoe UI", 9, "bold"))
        self.rotulo_ambiente.pack(side="left", padx=10)

        ttk.Button(grupo, text="Salvar dados da empresa",
                   command=self.salvar).grid(row=5, column=0, columnspan=2,
                                             sticky="w", pady=(10, 0))

    def _montar_certificado(self, pai) -> None:
        grupo = self._grupo(pai, "2. Certificado digital A1 (.pfx / .p12)")
        grupo.columnconfigure(1, weight=1)

        self.var_certificado = tk.StringVar()
        self.var_senha = tk.StringVar()

        ttk.Label(grupo, text="Arquivo *").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(grupo, textvariable=self.var_certificado).grid(
            row=0, column=1, sticky="ew", pady=3)
        ttk.Button(grupo, text="Procurar...", command=self._escolher_certificado).grid(
            row=0, column=2, padx=6)

        ttk.Label(grupo, text="Senha *").grid(row=1, column=0, sticky="w", padx=(0, 6))
        self.entrada_senha = ttk.Entry(grupo, textvariable=self.var_senha, show="*")
        self.entrada_senha.grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Button(grupo, text="Salvar e testar certificado",
                   command=self.salvar_certificado).grid(row=1, column=2, padx=6)

        self.rotulo_certificado = tk.Label(
            grupo, text="Nenhum certificado cadastrado.", anchor="w",
            fg="#666666", bg=COR_FUNDO)
        self.rotulo_certificado.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(6, 0))

        ttk.Label(grupo, foreground="#666666", wraplength=900, justify="left",
                  text=("A senha e gravada cifrada (AES-256) na pasta 'dados'. "
                        "Voce so precisa digita-la uma vez.")
                  ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))

    def _montar_emissao(self, pai) -> None:
        grupo = self._grupo(pai, "3. Planilha de notas")
        grupo.columnconfigure(1, weight=1)

        self.var_planilha = tk.StringVar()
        self.var_danfse = tk.BooleanVar(value=False)

        ttk.Label(grupo, text="Arquivo").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(grupo, textvariable=self.var_planilha).grid(
            row=0, column=1, sticky="ew", pady=3)
        ttk.Button(grupo, text="Procurar...", command=self._escolher_planilha).grid(
            row=0, column=2, padx=6)

        botoes = ttk.Frame(grupo)
        botoes.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        ttk.Button(botoes, text="Gerar planilha modelo",
                   command=self.app.gerar_modelo).pack(side="left")
        ttk.Button(botoes, text="Conferir sem enviar (simulacao)",
                   command=lambda: self.emitir(simular=True)).pack(side="left", padx=6)
        self.botao_emitir = tk.Button(
            botoes, text="EMITIR NOTAS", command=lambda: self.emitir(simular=False),
            bg=COR_TITULO, fg="white", font=("Segoe UI", 10, "bold"),
            relief="flat", padx=16, pady=4, cursor="hand2")
        self.botao_emitir.pack(side="left", padx=6)
        ttk.Checkbutton(botoes, text="Baixar DANFSe (PDF)",
                        variable=self.var_danfse).pack(side="left", padx=6)
        ttk.Button(botoes, text="Abrir pasta de saida",
                   command=self._abrir_saida).pack(side="right")

    def _montar_nota_emitida(self, pai) -> None:
        grupo = self._grupo(pai, "4. Nota ja emitida (consulta, PDF e cancelamento)")
        grupo.columnconfigure(1, weight=1)

        self.var_chave = tk.StringVar()
        ttk.Label(grupo, text="Chave de acesso").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(grupo, textvariable=self.var_chave).grid(row=0, column=1, sticky="ew", pady=3)

        botoes = ttk.Frame(grupo)
        botoes.grid(row=0, column=2, padx=6)
        ttk.Button(botoes, text="Consultar", command=self.consultar).pack(side="left")
        ttk.Button(botoes, text="Baixar DANFSe", command=self.baixar_danfse).pack(
            side="left", padx=6)
        ttk.Button(botoes, text="Cancelar nota", command=self.cancelar).pack(side="left")

    def _montar_log(self, pai) -> None:
        grupo = ttk.LabelFrame(pai, text=" Andamento ", padding=6)
        grupo.pack(fill="both", expand=True)
        self.texto_log = tk.Text(grupo, height=10, wrap="word", bg="#1E1E1E",
                                 fg="#DCDCDC", insertbackground="#DCDCDC",
                                 font=("Consolas", 9), relief="flat")
        barra = ttk.Scrollbar(grupo, command=self.texto_log.yview)
        self.texto_log.configure(yscrollcommand=barra.set, state="disabled")
        self.texto_log.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        for marca, cor in (("ok", "#6AC46A"), ("erro", "#FF7B72"),
                           ("aviso", "#E3B341"), ("info", "#79C0FF")):
            self.texto_log.tag_configure(marca, foreground=cor)

    # ------------------------------------------------------------------ #
    # Log
    # ------------------------------------------------------------------ #
    def registrar(self, mensagem: str) -> None:
        self.fila.put(mensagem)

    def _drenar_fila(self) -> None:
        try:
            while True:
                mensagem = self.fila.get_nowait()
                marca = ("erro" if "[erro]" in mensagem or "ERRO" in mensagem else
                         "ok" if "[ok]" in mensagem else
                         "aviso" if "[aviso]" in mensagem or "[pulada]" in mensagem else
                         "info")
                self.texto_log.configure(state="normal")
                self.texto_log.insert("end", mensagem + "\n", marca)
                self.texto_log.see("end")
                self.texto_log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(150, self._drenar_fila)

    # ------------------------------------------------------------------ #
    # Carregar / salvar
    # ------------------------------------------------------------------ #
    def _carregar_da_empresa(self) -> None:
        e = self.empresa
        self.var_razao.set(e.razao_social)
        self.var_cnpj.set(util.formatar_documento(e.cnpj) if e.cnpj else "")
        self.var_im.set(e.inscricao_municipal)
        self.var_municipio.set(e.codigo_municipio)
        self.var_serie.set(e.serie_padrao)
        self.var_proximo.set(str(e.proximo_numero))
        self.var_email.set(e.email)
        self.var_fone.set(e.telefone)
        self.var_ambiente.set(tabelas.ambiente(e.ambiente)["chave"])
        self.combo_simples.definir(e.optante_simples)
        self.combo_regime_sn.definir(e.regime_apuracao_sn or "1")
        self.combo_regime.definir(e.regime_especial)
        self.var_certificado.set(e.certificado_arquivo)
        self.var_senha.set(SENHA_GUARDADA if e.certificado_senha else "")
        self._alternar_regime_sn()
        self._atualizar_aviso_ambiente()
        self._atualizar_rotulo_certificado()

        planilha_padrao = self.app.planilha_sugerida()
        if planilha_padrao:
            self.var_planilha.set(str(planilha_padrao))

    def _recolher_para_empresa(self) -> None:
        e = self.empresa
        e.razao_social = util.texto(self.var_razao.get())
        e.cnpj = util.so_digitos(self.var_cnpj.get())
        e.inscricao_municipal = util.texto(self.var_im.get())
        e.codigo_municipio = util.so_digitos(self.var_municipio.get())
        e.serie_padrao = util.texto(self.var_serie.get()) or "1"
        e.proximo_numero = max(1, util.inteiro(self.var_proximo.get(), 1))
        e.email = util.texto(self.var_email.get())
        e.telefone = util.texto(self.var_fone.get())
        e.ambiente = self.var_ambiente.get()
        e.optante_simples = self.combo_simples.codigo()
        e.regime_apuracao_sn = (self.combo_regime_sn.codigo()
                                if e.optante_simples == "3" else "")
        e.regime_especial = self.combo_regime.codigo()

    def salvar(self, silencioso: bool = False) -> bool:
        self._recolher_para_empresa()
        try:
            self.app.config.salvar()
        except OSError as exc:
            messagebox.showerror(TITULO, f"Nao consegui gravar o cadastro:\n{exc}")
            return False
        problemas = [p for p in self.empresa.validar() if "ertificado" not in p]
        if problemas and not silencioso:
            messagebox.showwarning(
                TITULO, "Cadastro salvo, mas ainda falta acertar:\n\n  - "
                + "\n  - ".join(problemas))
        elif not silencioso:
            self.registrar("[ok] Dados da empresa salvos.")
            self.app.status(f"Empresa {self.empresa.nome} salva.")
        return True

    # ------------------------------------------------------------------ #
    def _alternar_regime_sn(self) -> None:
        """O regime de apuracao so existe para optante ME/EPP (codigo 3)."""
        aplicavel = self.combo_simples.codigo() == "3"
        if aplicavel:
            self.combo_regime_sn.configure(state="readonly")
            if not self.combo_regime_sn.codigo():
                self.combo_regime_sn.definir(self.empresa.regime_apuracao_sn or "1")
        else:
            self.combo_regime_sn.set("")
            self.combo_regime_sn.configure(state="disabled")

    def _atualizar_aviso_ambiente(self) -> None:
        producao = self.var_ambiente.get() == "producao"
        self.rotulo_ambiente.configure(
            text="ATENCAO: as notas terao valor fiscal" if producao
            else "Ambiente de teste: nada tem valor fiscal",
            fg=COR_PRODUCAO if producao else COR_HOMOLOGACAO)

    def _atualizar_rotulo_certificado(self) -> None:
        if not self.empresa.tem_certificado():
            self.rotulo_certificado.configure(
                text="Nenhum certificado cadastrado.", fg="#8C1D40")
            return
        texto = f"Certificado: {self.empresa.certificado_titular or '-'}"
        if self.empresa.certificado_validade:
            texto += f" | vence em {self.empresa.certificado_validade}"
        self.rotulo_certificado.configure(text=texto, fg="#2E5E4E")

    def _escolher_certificado(self) -> None:
        arquivo = filedialog.askopenfilename(
            title="Escolha o certificado digital A1",
            filetypes=[("Certificado A1", "*.pfx *.p12"), ("Todos os arquivos", "*.*")])
        if arquivo:
            self.var_certificado.set(arquivo)
            self.var_senha.set("")
            self.entrada_senha.focus_set()

    def salvar_certificado(self) -> None:
        arquivo = util.texto(self.var_certificado.get())
        if not arquivo:
            messagebox.showwarning(TITULO, "Escolha o arquivo do certificado (.pfx).")
            return

        senha = self.var_senha.get()
        if senha == SENHA_GUARDADA:
            if not self.empresa.certificado_senha:
                messagebox.showwarning(TITULO, "Digite a senha do certificado.")
                return
            senha = self.app.config.senha_do_certificado(self.empresa)
        if not senha:
            messagebox.showwarning(TITULO, "Digite a senha do certificado.")
            return

        self.salvar(silencioso=True)
        try:
            self.app.config.guardar_certificado(self.empresa, arquivo, senha)
            self.app.config.salvar()
            info = ler_certificado(self.empresa.certificado_arquivo, senha)
        except (ErroDeCertificado, ErroDeConfiguracao) as exc:
            messagebox.showerror(TITULO, str(exc))
            self.registrar(f"[erro] {exc}")
            return

        self.var_senha.set(SENHA_GUARDADA)
        self.var_certificado.set(self.empresa.certificado_arquivo)
        self._carregar_da_empresa()
        self.registrar(f"[ok] Certificado guardado: {info.resumo()}")
        if info.dias_para_vencer <= 30:
            messagebox.showwarning(
                TITULO, f"Este certificado vence em {info.dias_para_vencer} dia(s).")
        self.app.status("Certificado guardado com a senha cifrada.")

    # ------------------------------------------------------------------ #
    # Planilha e emissao
    # ------------------------------------------------------------------ #
    def _escolher_planilha(self) -> None:
        arquivo = filedialog.askopenfilename(
            title="Escolha a planilha de notas",
            filetypes=[("Planilha do Excel", "*.xlsx *.xlsm"), ("Todos os arquivos", "*.*")])
        if arquivo:
            self.var_planilha.set(arquivo)
            self.app.ultima_planilha = Path(arquivo)

    def _abrir_saida(self) -> None:
        pasta = self.app.diretorio_saida / util.nome_arquivo_seguro(self.empresa.nome)
        pasta.mkdir(parents=True, exist_ok=True)
        abrir_no_sistema(pasta)

    def _preparar_execucao(self) -> bool:
        if self.trabalhando:
            messagebox.showinfo(TITULO, "Ja existe um processamento em andamento.")
            return False
        if not self.salvar(silencioso=True):
            return False
        problemas = self.empresa.validar()
        if problemas:
            messagebox.showerror(
                TITULO, "Complete o cadastro antes de emitir:\n\n  - " + "\n  - ".join(problemas))
            return False
        return True

    def emitir(self, simular: bool) -> None:
        if not self._preparar_execucao():
            return
        planilha = util.texto(self.var_planilha.get())
        if not planilha or not Path(planilha).exists():
            messagebox.showwarning(TITULO, "Escolha a planilha com as notas.")
            return

        if not simular and self.empresa.ambiente == "producao":
            if not messagebox.askyesno(
                    TITULO,
                    f"As notas da aba '{self.empresa.nome}' serao emitidas em PRODUCAO "
                    "e terao valor fiscal.\n\nConfirma a emissao?", icon="warning"):
                return

        self.app.ultima_planilha = Path(planilha)
        titulo = "Simulacao" if simular else "Emissao"
        self.registrar(f"--- {titulo} iniciada ({self.empresa.ambiente}) ---")
        self._executar_em_segundo_plano(
            lambda: self._rodar_emissao(planilha, simular), titulo)

    def _rodar_emissao(self, planilha: str, simular: bool) -> None:
        emissor = Emissor(self.app.config, diretorio_saida=self.app.diretorio_saida,
                          simular=simular, progresso=self.registrar)
        lote = emissor.emitir_planilha(
            planilha, abas=[self.empresa.nome],
            baixar_danfse=self.var_danfse.get() and not simular)
        for aviso in lote.avisos:
            self.registrar(f"[aviso] {aviso}")
        for _aba, linha, motivo in lote.ignoradas:
            self.registrar(f"[pulada] linha {linha}: {motivo}")
        self.registrar(f"--- Resultado: {lote.resumo()} ---")
        if lote.emitidas:
            self.var_chave.set(lote.emitidas[-1].chave_acesso)

    def consultar(self) -> None:
        chave = util.so_digitos(self.var_chave.get())
        if not chave:
            messagebox.showwarning(TITULO, "Informe a chave de acesso da nota.")
            return
        if not self._preparar_execucao():
            return
        self._executar_em_segundo_plano(lambda: self._rodar_consulta(chave), "Consulta")

    def _rodar_consulta(self, chave: str) -> None:
        emissor = Emissor(self.app.config, diretorio_saida=self.app.diretorio_saida,
                          progresso=self.registrar)
        resposta = emissor.consultar(self.empresa, chave)
        self.registrar(f"[ok] Consulta concluida: {resposta}")

    def baixar_danfse(self) -> None:
        chave = util.so_digitos(self.var_chave.get())
        if not chave:
            messagebox.showwarning(TITULO, "Informe a chave de acesso da nota.")
            return
        if not self._preparar_execucao():
            return
        self._executar_em_segundo_plano(lambda: self._rodar_danfse(chave), "DANFSe")

    def _rodar_danfse(self, chave: str) -> None:
        emissor = Emissor(self.app.config, diretorio_saida=self.app.diretorio_saida,
                          progresso=self.registrar)
        arquivo = emissor.baixar_danfse(self.empresa, chave)
        self.registrar(f"[ok] DANFSe salva em {arquivo}")

    def cancelar(self) -> None:
        chave = util.so_digitos(self.var_chave.get())
        if not chave:
            messagebox.showwarning(TITULO, "Informe a chave de acesso da nota.")
            return
        if not self._preparar_execucao():
            return

        janela = JanelaCancelamento(self, chave)
        self.wait_window(janela)
        if not janela.confirmado:
            return
        codigo, motivo = janela.codigo, janela.motivo
        self._executar_em_segundo_plano(
            lambda: self._rodar_cancelamento(chave, codigo, motivo), "Cancelamento")

    def _rodar_cancelamento(self, chave: str, codigo: str, motivo: str) -> None:
        emissor = Emissor(self.app.config, diretorio_saida=self.app.diretorio_saida,
                          progresso=self.registrar)
        resposta = emissor.cancelar(self.empresa, chave, codigo, motivo)
        self.registrar(f"[ok] Cancelamento enviado: {resposta}")

    # ------------------------------------------------------------------ #
    def _executar_em_segundo_plano(self, tarefa, titulo: str) -> None:
        self.trabalhando = True
        self.botao_emitir.configure(state="disabled")
        self.app.status(f"{titulo} em andamento...")

        def envelope() -> None:
            try:
                tarefa()
            except Exception as exc:  # noqa: BLE001 - erro vai para o log da aba
                self.registrar(f"[erro] {exc}")
                self.registrar(traceback.format_exc())
            finally:
                self.after(0, self._concluir, titulo)

        threading.Thread(target=envelope, daemon=True).start()

    def _concluir(self, titulo: str) -> None:
        self.trabalhando = False
        self.botao_emitir.configure(state="normal")
        self.app.status(f"{titulo} concluida.")


class JanelaCancelamento(tk.Toplevel):
    """Pergunta o motivo antes de cancelar uma nota."""

    def __init__(self, pai, chave: str):
        super().__init__(pai)
        self.title("Cancelar NFS-e")
        self.resizable(False, False)
        self.transient(pai)
        self.grab_set()
        self.confirmado = False
        self.codigo = ""
        self.motivo = ""

        quadro = ttk.Frame(self, padding=14)
        quadro.pack(fill="both", expand=True)
        ttk.Label(quadro, text=f"Chave: {chave}", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ttk.Label(quadro, text="O cancelamento e definitivo e fica registrado no Portal.",
                  foreground=COR_PRODUCAO).pack(anchor="w", pady=(2, 10))

        ttk.Label(quadro, text="Motivo").pack(anchor="w")
        self.combo = CampoCombo(quadro, tabelas.MOTIVO_CANCELAMENTO, width=48)
        self.combo.definir("1")
        self.combo.pack(fill="x", pady=(0, 8))

        ttk.Label(quadro, text="Descricao do motivo").pack(anchor="w")
        self.entrada = ttk.Entry(quadro, width=52)
        self.entrada.pack(fill="x", pady=(0, 12))
        self.entrada.focus_set()

        botoes = ttk.Frame(quadro)
        botoes.pack(fill="x")
        ttk.Button(botoes, text="Cancelar nota", command=self._confirmar).pack(side="right")
        ttk.Button(botoes, text="Voltar", command=self.destroy).pack(side="right", padx=6)

    def _confirmar(self) -> None:
        motivo = util.texto(self.entrada.get())
        if not motivo:
            messagebox.showwarning(TITULO, "Descreva o motivo do cancelamento.", parent=self)
            return
        self.codigo, self.motivo, self.confirmado = self.combo.codigo(), motivo, True
        self.destroy()


class Aplicativo(tk.Tk):
    """Janela principal: uma aba por empresa."""

    def __init__(self, diretorio_dados: Path, diretorio_saida: Path):
        super().__init__()
        self.title(TITULO)
        self.geometry("1180x860")
        self.minsize(1000, 700)
        self.configure(bg=COR_FUNDO)

        self.diretorio_saida = Path(diretorio_saida)
        self.ultima_planilha: Path | None = None
        self.abas: dict[str, AbaEmpresa] = {}

        try:
            self.config = Configuracao.carregar(diretorio_dados)
        except ErroDeConfiguracao as exc:
            messagebox.showerror(TITULO, str(exc))
            raise SystemExit(1) from exc

        self._aplicar_estilo()
        self._montar()
        self._recarregar_abas()

    # ------------------------------------------------------------------ #
    def _aplicar_estilo(self) -> None:
        estilo = ttk.Style(self)
        if "clam" in estilo.theme_names():
            estilo.theme_use("clam")
        estilo.configure(".", background=COR_FUNDO, font=("Segoe UI", 9))
        estilo.configure("TLabelframe", background=COR_FUNDO)
        estilo.configure("TLabelframe.Label", background=COR_FUNDO,
                         foreground=COR_TITULO, font=("Segoe UI", 9, "bold"))
        estilo.configure("TNotebook.Tab", padding=(16, 8), font=("Segoe UI", 9, "bold"))
        estilo.configure("Cabecalho.TLabel", background=COR_TITULO, foreground="white")

    def _montar(self) -> None:
        cabecalho = tk.Frame(self, bg=COR_TITULO)
        cabecalho.pack(fill="x")
        tk.Label(cabecalho, text="Gerador de NFS-e", bg=COR_TITULO, fg="white",
                 font=("Segoe UI", 15, "bold")).pack(side="left", padx=14, pady=10)
        tk.Label(cabecalho, text="Portal Nacional - uma aba por empresa",
                 bg=COR_TITULO, fg="#C7D2E5",
                 font=("Segoe UI", 9)).pack(side="left", pady=10)

        barra = ttk.Frame(self, padding=(12, 10, 12, 4))
        barra.pack(fill="x")
        ttk.Button(barra, text="+ Nova empresa", command=self.nova_empresa).pack(side="left")
        ttk.Button(barra, text="Remover empresa",
                   command=self.remover_empresa).pack(side="left", padx=6)
        ttk.Separator(barra, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(barra, text="Gerar planilha modelo",
                   command=self.gerar_modelo).pack(side="left")
        ttk.Button(barra, text="Emitir em TODAS as abas",
                   command=self.emitir_tudo).pack(side="left", padx=6)
        ttk.Button(barra, text="Ajuda", command=self.mostrar_ajuda).pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(4, 8))

        self.var_status = tk.StringVar(value="Pronto.")
        rodape = tk.Label(self, textvariable=self.var_status, anchor="w",
                          bg="#E3E7EE", fg="#333333", padx=12, pady=5)
        rodape.pack(fill="x", side="bottom")

    def status(self, mensagem: str) -> None:
        self.var_status.set(mensagem)

    def planilha_sugerida(self) -> Path | None:
        if self.ultima_planilha and self.ultima_planilha.exists():
            return self.ultima_planilha
        padrao = Path(__file__).resolve().parent / "modelos" / "modelo_nfse.xlsx"
        return padrao if padrao.exists() else None

    # ------------------------------------------------------------------ #
    def _recarregar_abas(self) -> None:
        for aba in self.notebook.tabs():
            self.notebook.forget(aba)
        self.abas.clear()

        if not self.config.empresas:
            vazio = ttk.Frame(self.notebook, padding=40)
            ttk.Label(vazio, text="Nenhuma empresa cadastrada ainda.",
                      font=("Segoe UI", 13, "bold")).pack(pady=(20, 8))
            ttk.Label(vazio, justify="center", text=(
                "Clique em '+ Nova empresa' para criar a primeira aba.\n\n"
                "Para cada empresa voce informa os dados do prestador e o certificado "
                "digital A1.\nA senha do certificado fica guardada cifrada - so precisa "
                "digitar uma vez.")).pack()
            ttk.Button(vazio, text="+ Nova empresa",
                       command=self.nova_empresa).pack(pady=18)
            self.notebook.add(vazio, text="  Comece por aqui  ")
            return

        for empresa in self.config.empresas:
            aba = AbaEmpresa(self.notebook, self, empresa)
            self.notebook.add(aba, text=f"  {empresa.nome}  ")
            self.abas[empresa.nome] = aba

    def aba_atual(self) -> AbaEmpresa | None:
        atual = self.notebook.select()
        for aba in self.abas.values():
            if str(aba) == atual:
                return aba
        return None

    # ------------------------------------------------------------------ #
    def nova_empresa(self) -> None:
        nome = simpledialog.askstring(
            TITULO, "Nome da empresa (sera o nome da aba aqui e na planilha):",
            parent=self)
        if not nome:
            return
        nome = util.texto(nome)[:31]
        try:
            empresa = self.config.adicionar(Empresa(nome=nome, razao_social=nome))
        except ErroDeConfiguracao as exc:
            messagebox.showerror(TITULO, str(exc))
            return
        self.config.salvar()
        self._recarregar_abas()
        self.notebook.select(self.abas[empresa.nome])
        self.status(f"Empresa {nome} criada. Preencha os dados e cadastre o certificado.")

        if messagebox.askyesno(
                TITULO, f"Quero criar a aba '{nome}' na planilha modelo agora?"):
            self.gerar_modelo()

    def remover_empresa(self) -> None:
        aba = self.aba_atual()
        if aba is None:
            messagebox.showinfo(TITULO, "Nenhuma empresa selecionada.")
            return
        nome = aba.empresa.nome
        if not messagebox.askyesno(
                TITULO, f"Remover a empresa '{nome}' do sistema?\n\n"
                "As notas ja emitidas e os arquivos da pasta 'saida' sao preservados."):
            return
        apagar = messagebox.askyesno(
            TITULO, "Apagar tambem a copia do certificado digital guardada pelo sistema?")
        self.config.remover(nome, apagar_certificado=apagar)
        self.config.salvar()
        self._recarregar_abas()
        self.status(f"Empresa {nome} removida.")

    def gerar_modelo(self) -> None:
        nomes = self.config.nomes() or ["EMPRESA EXEMPLO"]
        sugestao = "modelo_nfse.xlsx"
        destino = filedialog.asksaveasfilename(
            title="Salvar planilha modelo", defaultextension=".xlsx",
            initialfile=sugestao, filetypes=[("Planilha do Excel", "*.xlsx")])
        if not destino:
            return
        try:
            caminho = modelo_planilha.gerar(destino, nomes)
        except OSError as exc:
            messagebox.showerror(TITULO, f"Nao consegui salvar a planilha:\n{exc}\n\n"
                                         "Se ela estiver aberta no Excel, feche e tente de novo.")
            return
        self.ultima_planilha = caminho
        for aba in self.abas.values():
            aba.var_planilha.set(str(caminho))
        self.status(f"Planilha modelo gerada: {caminho}")
        if messagebox.askyesno(TITULO, f"Planilha criada com as abas:\n\n"
                                       f"{', '.join(nomes)}\n\nAbrir agora?"):
            abrir_no_sistema(caminho)

    def emitir_tudo(self) -> None:
        aba = self.aba_atual()
        if aba is None:
            messagebox.showinfo(TITULO, "Cadastre uma empresa primeiro.")
            return
        planilha = util.texto(aba.var_planilha.get())
        if not planilha or not Path(planilha).exists():
            messagebox.showwarning(TITULO, "Escolha a planilha com as notas.")
            return
        producao = [e.nome for e in self.config.empresas if e.ambiente == "producao"]
        aviso = ("\n\nEm PRODUCAO (valor fiscal): " + ", ".join(producao)) if producao else ""
        if not messagebox.askyesno(
                TITULO, "Emitir as notas de todas as abas da planilha?" + aviso,
                icon="warning" if producao else "question"):
            return

        aba.registrar("--- Emissao de todas as abas iniciada ---")
        aba._executar_em_segundo_plano(
            lambda: self._rodar_lote_completo(planilha, aba), "Emissao geral")

    def _rodar_lote_completo(self, planilha: str, aba: AbaEmpresa) -> None:
        emissor = Emissor(self.config, diretorio_saida=self.diretorio_saida,
                          simular=False, progresso=aba.registrar)
        lote = emissor.emitir_planilha(planilha)
        for aviso in lote.avisos:
            aba.registrar(f"[aviso] {aviso}")
        aba.registrar(f"--- Resultado geral: {lote.resumo()} ---")

    def mostrar_ajuda(self) -> None:
        messagebox.showinfo(TITULO, (
            "Como usar\n\n"
            "1. Crie uma aba para cada empresa e preencha CNPJ, inscricao municipal "
            "e codigo do municipio (IBGE).\n"
            "2. Cadastre o certificado A1 (.pfx) e a senha - a senha fica cifrada e "
            "so e digitada uma vez.\n"
            "3. Gere a planilha modelo: ela nasce com uma aba por empresa.\n"
            "4. Preencha uma linha por nota (a linha 3 e exemplo e nunca e enviada).\n"
            "5. Use 'Conferir sem enviar' para validar tudo antes de valer.\n"
            "6. Clique em EMITIR NOTAS. O resultado volta para a propria planilha e "
            "os XML/PDF ficam na pasta 'saida'.\n\n"
            "Comece sempre pelo ambiente de Homologacao."))


def main() -> int:
    raiz = Path(__file__).resolve().parent
    aplicativo = Aplicativo(diretorio_dados=raiz / "dados",
                            diretorio_saida=raiz / "saida")
    aplicativo.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
