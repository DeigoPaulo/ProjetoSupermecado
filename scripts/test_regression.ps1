param(
    [ValidateSet("rapido", "completo")]
    [string]$Perfil = "rapido",
    [switch]$KeepDb
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Manage = Join-Path $Root "manage.py"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python do ambiente virtual nao encontrado em $Python. Crie a .venv e instale requirements.txt."
}
if (-not (Test-Path -LiteralPath $Manage)) {
    throw "manage.py nao encontrado em $Manage."
}

$ArgumentosBase = @($Manage, "test", "-v", "1")
if ($KeepDb) {
    $ArgumentosBase += "--keepdb"
}

$Grupos = @(
    @("apps.configuracoes"),
    @("apps.pdv", "apps.vendas", "apps.estoque"),
    @("apps.compras", "apps.financeiro", "apps.fiscal"),
    @("apps.produtos", "apps.marketplace", "apps.licenciamento")
)

if ($Perfil -eq "completo") {
    Write-Host "`nExecutando: suite completa" -ForegroundColor Cyan
    & $Python @ArgumentosBase
    if ($LASTEXITCODE -ne 0) {
        throw "Falha na regressao: suite completa (codigo $LASTEXITCODE)."
    }
} else {
    foreach ($Grupo in $Grupos) {
        $Argumentos = @($ArgumentosBase) + $Grupo
        $Rotulo = $Grupo -join ", "
        Write-Host "`nExecutando: $Rotulo" -ForegroundColor Cyan
        & $Python @Argumentos
        if ($LASTEXITCODE -ne 0) {
            throw "Falha na regressao: $Rotulo (codigo $LASTEXITCODE)."
        }
    }
}

Write-Host "`nRegressao $Perfil concluida com sucesso." -ForegroundColor Green
