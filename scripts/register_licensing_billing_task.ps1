param(
    [string]$TaskName = "Deigo Varejo Central - Licenciamento e Cobrancas",
    [string]$Horario = "06:00",
    [switch]$ExecutarSemLogin,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Manage = Join-Path $Root "manage.py"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python do ambiente virtual nao encontrado em $Python."
}
if (-not (Test-Path -LiteralPath $Manage)) {
    throw "manage.py nao encontrado em $Manage."
}
try {
    $HorarioExecucao = [datetime]::ParseExact($Horario, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
} catch {
    throw "Horario deve usar o formato HH:mm, por exemplo 06:00."
}

$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing) {
    if (-not $Force) {
        throw "A tarefa '$TaskName' ja existe. Use -Force para substituir."
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$Arguments = "`"$Manage`" processar_cobrancas_licenca"
$Action = New-ScheduledTaskAction -Execute $Python -Argument $Arguments -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $HorarioExecucao
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$Description = "Gera cobrancas mensais idempotentes e atualiza aviso, tolerancia e suspensao das licencas."

if ($ExecutarSemLogin) {
    $Credential = Get-Credential -Message "Conta de servico com acesso ao projeto e a internet para consultar o Asaas"
    if (-not $Credential) {
        throw "Credencial nao informada."
    }
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description $Description -User $Credential.UserName -Password $Credential.GetNetworkCredential().Password -RunLevel Highest | Out-Null
} else {
    $User = "$env:USERDOMAIN\$env:USERNAME"
    $Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Highest
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description $Description | Out-Null
}

Write-Host "Tarefa registrada: $TaskName"
Write-Host "Execucao diaria: $Horario"
Write-Host "Comando: $Python $Arguments"
if (-not $ExecutarSemLogin) {
    Write-Warning "A tarefa usa sessao interativa. No servidor central, prefira -ExecutarSemLogin com uma conta de servico dedicada."
}