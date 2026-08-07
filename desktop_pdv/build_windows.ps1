param(
    [ValidatePattern('^\d+\.\d+$')]
    [string]$PythonVersion = "3.12"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root ".build-venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Output = Join-Path $Root "dist\DeTecPDV.exe"
$Spec = Join-Path $Root "DeTecPDV.spec"

function Assert-LastExitCode {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step falhou com codigo de saida $LASTEXITCODE."
    }
}

& py "-$PythonVersion" -c "import sys; print(sys.version)"
Assert-LastExitCode "Validacao do Python $PythonVersion"

$RecreateVenv = -not (Test-Path -LiteralPath $Python -PathType Leaf)
if (-not $RecreateVenv) {
    $CurrentVersion = (& $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    Assert-LastExitCode "Leitura da versao do ambiente de build"
    $RecreateVenv = $CurrentVersion -ne $PythonVersion
}

if ($RecreateVenv) {
    Write-Host "Preparando ambiente de build com Python $PythonVersion..."
    & py "-$PythonVersion" -m venv --clear $Venv
    Assert-LastExitCode "Criacao do ambiente de build"
}

& $Python -m pip --version
Assert-LastExitCode "Validacao do pip"
& $Python -m pip install -r (Join-Path $Root "requirements-build.txt")
Assert-LastExitCode "Instalacao das dependencias de build"
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath (Join-Path $Root "dist") `
    --workpath (Join-Path $Root "build") `
    $Spec
Assert-LastExitCode "Geracao do executavel"

if (-not (Test-Path -LiteralPath $Output -PathType Leaf)) {
    throw "O PyInstaller terminou sem criar o executavel esperado em $Output."
}

$OutputFile = Get-Item -LiteralPath $Output
Write-Host "Executavel gerado em $($OutputFile.FullName) ($($OutputFile.Length) bytes)."