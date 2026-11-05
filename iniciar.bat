@echo off
REM Atalho do Gerador de NFS-e para Windows.
REM Na primeira execucao cria o ambiente e instala as bibliotecas.
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")

REM Ja instalado e completo? (tambem detecta instalacao interrompida pela metade)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import openpyxl, lxml, requests, cryptography" >nul 2>nul
    if not errorlevel 1 goto abrir
)

echo Preparando o sistema (so na primeira vez). Isso leva alguns minutos...
if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv
    if errorlevel 1 goto sem_python
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Nao consegui instalar as bibliotecas. Confira a conexao com a internet
    echo e abra este arquivo de novo.
    pause
    exit /b 1
)

:abrir
".venv\Scripts\python.exe" app.py
if errorlevel 1 pause
exit /b 0

:sem_python
echo.
echo Nao encontrei o Python. Instale em https://python.org/downloads
echo Marque a opcao "Add python.exe to PATH" durante a instalacao.
pause
exit /b 1
