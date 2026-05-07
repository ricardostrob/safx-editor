@echo off
chcp 65001 >nul
title Sync DEV → DIST | SAFX Editor

set BASE=g:\Outros computadores\Meu MacBook Pro\Adejo Desenvolvimento\DEV\LANXESS
set SRC=%BASE%\SAFX_Editor
set DST=%BASE%\DIST\SAFX_Editor

echo.
echo  Sincronizando DEV → DIST...
echo  Origem : %SRC%
echo  Destino: %DST%
echo.

:: Copia todo o código (exceto cache e arquivos temporários)
robocopy "%SRC%" "%DST%" /E /PURGE ^
    /XD "__pycache__" ".git" "dist" "build" "*.egg-info" ^
    /XF "*.pyc" "*.pyo" "*.log" ".keystore" ^
    /NFL /NDL /NJH /NJS

:: Copia LICENSE
copy /Y "%BASE%\LICENSE" "%BASE%\DIST\LICENSE" >nul

echo  ✓ Sincronização concluída!
echo.
pause
