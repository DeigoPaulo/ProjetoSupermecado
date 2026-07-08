$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root ".venv-build"
$Python = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $Python)) {
    py -3 -m venv $Venv
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $Root "requirements-build.txt")
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "SupermercadoPDV" `
    --distpath (Join-Path $Root "dist") `
    --workpath (Join-Path $Root "build") `
    (Join-Path $Root "app.py")

Write-Host "Executavel gerado em desktop_pdv\dist\SupermercadoPDV.exe"
