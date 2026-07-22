param(
    [string]$Bind = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$CollectStatic,
    [switch]$NoMigrate
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Manage = Join-Path $Root "manage.py"
$EnvFile = Join-Path $Root ".env"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python do ambiente virtual nao encontrado em $Python. Crie a .venv e instale requirements.txt."
}
if (-not (Test-Path -LiteralPath $Manage)) {
    throw "manage.py nao encontrado em $Manage."
}
if (-not (Test-Path -LiteralPath $EnvFile)) {
    Write-Warning ".env nao encontrado. Copie .env.example para .env antes de usar em loja real."
}

Set-Location $Root

if (-not $NoMigrate) {
    & $Python $Manage migrate --noinput
}

if ($CollectStatic) {
    & $Python $Manage collectstatic --noinput
}

$Listen = "$Bind`:$Port"
Write-Host "Servidor local administrativo em http://$Listen/"
Write-Host "Use 127.0.0.1 para uso na propria maquina ou o IP da rede interna para outros computadores."

& $Python $Manage runserver $Listen
