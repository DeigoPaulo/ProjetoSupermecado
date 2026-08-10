param(
    [ValidatePattern('^\d+\.\d+$')]
    [string]$PythonVersion = "3.12",
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $Root "..")).Path
$Venv = Join-Path $Root ".build-venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$PortablePython = Join-Path $ProjectRoot "dist\python-runtime-msi\python.exe"
$Output = Join-Path $Root "dist\Instalar DeTec Server.exe"
$Icon = Join-Path $ProjectRoot "desktop_admin\assets\deigo-admin-cart.ico"

function Assert-LastExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step falhou com codigo de saida $LASTEXITCODE." }
}

function Test-Python([string]$Executable) {
    if (-not $Executable -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $false }
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        & $Executable -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

if (-not $PythonPath) {
    if (Test-Python $PortablePython) {
        $PythonPath = $PortablePython
    } else {
        $PythonPath = (& py "-$PythonVersion" -c "import sys; print(sys.executable)" | Select-Object -Last 1).Trim()
    }
}
if (-not (Test-Python $PythonPath)) { throw "Python 3.12 valido nao encontrado para o build." }

$VenvValida = Test-Python $Python
if ($VenvValida) {
    $BaseEsperada = (& $PythonPath -c "import os,sys; print(os.path.normcase(os.path.realpath(sys.executable)))" | Select-Object -Last 1).Trim()
    $BaseAtual = (& $Python -c "import os,sys; print(os.path.normcase(os.path.realpath(sys._base_executable)))" | Select-Object -Last 1).Trim()
    $VenvValida = $BaseEsperada -eq $BaseAtual
}
if (-not $VenvValida -and (Test-Path -LiteralPath $Venv)) {
    Remove-Item -LiteralPath $Venv -Recurse -Force
}
if (-not $VenvValida) {
    & $PythonPath -m venv $Venv
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
