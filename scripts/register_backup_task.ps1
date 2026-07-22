param(
    [string]$TaskName = "MercaFlow ERP - Backup Local",
    [string]$Horario = "02:30",
    [string]$Destino = "",
    [int]$RetencaoDias = 15,
    [switch]$IncluirLogs,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Script = Join-Path $Root "scripts\backup_local.ps1"
$PowerShell = (Get-Command powershell.exe).Source
$User = "$env:USERDOMAIN\$env:USERNAME"

if (-not (Test-Path -LiteralPath $Script)) {
    throw "Script nao encontrado: $Script"
}

$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing) {
    if (-not $Force) {
        throw "A tarefa '$TaskName' ja existe. Use -Force para substituir."
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

try {
    $ParsedTime = [datetime]::ParseExact($Horario, "HH:mm", $null)
} catch {
    throw "Horario invalido. Use o formato HH:mm, exemplo: 02:30."
}

$RunAt = Get-Date -Hour $ParsedTime.Hour -Minute $ParsedTime.Minute -Second 0
$Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$Script`" -RetencaoDias $RetencaoDias"
if ($Destino.Trim()) {
    $Arguments += " -Destino `"$Destino`""
}
if ($IncluirLogs) {
    $Arguments += " -IncluirLogs"
}

$Action = New-ScheduledTaskAction -Execute $PowerShell -Argument $Arguments -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $RunAt
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Executa backup local diario do MercaFlow ERP."

Write-Host "Tarefa registrada: $TaskName"
Write-Host "Horario diario: $Horario"
