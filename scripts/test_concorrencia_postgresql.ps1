param(
    [string]$TestLabel = "apps.compras.test_concorrencia_finalizacao"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "Runtime Python do projeto não encontrado em .venv\Scripts\python.exe."
}

$RequiredVariables = @("POSTGRES_DB", "POSTGRES_TEST_DB", "POSTGRES_HOST", "POSTGRES_USER")
foreach ($VariableName in $RequiredVariables) {
    $Value = [Environment]::GetEnvironmentVariable($VariableName, "Process")
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "Configure $VariableName no ambiente do processo antes de executar o teste."
    }
}

$SourceDatabase = [Environment]::GetEnvironmentVariable("POSTGRES_DB", "Process")
$TestDatabase = [Environment]::GetEnvironmentVariable("POSTGRES_TEST_DB", "Process")
if ($TestDatabase -notmatch '^test_[A-Za-z0-9_]+$') {
    throw "POSTGRES_TEST_DB deve começar com test_ e conter somente letras, números e sublinhado."
}
if ($SourceDatabase.Equals($TestDatabase, [StringComparison]::OrdinalIgnoreCase)) {
    throw "POSTGRES_TEST_DB deve ser diferente de POSTGRES_DB."
}
if ($TestLabel -notmatch '^apps\.[A-Za-z0-9_.]+$') {
    throw "TestLabel deve ser um caminho de teste Django dentro de apps."
}

[Environment]::SetEnvironmentVariable("DATABASE_URL", $null, "Process")
[Environment]::SetEnvironmentVariable("POSTGRES_CONN_MAX_AGE", "0", "Process")

Push-Location $ProjectRoot
try {
    & $PythonPath manage.py test $TestLabel --verbosity 2 --noinput
    if ($LASTEXITCODE -ne 0) {
        throw "O teste concorrente PostgreSQL falhou com código $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
