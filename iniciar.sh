#!/usr/bin/env bash
# Atalho do Gerador de NFS-e para Linux e macOS.
# Na primeira execucao cria o ambiente e instala as bibliotecas.
set -e
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "Preparando o sistema pela primeira vez. Isso leva alguns minutos..."
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
fi

if .venv/bin/python -c "import tkinter" 2>/dev/null; then
    exec .venv/bin/python app.py "$@"
else
    echo "Tkinter nao esta instalado (sudo apt install python3-tk)."
    echo "Abrindo a ajuda da versao de linha de comando:"
    exec .venv/bin/python nfse_cli.py --help
fi
