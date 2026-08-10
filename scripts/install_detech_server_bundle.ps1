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

function Get-PayloadItem([object]$Manifest, [string]$Type) {
    $item = @($Manifest.arquivos | Where-Object { $_.tipo -eq $Type }) | Select-Object -First 1
    if (-not $item) { throw "Arquivo obrigatorio ausente no manifesto: $Type" }
    return $item
}

function Test-Python312Runtime([string]$Candidate) {
    if (-not $Candidate -or -not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return $false }
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        & $Candidate -c "from pathlib import Path; import ensurepip, ssl, sys, venv; raise SystemExit(0 if sys.version_info[:2] == (3, 12) and (Path(sys.base_prefix) / 'Lib' / 'os.py').is_file() else 1)" 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

Assert-Administrator
if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) { throw "bundle.manifest.json nao encontrado." }
$manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.contrato -ne "detech_server_offline_bundle_v1") { throw "Contrato do pacote invalido." }
$serverZip = Get-Payload $manifest "servidor"
$pythonRuntimeItem = Get-PayloadItem $manifest "python-runtime"
$pythonRuntime = Get-Payload $manifest "python-runtime"
$postgresInstaller = Get-Payload $manifest "postgresql"
$winSW = Get-Payload $manifest "winsw"
$wheelhouseArchive = Get-Payload $manifest "python-wheelhouse"

$managedPythonRoot = Join-Path $env:ProgramData "DeTecServer\Python312"
$expectedManagedRoot = Join-Path $env:ProgramData "DeTecServer\Python312"
if (-not $managedPythonRoot.Equals($expectedManagedRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Destino do runtime Python fora da area gerenciada."
}
$existingService = Get-Service -Name "DeigoVarejoServidorLocal" -ErrorAction SilentlyContinue
if ($existingService -and $existingService.Status -ne "Stopped") {
    Stop-Service -Name "DeigoVarejoServidorLocal" -Force
    (Get-Service -Name "DeigoVarejoServidorLocal").WaitForStatus("Stopped", [TimeSpan]::FromSeconds(30))
}
$python = Join-Path $managedPythonRoot "python.exe"
$runtimeMarker = Join-Path $managedPythonRoot ".detech-runtime.sha256"
$expectedRuntimeHash = ([string]$pythonRuntimeItem.sha256).ToUpperInvariant()
$installedRuntimeHash = if (Test-Path -LiteralPath $runtimeMarker -PathType Leaf) {
    (Get-Content -LiteralPath $runtimeMarker -Raw).Trim().ToUpperInvariant()
} else {
    ""
}
$runtimeValid = Test-Python312Runtime $python
$runtimeCurrent = $runtimeValid -and (-not $installedRuntimeHash -or $installedRuntimeHash -eq $expectedRuntimeHash)
if ($runtimeCurrent) {
    Write-Host "Runtime Python existente e compativel. Reutilizando sem reinstalar."
    if (-not $installedRuntimeHash) {
        Set-Content -LiteralPath $runtimeMarker -Value $expectedRuntimeHash -Encoding ASCII
    }
} else {
    if (Test-Path -LiteralPath $managedPythonRoot) {
        Remove-Item -LiteralPath $managedPythonRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $managedPythonRoot -Force | Out-Null
    Expand-Archive -LiteralPath $pythonRuntime -DestinationPath $managedPythonRoot -Force
    if (-not (Test-Python312Runtime $python)) {
        throw "O runtime Python incluido no pacote nao passou na validacao."
    }
    Set-Content -LiteralPath $runtimeMarker -Value $expectedRuntimeHash -Encoding ASCII
    Write-Host "Runtime Python instalado ou atualizado pelo pacote."
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
