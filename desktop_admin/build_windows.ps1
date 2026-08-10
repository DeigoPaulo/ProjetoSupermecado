param(
    [ValidatePattern('^\d+\.\d+$')]
    [string]$PythonVersion = "3.12"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root ".build-venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Build = Join-Path $Root "build"
$Output = Join-Path $Root "dist\DeTecAdmin.exe"

function Assert-LastExitCode {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step falhou com código de saída $LASTEXITCODE."
    }
}

& py "-$PythonVersion" -c "import sys; print(sys.version)"
Assert-LastExitCode "Validação do Python $PythonVersion"

$RecreateVenv = -not (Test-Path -LiteralPath $Python -PathType Leaf)
if (-not $RecreateVenv) {
    $CurrentVersion = (& $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    Assert-LastExitCode "Leitura da versão do ambiente de build"
    $RecreateVenv = $CurrentVersion -ne $PythonVersion
}

if ($RecreateVenv) {
    Write-Host "Preparando ambiente de build com Python $PythonVersion..."
    & py "-$PythonVersion" -m venv --clear $Venv
    Assert-LastExitCode "Criação do ambiente de build"
}

& $Python -m pip install -r (Join-Path $Root "requirements-build.txt")
Assert-LastExitCode "Instalação das dependências de build"
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name DeTecAdmin `
    --icon (Join-Path $Root "assets\deigo-admin-cart.ico") `
    --distpath (Join-Path $Root "dist") `
    --workpath $Build `
    --specpath $Build `
    (Join-Path $Root "app.py")
Assert-LastExitCode "Geração do executável"

if (-not (Test-Path -LiteralPath $Output -PathType Leaf)) {
    throw "O PyInstaller terminou sem criar o executável esperado em $Output."
}

$OutputFile = Get-Item -LiteralPath $Output
Write-Host "Executável criado em $($OutputFile.FullName) ($($OutputFile.Length) bytes)."