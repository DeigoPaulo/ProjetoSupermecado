param(
    [string]$ServiceDirectory = "$env:ProgramData\MercaFlow\ServidorLocal",
    [switch]$RemoveServiceFiles
)

$ErrorActionPreference = "Stop"
$ServiceName = "MercaFlowServidorLocal"
$ServiceExe = Join-Path $ServiceDirectory "$ServiceName.exe"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Execute este script em um PowerShell aberto como administrador."
}

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $service) {
    Write-Host "O servico $ServiceName nao esta instalado."
} else {
    if (-not (Test-Path -LiteralPath $ServiceExe -PathType Leaf)) {
        throw "Executavel do servico nao encontrado em $ServiceExe."
    }
    if ($service.Status -ne "Stopped") {
        & $ServiceExe stop
        if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel parar o servico." }
    }
    & $ServiceExe uninstall
    if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel remover o servico." }
    Write-Host "Servico $ServiceName removido."
}

if ($RemoveServiceFiles -and (Test-Path -LiteralPath $ServiceDirectory)) {
    $resolved = (Resolve-Path -LiteralPath $ServiceDirectory).Path
    $programData = (Resolve-Path -LiteralPath $env:ProgramData).Path
    if (-not $resolved.StartsWith($programData, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Remocao recusada: a pasta precisa estar dentro de $programData."
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
    Write-Host "Arquivos do servico removidos de $resolved."
}