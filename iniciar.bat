@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Ambiente Python nao encontrado. Siga a instalacao no README.md.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m assistente_pc --gui --model qwen2.5:7b
if errorlevel 1 pause
