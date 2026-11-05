#!/usr/bin/env bash
# Atalho do Gerador de NFS-e para Linux e macOS.
# Na primeira execucao cria o ambiente e instala as bibliotecas.
set -e
cd "$(dirname "$0")"

instalado() {
    [ -x ".venv/bin/python" ] && \
        .venv/bin/python -c "import openpyxl, lxml, requests, cryptography" 2>/dev/null
}

if ! instalado; then
    # Tambem cobre uma instalacao anterior interrompida pela metade.
    echo "Preparando o sistema (so na primeira vez). Isso leva alguns minutos..."
    [ -x ".venv/bin/python" ] || python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
fi

if .venv/bin/python -c "import tkinter" 2>/dev/null; then
    exec .venv/bin/python app.py "$@"
else
    echo "Tkinter nao esta instalado (Linux: sudo apt install python3-tk)."
    echo "Abrindo a ajuda da versao de linha de comando:"
    exec .venv/bin/python nfse_cli.py --help
fi
