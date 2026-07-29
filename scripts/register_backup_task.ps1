param(
    [string]$TaskName = "Deigo Varejo - Backup Local",
    [string]$Horario = "02:30",
    [string]$Destino = "",
    [ValidateRange(1, 3650)]
    [int]$RetencaoDias = 15,
    [switch]$IncluirLogs,
    [string]$ServiceAccount = "SYSTEM",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Script = Join-Path $Root "scripts\backup_local.ps1"
$PowerShell = (Get-Command powershell.exe).Source
if (-not (Test-Path -LiteralPath $Script -PathType Leaf)) {
    throw "Script nao encontrado: $Script"
}
if (-not $ServiceAccount.Trim()) {
    throw "Informe uma conta de servico valida. SYSTEM e o padrao recomendado."
}
try {
    $ParsedTime = [datetime]::ParseExact($Horario, "HH:mm", $null)
} catch {
    throw "Horario invalido. Use o formato HH:mm, exemplo: 02:30."
}

$ValidationArguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $Script, "-ValidarSomente")
if ($Destino.Trim()) { $ValidationArguments += @("-Destino", $Destino) }
$ValidationOutput = & $PowerShell @ValidationArguments
if ($LASTEXITCODE -ne 0) {
    throw "A validacao das fontes de backup falhou. A tarefa nao foi registrada."
}
try {
    $Validation = $ValidationOutput | ConvertFrom-Json
} catch {
    throw "O diagnostico do backup nao retornou JSON valido."
}
if ($Validation.contrato -ne "local_backup_sources_v1") {
    throw "Contrato de diagnostico do backup inesperado."
}

$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing) {
    if (-not $Force) {
        throw "A tarefa '$TaskName' ja existe. Use -Force para substituir."
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$RunAt = Get-Date -Hour $ParsedTime.Hour -Minute $ParsedTime.Minute -Second 0
$Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$Script`" -RetencaoDias $RetencaoDias"
if ($Destino.Trim()) { $Arguments += " -Destino `"$Destino`"" }
if ($IncluirLogs) { $Arguments += " -IncluirLogs" }

$Action = New-ScheduledTaskAction -Execute $PowerShell -Argument $Arguments -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $RunAt
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal -UserId $ServiceAccount -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Executa backup local diario do Deigo Varejo sem depender de usuario conectado."

Write-Host "Tarefa registrada: $TaskName"
Write-Host "Horario diario: $Horario"
Write-Host "Conta de servico: $ServiceAccount"
Write-Host "Destino validado: $($Validation.destino)"