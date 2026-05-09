# Gera SAFX_Editor/dist/SAFX_Editor e, se existir iscc, SAFX_Editor/release/SAFX_Editor_Setup.exe
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "== SAFX Editor — build Windows (PyInstaller) ==" -ForegroundColor Cyan
python -m pip install -q -r requirements.txt -r packaging/requirements-build.txt
python -m PyInstaller --clean --noconfirm SAFX_Editor.spec

$Iss = Join-Path $PSScriptRoot "SAFX_Editor_installer.iss"
$Iscc = Get-Command iscc -ErrorAction SilentlyContinue
if ($Iscc) {
    Write-Host "== Arte do instalador (logo / assistente) ==" -ForegroundColor Cyan
    python packaging/branding/build_assets.py --inno-only
    Write-Host "== Compilando instalador Inno Setup ==" -ForegroundColor Cyan
    & iscc $Iss
    Write-Host "Instalador: $Root\release\SAFX_Editor_Setup.exe" -ForegroundColor Green
} else {
    Write-Host "Inno Setup (iscc) não está no PATH. Instale: https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
    Write-Host "App portátil pronto em: $Root\dist\SAFX_Editor\SAFX_Editor.exe" -ForegroundColor Green
}

# Copia entrega completa para a pasta na raiz do repositório (cliente Windows)
$RepoRoot = Split-Path -Parent $Root
$Windons = Join-Path $RepoRoot "Windons"
$Portable = Join-Path $Root "dist\SAFX_Editor"
if (Test-Path $Portable) {
    Write-Host "== A copiar para $Windons ==" -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $Windons | Out-Null
    robocopy $Portable (Join-Path $Windons "SAFX_Editor") /E /XO /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy falhou (código $LASTEXITCODE)" }
    $setup = Join-Path $Root "release\SAFX_Editor_Setup.exe"
    if (Test-Path $setup) {
        Copy-Item $setup $Windons -Force
        Write-Host "Instalador copiado: $Windons\SAFX_Editor_Setup.exe" -ForegroundColor Green
    }
    Write-Host "App portátil copiado: $Windons\SAFX_Editor\" -ForegroundColor Green
}
