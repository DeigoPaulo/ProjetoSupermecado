param(
    [string]$TaskName = "MercaFlow ERP - Sincronizacao",
    [int]$IntervaloMinutos = 1,
    [int]$LimiteSaida = 50,
    [int]$LimiteEntrada = 50,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Manage = Join-Path $Root "manage.py"
$User = "$env:USERDOMAIN\$env:USERNAME"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python do ambiente virtual nao encontrado em $Python. Crie a .venv e instale requirements.txt."
}
if (-not (Test-Path -LiteralPath $Manage)) {
    throw "manage.py nao encontrado em $Manage."
}
if ($IntervaloMinutos -lt 1) {
    throw "IntervaloMinutos deve ser maior ou igual a 1."
}
if ($LimiteSaida -lt 1 -or $LimiteEntrada -lt 1) {
    throw "LimiteSaida e LimiteEntrada devem ser maiores ou iguais a 1."
}

$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing) {
    if (-not $Force) {
        throw "A tarefa '$TaskName' ja existe. Use -Force para substituir."
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$Arguments = "`"$Manage`" processar_sincronizacao_completa --limite-saida $LimiteSaida --limite-entrada $LimiteEntrada"
$Action = New-ScheduledTaskAction -Execute $Python -Argument $Arguments -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $IntervaloMinutos)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Processa filas de saida e entrada da sincronizacao loja-nuvem do MercaFlow ERP."

Write-Host "Tarefa registrada: $TaskName"
Write-Host "Intervalo: a cada $IntervaloMinutos minuto(s)"
Write-Host "Comando: $Python $Arguments"
