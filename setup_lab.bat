@echo off
setlocal

echo ===============================================
echo  Automatizador de Ensaios - Setup PC Laboratorio
echo ===============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Python nao encontrado no PATH.
    echo Instale o Python 3.11+ de https://www.python.org/downloads/
    echo marcando a opcao "Add python.exe to PATH" durante a instalacao.
    echo Depois rode este script de novo.
    pause
    exit /b 1
)

echo Criando ambiente virtual em .venv ...
python -m venv "%~dp0.venv"
if errorlevel 1 (
    echo [ERRO] Falha ao criar o ambiente virtual.
    pause
    exit /b 1
)

echo Instalando dependencias (PySide6, pyvisa, python-docx)...
call "%~dp0.venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias. Veja o erro acima.
    echo Se for erro de caminho longo, mova a pasta do projeto para
    echo um caminho mais curto, tipo C:\Ensaios, e rode de novo.
    pause
    exit /b 1
)

echo.
echo ===============================================
echo  Setup concluido!
echo ===============================================
echo.
echo Para abrir o app: de um duplo clique em "iniciar_app.bat"
echo.
echo IMPORTANTE antes de usar com hardware real (GPIB):
echo  1. Confirme no NI-MAX que os instrumentos aparecem (GPIB0::N::INSTR).
echo  2. Abra o app, va em Configuracoes e DESMARQUE "Modo simulado".
echo  3. Ajuste os enderecos GPIB do UCS500N e do Chroma conforme o NI-MAX.
echo  4. Dips (4-11, Chroma) usa comandos reais do manual - deve funcionar.
echo     Burst/Surge (4-4/4-5, UCS500N) ainda usam comandos placeholder -
echo     conecta certinho mas nao aplica pulso ate o dicionario de comandos
echo     real do UCS500N ser adicionado em app\instruments\ucs500n_commands.py
echo.
pause
