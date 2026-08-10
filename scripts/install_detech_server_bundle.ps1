param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^(?:\d{1,3}\.){3}\d{1,3}$")]
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

function Find-Python312 {
    foreach ($candidate in @("$env:ProgramFiles\Python312\python.exe", "$env:LocalAppData\Programs\Python\Python312\python.exe")) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        & $python.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { return $python.Source }
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

$python = Find-Python312
if (-not $python) {
    Start-Process -FilePath $pythonInstaller -ArgumentList @("/quiet", "InstallAllUsers=1", "PrependPath=1", "Include_test=0") -Wait
    $python = Find-Python312
    if (-not $python) { throw "A instalacao automatica do Python nao foi concluida." }
}

$psql = Get-Command psql.exe -ErrorAction SilentlyContinue
if (-not $psql) { $psql = Get-Command psql -ErrorAction SilentlyContinue }
if (-not $psql) {
    if (-not $OpenPostgreSqlInstaller) {
        throw "PostgreSQL ainda nao esta instalado. Execute novamente com -OpenPostgreSqlInstaller, conclua o instalador oficial e repita o comando."
    }
    Start-Process -FilePath $postgresInstaller -Wait
    throw "Conclua a instalacao do PostgreSQL e execute novamente este mesmo comando."
}

if (Test-Path -LiteralPath $InstallDirectory) {
    if (-not $Force) { throw "A pasta de destino ja existe: $InstallDirectory. Use -Force somente em reinstalacao controlada." }
    Remove-Item -LiteralPath $InstallDirectory -Recurse -Force
}
New-Item -ItemType Directory -Path $InstallDirectory -Force | Out-Null
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
