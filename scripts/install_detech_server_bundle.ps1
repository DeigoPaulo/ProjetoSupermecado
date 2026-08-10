param(
    [Parameter(Mandatory = $true)]
    [string]$ServerIp,
    [string]$InstallDirectory = "C:\DeTecServer\app",
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [string]$PostgresDatabase = "detech_erp",
    [string]$PostgresUser = "detech_erp",
    [securestring]$PostgresPassword,
    [string]$PostgresAdminUser = "postgres",
    [securestring]$PostgresAdminPassword,
    [switch]$OpenPostgreSqlInstaller,
    [switch]$SkipFirewall,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
function Normalize-IPv4([string]$Value) {
    $normalized = $Value.Trim().Trim('"').Trim("'")
    $address = $null
    if (-not [Net.IPAddress]::TryParse($normalized, [ref]$address) -or
        $address.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
        throw "Informe um endereco IPv4 valido para o servidor."
    }
    return $address.ToString()
}

$ServerIp = Normalize-IPv4 $ServerIp

$BundleRoot = $PSScriptRoot
$ManifestPath = Join-Path $BundleRoot "bundle.manifest.json"

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw "Abra o PowerShell como administrador." }
}

function Get-Payload([object]$Manifest, [string]$Type) {
    $item = @($Manifest.arquivos | Where-Object { $_.tipo -eq $Type }) | Select-Object -First 1
    if (-not $item) { throw "Arquivo obrigatorio ausente no manifesto: $Type" }
    $path = Join-Path $BundleRoot ($item.caminho -replace '/', '\')
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Arquivo ausente no pacote: $($item.caminho)" }
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    if ($hash -ne [string]$item.sha256) { throw "Integridade invalida para $Type." }
    return $path
}

function Test-Python312Candidate([string]$Candidate) {
    if (-not $Candidate -or -not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return $false }
    $windowsApps = Join-Path $env:LocalAppData "Microsoft\WindowsApps"
    if ($Candidate.StartsWith($windowsApps, [StringComparison]::OrdinalIgnoreCase)) { return $false }

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        & $Candidate -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Find-MachinePython312 {
    $candidates = @(
        (Join-Path $env:ProgramFiles "Python312\python.exe")
    )
    foreach ($registryPath in @(
        "HKLM:\SOFTWARE\Python\PythonCore\3.12\InstallPath",
        "HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore\3.12\InstallPath"
    )) {
        $registered = Get-ItemProperty -LiteralPath $registryPath -ErrorAction SilentlyContinue
        if ($registered.ExecutablePath) { $candidates += [string]$registered.ExecutablePath }
    }
    foreach ($candidate in @($candidates | Where-Object { $_ } | Select-Object -Unique)) {
        if (Test-Python312Candidate $candidate) { return $candidate }
    }
    return $null
}

Assert-Administrator
if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) { throw "bundle.manifest.json nao encontrado." }
$manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.contrato -ne "detech_server_offline_bundle_v1") { throw "Contrato do pacote invalido." }
$serverZip = Get-Payload $manifest "servidor"
$pythonInstaller = Get-Payload $manifest "python"
$postgresInstaller = Get-Payload $manifest "postgresql"
$winSW = Get-Payload $manifest "winsw"
$wheelhouseArchive = Get-Payload $manifest "python-wheelhouse"

$python = Find-MachinePython312
if (-not $python) {
    $pythonInstall = Start-Process -FilePath $pythonInstaller -ArgumentList @(
        "/quiet",
        "InstallAllUsers=1",
        "TargetDir=`"$env:ProgramFiles\Python312`"",
        "PrependPath=1",
        "Include_test=0",
        "Include_launcher=1",
        "InstallLauncherAllUsers=1"
    ) -Wait -PassThru
    if ($pythonInstall.ExitCode -notin @(0, 3010)) {
        throw "O instalador do Python terminou com o codigo $($pythonInstall.ExitCode)."
    }
    $python = Find-MachinePython312
    if (-not $python) {
        throw "A instalacao do Python 3.12 para todos os usuarios nao foi concluida."
    }
}

function Find-PostgreSqlClient {
    $commands = @(Get-Command psql.exe -All -CommandType Application -ErrorAction SilentlyContinue)
    foreach ($command in $commands) {
        if ($command.Source -and (Test-Path -LiteralPath $command.Source -PathType Leaf)) {
            return $command.Source
        }
    }

    $postgresRoot = Join-Path $env:ProgramFiles "PostgreSQL"
    if (Test-Path -LiteralPath $postgresRoot -PathType Container) {
        $versions = @(Get-ChildItem -LiteralPath $postgresRoot -Directory | Sort-Object Name -Descending)
        foreach ($version in $versions) {
            $candidate = Join-Path $version.FullName "bin\psql.exe"
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
        }
    }
    return $null
}

$psqlPath = Find-PostgreSqlClient
if (-not $psqlPath) {
    if (-not $OpenPostgreSqlInstaller) {
        throw "PostgreSQL ainda nao esta instalado. Execute novamente com -OpenPostgreSqlInstaller, conclua o instalador oficial e repita o comando."
    }
    Start-Process -FilePath $postgresInstaller -Wait
    throw "Conclua a instalacao do PostgreSQL e execute novamente este mesmo instalador."
}
$psqlDirectory = Split-Path -Parent $psqlPath
if (($env:Path -split ';') -notcontains $psqlDirectory) {
    $env:Path = "$psqlDirectory;$env:Path"
}

$wheelhouse = Join-Path $BundleRoot "payload\wheelhouse"
if (Test-Path -LiteralPath $wheelhouse) { Remove-Item -LiteralPath $wheelhouse -Recurse -Force }
Expand-Archive -LiteralPath $wheelhouseArchive -DestinationPath $wheelhouse -Force
$env:PIP_NO_INDEX = "1"
$env:PIP_FIND_LINKS = $wheelhouse
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"

if (Test-Path -LiteralPath $InstallDirectory -PathType Leaf) {
    throw "O destino da instalacao existe como arquivo, nao como pasta: $InstallDirectory"
}
if (Test-Path -LiteralPath $InstallDirectory -PathType Container) {
    Write-Host "Instalacao existente ou parcial encontrada. Atualizando os arquivos sem remover configuracoes e dados."
}
New-Item -ItemType Directory -Path $InstallDirectory -Force | Out-Null
# Expand-Archive com -Force sobrescreve o codigo do pacote, mas preserva .env, media,
# backups e demais arquivos locais que nao existem no ZIP.
Expand-Archive -LiteralPath $serverZip -DestinationPath $InstallDirectory -Force
$childInstaller = Join-Path $InstallDirectory "scripts\install_detech_server.ps1"
if (-not (Test-Path -LiteralPath $childInstaller -PathType Leaf)) { throw "Instalador interno ausente no pacote do servidor." }
$winswHash = (Get-FileHash -LiteralPath $winSW -Algorithm SHA256).Hash
$params = @{
    ServerIp = $ServerIp
    WinSWPath = $winSW
    WinSWSha256 = $winswHash
    PythonPath = $python
    Port = $Port
    DatabaseEngine = "PostgreSQL"
    PostgresDatabase = $PostgresDatabase
    PostgresUser = $PostgresUser
    PostgresAdminUser = $PostgresAdminUser
    SkipFirewall = $SkipFirewall
    Force = $Force
}
if ($PostgresPassword) { $params.PostgresPassword = $PostgresPassword }
if ($PostgresAdminPassword) { $params.PostgresAdminPassword = $PostgresAdminPassword }
& $childInstaller @params
