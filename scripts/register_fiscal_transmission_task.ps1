param(
    [string]$TaskName = "Deigo Varejo - Transmissao Fiscal",
    [int]$IntervaloMinutos = 1,
    [int]$Limite = 50,
    [switch]$SimularHomologacao,
    [switch]$ExecutarSemLogin,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
if ($IntervaloMinutos -lt 1 -or $IntervaloMinutos -gt 60) { throw "IntervaloMinutos deve ficar entre 1 e 60." }
if ($Limite -lt 1 -or $Limite -gt 200) { throw "Limite deve ficar entre 1 e 200." }
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Manage = Join-Path $Root "manage.py"
if (-not (Test-Path -LiteralPath $Python)) { throw "Python do ambiente virtual nao encontrado em $Python." }
if (-not (Test-Path -LiteralPath $Manage)) { throw "manage.py nao encontrado em $Manage." }
$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing) {
    if (-not $Force) { throw "A tarefa '$TaskName' ja existe. Use -Force para substituir." }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
$Arguments = "`"$Manage`" processar_fila_fiscal --limite $Limite"
if ($SimularHomologacao) { $Arguments += " --simular-homologacao" }
$Action = New-ScheduledTaskAction -Execute $Python -Argument $Arguments -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes $IntervaloMinutos)
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$Description = "Transmite documentos fiscais pendentes com idempotencia, lease e retentativa exponencial."
if ($ExecutarSemLogin) {
    $Credential = Get-Credential -Message "Conta de servico com acesso ao certificado A1 e ao adaptador SEFAZ"
    if (-not $Credential) { throw "Credencial nao informada." }
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description $Description -User $Credential.UserName -Password $Credential.GetNetworkCredential().Password -RunLevel Highest | Out-Null
} else {
    $User = "$env:USERDOMAIN\$env:USERNAME"
    $Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Highest
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description $Description | Out-Null
}
Write-Host "Tarefa registrada: $TaskName"
Write-Host "Intervalo: $IntervaloMinutos minuto(s)"
Write-Host "Comando: $Python $Arguments"
if ($SimularHomologacao) { Write-Warning "A simulacao de homologacao foi habilitada nesta tarefa. Nao use esse parametro em producao." }
if (-not $ExecutarSemLogin) { Write-Warning "Para servidor, prefira -ExecutarSemLogin com conta de servico dedicada." }