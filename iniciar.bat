@echo off
REM Atalho do Gerador de NFS-e para Windows.
REM Na primeira execucao cria o ambiente e instala as bibliotecas.
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)

if not exist ".venv\Scripts\python.exe" (
    echo Preparando o sistema pela primeira vez. Isso leva alguns minutos...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo.
        echo Nao encontrei o Python. Instale em https://python.org/downloads
        echo Marque a opcao "Add python.exe to PATH" durante a instalacao.
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

".venv\Scripts\python.exe" app.py
if errorlevel 1 pause
