@echo off
chcp 65001 >nul
title SAFX Editor — Instalação | Adejo Tecnologia

echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║          SAFX Editor — MasterSAF Data Adjuster          ║
echo  ║       Adejo Tecnologia / TecTex  ^|  (11) 99308-3138     ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.
echo  Instalando dependências...
echo.

:: Verifica Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Python nao encontrado!
    echo  Acesse https://python.org/downloads e instale Python 3.11 ou superior.
    echo.
    pause
    exit /b 1
)

:: Instala dependências
cd /d "%~dp0SAFX_Editor"
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet

if errorlevel 1 (
    echo.
    echo  [ERRO] Falha ao instalar dependências. Verifique sua conexão.
    pause
    exit /b 1
)

echo.
echo  ✓ Instalação concluída com sucesso!
echo.

:: Cria atalho na área de trabalho
python -c "
import os, sys
from pathlib import Path
try:
    import winshell
    from win32com.client import Dispatch
    desktop = winshell.desktop()
    path = str(Path(desktop) / 'SAFX Editor.lnk')
    shell = Dispatch('WScript.Shell')
    shortcut = shell.CreateShortCut(path)
    shortcut.Targetpath = sys.executable.replace('python.exe','pythonw.exe')
    shortcut.Arguments = str(Path(r'%~dp0') / 'SAFX_Editor' / 'SAFX_Editor.pyw')
    shortcut.WorkingDirectory = str(Path(r'%~dp0') / 'SAFX_Editor')
    icon = str(Path(r'%~dp0') / 'SAFX_Editor' / 'assets' / 'adejo_icon.ico')
    if Path(icon).exists():
        shortcut.IconLocation = icon
    shortcut.Description = 'SAFX Editor - Adejo Tecnologia'
    shortcut.save()
    print('Atalho criado na area de trabalho.')
except Exception as e:
    print(f'Atalho nao criado: {e}')
" 2>nul

echo.
echo  Iniciando o SAFX Editor...
echo.
timeout /t 2 /nobreak >nul

cd /d "%~dp0SAFX_Editor"
start "" pythonw SAFX_Editor.pyw
exit /b 0
