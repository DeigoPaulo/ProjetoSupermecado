param(
    [string]$TaskName = "MercaFlow ERP - Servidor Local",
    [string]$Bind = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$AtStartup,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Script = Join-Path $Root "scripts\run_local_server.ps1"
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

$Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$Script`" -Bind `"$Bind`" -Port $Port"
$Action = New-ScheduledTaskAction -Execute $PowerShell -Argument $Arguments -WorkingDirectory $Root
if ($AtStartup) {
    $Trigger = New-ScheduledTaskTrigger -AtStartup
} else {
    $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $User
}
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 0)
$Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Inicia o servidor local administrativo do MercaFlow ERP."

Write-Host "Tarefa registrada: $TaskName"
Write-Host "Servidor: http://$Bind`:$Port/"
