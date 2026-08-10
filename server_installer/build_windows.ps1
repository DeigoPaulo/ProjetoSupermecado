param(
    [ValidatePattern('^\d+\.\d+$')]
    [string]$PythonVersion = "3.12"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $Root "..")).Path
$Venv = Join-Path $Root ".build-venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Output = Join-Path $Root "dist\Instalar DeTec Server.exe"
$Icon = Join-Path $ProjectRoot "desktop_admin\assets\deigo-admin-cart.ico"

function Assert-LastExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step falhou com codigo de saida $LASTEXITCODE." }
}

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    & py "-$PythonVersion" -m venv $Venv
    Assert-LastExitCode "Criacao do ambiente de build"
}
& $Python -m pip install -r (Join-Path $Root "requirements-build.txt")
Assert-LastExitCode "Instalacao das dependencias de build"
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --uac-admin `
    --name "Instalar DeTec Server" `
    --icon $Icon `
    --distpath (Join-Path $Root "dist") `
    --workpath (Join-Path $Root "build") `
    --specpath (Join-Path $Root "build") `
    (Join-Path $Root "launcher.py")
Assert-LastExitCode "Geracao do executavel"

if (-not (Test-Path -LiteralPath $Output -PathType Leaf)) {
    throw "O executavel nao foi gerado em $Output."
}
Write-Host "Instalador gerado: $Output"
