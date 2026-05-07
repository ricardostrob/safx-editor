@echo off
chcp 65001 >nul
title Publicar no GitHub | SAFX Editor

echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║        SAFX Editor — Publicar no GitHub                 ║
echo  ║       Adejo Tecnologia / TecTex  ^|  (11) 99308-3138     ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.

:: Define o nome do repositório
set REPO_NAME=safx-editor

:: Verifica GitHub CLI
where gh >nul 2>&1
if errorlevel 1 (
    echo  [AVISO] GitHub CLI nao encontrado.
    echo.
    echo  Instale em: https://cli.github.com
    echo  Depois rode este script novamente.
    echo.
    echo  Ou siga o processo manual:
    echo  1. Acesse https://github.com/new
    echo  2. Crie o repositorio: %REPO_NAME%
    echo  3. Copie a URL SSH ou HTTPS
    echo  4. Execute:
    echo     cd "g:\Outros computadores\Meu MacBook Pro\Adejo Desenvolvimento\DEV\LANXESS"
    echo     git remote add origin https://github.com/SEU_USUARIO/%REPO_NAME%.git
    echo     git branch -M main
    echo     git push -u origin main
    pause
    exit /b 1
)

echo  Fazendo login no GitHub (abrira o navegador)...
gh auth login

echo.
echo  Criando repositorio privado no GitHub...
cd /d "g:\Outros computadores\Meu MacBook Pro\Adejo Desenvolvimento\DEV\LANXESS"
gh repo create %REPO_NAME% --private --source=. --remote=origin --push --description "SAFX Editor - MasterSAF Data Adjuster - Adejo Tecnologia/TecTex"

if errorlevel 1 (
    echo.
    echo  [ERRO] Falha ao criar repositorio. Tente manualmente.
    pause
    exit /b 1
)

echo.
echo  ✓ Repositorio criado e codigo publicado com sucesso!
echo.
gh repo view --web
pause
