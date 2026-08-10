param(
    [string]$Python = "python",
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Venv = Join-Path $Root ".venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$Requirements = Join-Path $Root "requirements.txt"
$EnvExample = Join-Path $Root ".env.example"
$EnvFile = Join-Path $Root ".env"

function Test-Python312 {
    param([string]$Executable)

    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf) -and -not (Get-Command $Executable -ErrorAction SilentlyContinue)) {
        return $false
    }

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        & $Executable -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

Set-Location $Root

if (-not (Test-Python312 $Python)) {
    throw "Python 3.12 ou superior nao encontrado em '$Python'. Informe o executavel com -Python 'C:\caminho\python.exe'."
}

$VenvValida = Test-Python312 $VenvPython
if ($VenvValida) {
    $PythonBase = (& $Python -c "import os,sys; print(os.path.normcase(os.path.realpath(sys.executable)))" | Select-Object -Last 1).Trim()
    $VenvBase = (& $VenvPython -c "import os,sys; print(os.path.normcase(os.path.realpath(sys._base_executable)))" | Select-Object -Last 1).Trim()
    if ($PythonBase -ne $VenvBase) {
        Write-Warning "O ambiente virtual aponta para outro Python ($VenvBase). Ele sera recriado com $PythonBase."
        $VenvValida = $false
    }
}
if (-not $VenvValida -and (Test-Path -LiteralPath $Venv)) {
    $Sufixo = Get-Date -Format "yyyyMMdd-HHmmss"
    $BackupVenv = Join-Path $Root ".venv.broken-$Sufixo"
    Move-Item -LiteralPath $Venv -Destination $BackupVenv
    Write-Warning "Ambiente virtual anterior preservado em $BackupVenv"
}

if (-not $VenvValida) {
    & $Python -m venv $Venv
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao criar o ambiente virtual em $Venv."
    }
}

if (-not $SkipInstall) {
    & $VenvPython -m pip install -r $Requirements
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao instalar as dependencias de requirements.txt."
    }
}

if (-not (Test-Path -LiteralPath $EnvFile)) {
    Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
    Write-Host ".env criado a partir de .env.example."
}

& $VenvPython manage.py check
if ($LASTEXITCODE -ne 0) {
    throw "O Django encontrou problemas na configuracao."
}

& $VenvPython manage.py makemigrations --check --dry-run
if ($LASTEXITCODE -ne 0) {
    throw "Existem alteracoes de models sem migration."
}

Write-Host "Ambiente local pronto. Inicie com:"
Write-Host "  .\.venv\Scripts\python.exe manage.py migrate"
Write-Host "  .\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000"
