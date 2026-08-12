@echo off
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
    echo Ambiente virtual nao encontrado. Rode "setup_lab.bat" primeiro.
    pause
    exit /b 1
)
start "" "%~dp0.venv\Scripts\pythonw.exe" -m app.main
