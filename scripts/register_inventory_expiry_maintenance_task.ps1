param(
    [string]$TaskName = "Deigo Varejo - Manutencao Inventarios Validade",
    [ValidatePattern("^([01]\d|2[0-3]):[0-5]\d$")]
    [string]$Horario = "00:15",
    [switch]$ExecutarSemLogin,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Manage = Join-Path $Root "manage.py"

if (-not (Test-Path -LiteralPath $Python)) { throw "Ambiente Python não encontrado em $Python." }
if (-not (Test-Path -LiteralPath $Manage)) { throw "manage.py não encontrado em $Manage." }
if ((Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) -and -not $Force) {
    throw "A tarefa '$TaskName' já existe. Use -Force para atualizá-la."
}

$Action = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument ('"{0}" expirar_inventarios_validade --confirmar-expiracao' -f $Manage) `
    -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $Horario
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

if ($ExecutarSemLogin) {
    Register-ScheduledTask -TaskName $TaskName -Description "Encerra rascunhos de validade vencidos sem ajustar estoque." -Action $Action -Trigger $Trigger -Settings $Settings -User "SYSTEM" -RunLevel Highest -Force:$Force | Out-Null
} else {
    $Credential = Get-Credential -Message "Conta do Windows para a manutenção diária de validade"
    Register-ScheduledTask -TaskName $TaskName -Description "Encerra rascunhos de validade vencidos sem ajustar estoque." -Action $Action -Trigger $Trigger -Settings $Settings -User $Credential.UserName -Password $Credential.GetNetworkCredential().Password -RunLevel Highest -Force:$Force | Out-Null
}

Write-Host "Tarefa '$TaskName' registrada para $Horario."
Write-Host "A rotina apenas encerra rascunhos vencidos e registra o resultado; nenhum saldo é alterado."
