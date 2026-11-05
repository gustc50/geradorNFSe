"""Roteiro completo da interface grafica, clicando nos botoes de verdade.

As caixas de dialogo sao respondidas automaticamente e o Portal e simulado.
Cobre: cadastro de empresa e certificado, reabertura do programa, planilha
modelo, simulacao, emissao, numeracao entre emissoes, confirmacao de producao,
consulta, DANFSe, cancelamento, emissao em todas as abas e remocao.

E pulado quando a maquina nao tem Tkinter ou tela (ex.: servidor sem monitor).
"""

import os
import sys
import time
from unittest.mock import patch

import pytest
from openpyxl import load_workbook

tk = pytest.importorskip("tkinter")
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("sem tela disponivel", allow_module_level=True)

import app as gui                                   # noqa: E402
from nfse.api import RespostaEmissao                # noqa: E402
from tests.apoio import gerar_pfx                   # noqa: E402


def test_roteiro_completo_da_interface(tmp_path):
    try:
        tk.Tk().destroy()
    except tk.TclError:
        pytest.skip("Tk nao consegue abrir janela neste ambiente")

    base = tmp_path
    pfx = gerar_pfx(base / "meu_certificado.pfx", senha="Senha@123")
    dialogos = []
    falhas = []
    resultados = []

    def responde(resposta):
        def f(titulo, mensagem, **kw):
            dialogos.append(mensagem.splitlines()[0][:90])
            return resposta
        return f

    def esperar(aba, segundos=30):
        fim = time.time() + segundos
        while aba.trabalhando and time.time() < fim:
            aba.update()
            time.sleep(0.05)
        aba.update()
        aba._drenar_fila()

    def log(aba):
        return aba.texto_log.get("1.0", "end")

    def ok(cond, msg):
        if not cond:
            falhas.append(msg)
        return cond

    with patch.object(gui.messagebox, "showinfo", responde(None)), \
         patch.object(gui.messagebox, "showwarning", responde(None)), \
         patch.object(gui.messagebox, "showerror", responde(None)), \
         patch.object(gui.messagebox, "askyesno", responde(False)):

        a = gui.Aplicativo(diretorio_dados=base / "dados", diretorio_saida=base / "saida")
        a.update()
        resultados.append(ok([a.notebook.tab(t, "text").strip() for t in a.notebook.tabs()] == ["Comece por aqui"],
                             "sem empresas mostra a aba 'Comece por aqui'"))

        # 1. Nova empresa pelo botao
        with patch.object(gui.simpledialog, "askstring", lambda *a_, **k: "CONTABIL NGF"):
            a.nova_empresa()
        a.update()
        aba = a.abas.get("CONTABIL NGF")
        resultados.append(ok(aba is not None, "botao '+ Nova empresa' cria a aba"))

        # 2. Dados da empresa
        aba.var_cnpj.set("11.222.333/0001-81"); aba.var_im.set("987654")
        aba.var_municipio.set("3550308"); aba.var_email.set("fiscal@ngf.com.br")
        aba.var_fone.set("(11) 3333-4444")
        aba.combo_simples.definir("3"); aba._alternar_regime_sn()
        resultados.append(ok(str(aba.combo_regime_sn.cget("state")) == "readonly" and aba.combo_regime_sn.codigo() == "1",
                             "Simples ME/EPP habilita e preenche o regime de apuracao"))
        aba.salvar()

        # 3. Certificado: senha errada, depois certa
        aba.var_certificado.set(str(pfx)); aba.var_senha.set("errada")
        dialogos.clear(); aba.salvar_certificado()
        resultados.append(ok(any("Senha incorreta" in d for d in dialogos), "senha errada do certificado e avisada"))
        aba.var_senha.set("Senha@123"); aba.salvar_certificado(); a.update()
        resultados.append(ok(aba.var_senha.get() == gui.SENHA_GUARDADA and "vence em" in aba.rotulo_certificado.cget("text"),
                             "certificado guardado e senha mascarada"))
        salvo = (base / "dados" / "empresas.json").read_text(encoding="utf-8")
        resultados.append(ok("Senha@123" not in salvo and "aesgcm:" in salvo, "senha gravada cifrada no disco"))

        # 4. Reabrir o programa: tudo continua la
        a.destroy()
        a = gui.Aplicativo(diretorio_dados=base / "dados", diretorio_saida=base / "saida"); a.update()
        aba = a.abas["CONTABIL NGF"]
        resultados.append(ok(aba.var_senha.get() == gui.SENHA_GUARDADA and aba.combo_simples.codigo() == "3",
                             "ao reabrir, empresa e certificado continuam cadastrados"))
        # salvar certificado de novo sem redigitar a senha
        dialogos.clear(); aba.salvar_certificado()
        resultados.append(ok(not any("Senha" in d for d in dialogos), "re-salvar o certificado nao pede a senha de novo"))

        # 5. Gerar planilha modelo pelo botao
        planilha = base / "notas.xlsx"
        with patch.object(gui.filedialog, "asksaveasfilename", lambda **k: str(planilha)):
            a.gerar_modelo()
        resultados.append(ok(planilha.exists() and "CONTABIL NGF" in load_workbook(planilha).sheetnames,
                             "planilha modelo gerada com a aba da empresa"))
        wb = load_workbook(planilha); ws = wb["CONTABIL NGF"]; t = {c.value: c.column for c in ws[2]}
        for linha, valores in {
            4: {"Tipo doc. tomador": "CNPJ", "CNPJ/CPF do tomador": "11444777000161",
                "Nome/Razao social do tomador": "CLIENTE ALFA", "Cod. tributacao nacional": "010701",
                "Descricao do servico": "Honorarios", "Valor do servico": 1500,
                "Tributacao do ISSQN": "1", "Retencao do ISSQN": "1", "Aliquota ISS (%)": 2},
            5: {"Tipo doc. tomador": "CNPJ", "CNPJ/CPF do tomador": "11444777000162",
                "Nome/Razao social do tomador": "CNPJ ERRADO", "Cod. tributacao nacional": "010701",
                "Descricao do servico": "x", "Valor do servico": 10,
                "Tributacao do ISSQN": "1", "Retencao do ISSQN": "1"}}.items():
            for k, v in valores.items(): ws.cell(row=linha, column=t[k]).value = v
        wb.save(planilha)
        aba.var_planilha.set(str(planilha))

        # 6. Simulacao
        aba.emitir(simular=True); esperar(aba)
        resultados.append(ok("1 simulada(s), 1 com erro" in log(aba), "simulacao: 1 ok, 1 com erro (CNPJ invalido)"))
        resultados.append(ok("CNPJ do tomador invalido" in log(aba), "erro da linha aparece no log"))

        # 7. Emissao real (Portal simulado)
        with patch("nfse.emissor.ClienteNFSe") as cliente:
            cliente.return_value.emitir.return_value = RespostaEmissao(
                chave_acesso="3" * 50, numero_nfse="45", xml_nfse=b"<NFSe/>")
            aba.emitir(simular=False); esperar(aba)
        resultados.append(ok("1 emitida(s)" in log(aba) and aba.var_chave.get() == "3" * 50,
                             "emissao: nota autorizada e chave preenchida na tela"))
        ws = load_workbook(planilha)["CONTABIL NGF"]
        resultados.append(ok(ws.cell(row=4, column=t["Status"]).value == "EMITIDA" and
                             ws.cell(row=4, column=t["Chave de acesso"]).value == "3" * 50,
                             "status e chave gravados na planilha"))

        resultados.append(ok(aba.var_proximo.get() == "2", "tela mostra o proximo numero atualizado (2) apos emitir"))
        resultados.append(ok(not a.ocupado and str(aba.botao_emitir.cget("state")) == "normal",
                             "botao EMITIR liberado ao terminar"))

        # 8. Rodar de novo: nao reenvia a emitida e a linha nova usa o numero SEGUINTE
        wb = load_workbook(planilha); ws = wb["CONTABIL NGF"]
        for k, v in {"Tipo doc. tomador": "CPF", "CNPJ/CPF do tomador": "52998224725",
                     "Nome/Razao social do tomador": "MARIA", "Cod. tributacao nacional": "010701",
                     "Descricao do servico": "IRPF", "Valor do servico": 800,
                     "Tributacao do ISSQN": "1", "Retencao do ISSQN": "1"}.items():
            ws.cell(row=6, column=t[k]).value = v
        wb.save(planilha)
        enviados = []
        def captura(xml):
            enviados.append(xml.split(b"<nDPS>")[1].split(b"</nDPS>")[0].decode())
            return RespostaEmissao(chave_acesso="4" * 50, numero_nfse="46")
        with patch("nfse.emissor.ClienteNFSe") as cliente:
            cliente.return_value.emitir.side_effect = captura
            aba.emitir(simular=False); esperar(aba)
        resultados.append(ok(enviados == ["2"], f"segunda emissao: so a linha nova, com nDPS 2 (enviado: {enviados})"))
        resultados.append(ok(aba.var_proximo.get() == "3", "contador vai para 3"))

        # 9. Producao exige confirmacao (respondendo 'Nao')
        aba.var_ambiente.set("producao"); aba._atualizar_aviso_ambiente()
        dialogos.clear()
        with patch("nfse.emissor.ClienteNFSe") as cliente:
            aba.emitir(simular=False); esperar(aba)
            resultados.append(ok(any("PRODUCAO" in d for d in dialogos) and not cliente.called,
                                 "producao pede confirmacao e 'Nao' cancela o envio"))
        aba.var_ambiente.set("homologacao"); aba.salvar(silencioso=True)

        # 10. Consulta e DANFSe
        with patch("nfse.api.ClienteNFSe.consultar") as consultar, \
             patch("nfse.api.ClienteNFSe.baixar_danfse", return_value=base / "x.pdf") as danfse:
            consultar.return_value = RespostaEmissao(chave_acesso="3" * 50, bruto={"situacao": "ok"})
            aba.consultar(); esperar(aba)
            aba.baixar_danfse(); esperar(aba)
            resultados.append(ok(consultar.called and danfse.called and "DANFSe salva" in log(aba),
                                 "botoes Consultar e Baixar DANFSe funcionam"))

        # 11. Janela de cancelamento: motivo curto e recusado
        j = gui.JanelaCancelamento(aba, "3" * 50); a.update()
        resultados.append(ok(j.combo.cget("values") == ("1 - Erro na emissao", "2 - Servico nao prestado", "9 - Outros"),
                             "motivos de cancelamento sao os do schema oficial"))
        j.entrada.insert(0, "Erro"); dialogos.clear(); j._confirmar()
        resultados.append(ok(not j.confirmado and any("15 caracteres" in d for d in dialogos),
                             "cancelamento recusa motivo com menos de 15 caracteres"))
        j.entrada.insert("end", " no valor da nota"); j._confirmar()
        resultados.append(ok(j.confirmado and j.codigo == "1", "cancelamento aceita motivo valido"))

        # 11b. Emitir em TODAS as abas (com segunda empresa sem certificado -> aviso)
        with patch.object(gui.simpledialog, "askstring", lambda *a_, **k: "SEGUNDA EMPRESA"):
            a.nova_empresa()
        a.update()
        a.notebook.select(a.abas["CONTABIL NGF"]); aba = a.abas["CONTABIL NGF"]
        with patch.object(gui.messagebox, "askyesno", responde(True)), \
             patch("nfse.emissor.ClienteNFSe") as cliente:
            a.emitir_tudo(); esperar(aba)
        resultados.append(ok("Resultado geral" in log(aba) and not a.ocupado, "emitir em todas as abas conclui"))

        # 11c. Planilha aberta no Excel: avisa e nao envia nada
        aba = a.abas["CONTABIL NGF"]
        dialogos.clear()
        with patch.object(gui, "planilha_bloqueada", return_value=True), \
             patch("nfse.emissor.ClienteNFSe") as cliente:
            aba.emitir(simular=False)
            esperar(aba)
            resultados.append(ok(any("aberta no Excel" in d for d in dialogos)
                                 and not cliente.called,
                                 "planilha aberta no Excel: avisa e nao envia"))

        # 12. Remover empresa
        with patch.object(gui.messagebox, "askyesno", responde(True)):
            a.remover_empresa()
        resultados.append(ok("CONTABIL NGF" not in a.abas, "remover empresa"))
        a.destroy()

    assert not falhas, "Falhas na interface: " + "; ".join(falhas)
