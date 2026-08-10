param(
    [Parameter(Mandatory = $true)]
    [string]$ServerIp,

    [Parameter(Mandatory = $true)]
    [string]$WinSWPath,

    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[A-Fa-f0-9]{64}$")]
    [string]$WinSWSha256,

    [string]$PythonPath = "python",
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [ValidateSet("PostgreSQL", "SQLite")]
    [string]$DatabaseEngine = "PostgreSQL",
    [string]$PostgresHost = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$PostgresPort = 5432,
    [string]$PostgresDatabase = "detech_erp",
    [string]$PostgresUser = "detech_erp",
    [securestring]$PostgresPassword,
    [string]$PostgresAdminUser = "postgres",
    [securestring]$PostgresAdminPassword,
    [switch]$SkipFirewall,
    [switch]$Preflight,
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

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$EnvFile = Join-Path $Root ".env"
$EnvExample = Join-Path $Root ".env.example"

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Abra o PowerShell como administrador e execute novamente."
    }
}

function Assert-SafeName([string]$Value, [string]$Label) {
    if ($Value -notmatch "^[a-zA-Z_][a-zA-Z0-9_]{0,62}$") {
        throw "$Label deve conter apenas letras, numeros e sublinhado, iniciando por letra ou sublinhado."
    }
}

function Get-PlainSecret([securestring]$Secret) {
    $credential = [PSCredential]::new("unused", $Secret)
    return $credential.GetNetworkCredential().Password
}

function Set-EnvValue([string]$Name, [string]$Value) {
    $escaped = [Regex]::Escape($Name)
    $line = "$Name=$Value"
    $content = [IO.File]::ReadAllText($EnvFile)
    if ($content -match "(?m)^$escaped=") {
        $content = [Regex]::Replace($content, "(?m)^$escaped=.*$", [Text.RegularExpressions.MatchEvaluator]{ param($match) $line })
    } else {
        if (-not $content.EndsWith("`n")) { $content += "`r`n" }
        $content += "$line`r`n"
    }
    [IO.File]::WriteAllText($EnvFile, $content, [Text.UTF8Encoding]::new($false))
}

function Get-EnvValue([string]$Name) {
    $escaped = [Regex]::Escape($Name)
    $match = [Regex]::Match([IO.File]::ReadAllText($EnvFile), "(?m)^$escaped=(.*)$")
    if ($match.Success) { return $match.Groups[1].Value.Trim() }
    return ""
}

function Test-Python312([string]$Executable) {
    $command = Get-Command $Executable -ErrorAction SilentlyContinue
    if (-not $command -and -not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $false }
    & $Executable -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" 2>$null
    return $LASTEXITCODE -eq 0
}

function New-SecretKey {
    $bytes = New-Object byte[] 48
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_").TrimEnd("=")
}

function Initialize-PostgreSql {
    Assert-SafeName $PostgresDatabase "PostgresDatabase"
    Assert-SafeName $PostgresUser "PostgresUser"
    $psql = Get-Command "psql.exe" -ErrorAction SilentlyContinue
    if (-not $psql) { $psql = Get-Command "psql" -ErrorAction SilentlyContinue }
    if (-not $psql) {
        throw "PostgreSQL/psql nao encontrado. Instale o PostgreSQL 16 x64 antes de continuar."
    }
    if (-not $PostgresPassword) { $script:PostgresPassword = Read-Host "Senha do usuario do ERP no PostgreSQL" -AsSecureString }
    if (-not $PostgresAdminPassword) { $script:PostgresAdminPassword = Read-Host "Senha do usuario administrador do PostgreSQL" -AsSecureString }
    $adminPassword = Get-PlainSecret $PostgresAdminPassword
    $appPassword = Get-PlainSecret $PostgresPassword
    $env:PGPASSWORD = $adminPassword
    try {
        $roleExists = (& $psql.Source -h $PostgresHost -p $PostgresPort -U $PostgresAdminUser -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname = '$PostgresUser'" | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel conectar no PostgreSQL com o usuario administrador informado." }
        $safePassword = $appPassword.Replace("'", "''")
        if ($roleExists -eq "1") {
            & $psql.Source -h $PostgresHost -p $PostgresPort -U $PostgresAdminUser -d postgres -v ON_ERROR_STOP=1 -c "ALTER ROLE $PostgresUser WITH LOGIN PASSWORD '$safePassword';"
        } else {
            & $psql.Source -h $PostgresHost -p $PostgresPort -U $PostgresAdminUser -d postgres -v ON_ERROR_STOP=1 -c "CREATE ROLE $PostgresUser LOGIN PASSWORD '$safePassword';"
        }
        if ($LASTEXITCODE -ne 0) { throw "Falha ao preparar o usuario do PostgreSQL." }
        $databaseExists = (& $psql.Source -h $PostgresHost -p $PostgresPort -U $PostgresAdminUser -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$PostgresDatabase'" | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { throw "Falha ao verificar o banco do ERP." }
        if ($databaseExists -ne "1") {
            & $psql.Source -h $PostgresHost -p $PostgresPort -U $PostgresAdminUser -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $PostgresDatabase OWNER $PostgresUser ENCODING 'UTF8';"
            if ($LASTEXITCODE -ne 0) { throw "Falha ao criar o banco do ERP." }
        }
        $databaseReady = (& $psql.Source -h $PostgresHost -p $PostgresPort -U $PostgresAdminUser -d $PostgresDatabase -tAc "SELECT 1" | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or $databaseReady -ne "1") {
            throw "O banco do ERP foi preparado, mas a conexao de validacao falhou."
        }
    } finally {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    }
}

if (-not $Preflight) { Assert-Administrator }
if (-not (Test-Python312 $PythonPath)) {
    throw "Python 3.12 ou superior nao encontrado em '$PythonPath'. Instale-o antes de executar este instalador."
}
if (-not (Test-Path -LiteralPath $WinSWPath -PathType Leaf)) { throw "WinSW nao encontrado: $WinSWPath" }
$actualWinSWHash = (Get-FileHash -LiteralPath $WinSWPath -Algorithm SHA256).Hash
if ($actualWinSWHash -ne $WinSWSha256.ToUpperInvariant()) { throw "SHA-256 do WinSW divergente." }
if ($Preflight) {
    if ($DatabaseEngine -eq "PostgreSQL") {
        $psql = Get-Command "psql.exe" -ErrorAction SilentlyContinue
        if (-not $psql) { $psql = Get-Command "psql" -ErrorAction SilentlyContinue }
        if (-not $psql) { throw "PostgreSQL/psql nao encontrado. Instale o PostgreSQL 16 x64 antes da instalacao." }
    }
    Write-Host "Pre-homologacao aprovada para http://$ServerIp`:$Port/login/"
    Write-Host "Nenhum arquivo, banco, servico ou regra de firewall foi alterado."
    exit 0
}
if (-not (Test-Path -LiteralPath $EnvFile)) { Copy-Item -LiteralPath $EnvExample -Destination $EnvFile }

if ($DatabaseEngine -eq "PostgreSQL") {
    Initialize-PostgreSql
    Set-EnvValue "POSTGRES_DB" $PostgresDatabase
    Set-EnvValue "POSTGRES_USER" $PostgresUser
    Set-EnvValue "POSTGRES_PASSWORD" (Get-PlainSecret $PostgresPassword)
    Set-EnvValue "POSTGRES_HOST" $PostgresHost
    Set-EnvValue "POSTGRES_PORT" $PostgresPort
}
Set-EnvValue "DJANGO_ENV" "production"
Set-EnvValue "DEBUG" "false"
if (-not (Get-EnvValue "SECRET_KEY")) { Set-EnvValue "SECRET_KEY" (New-SecretKey) }
Set-EnvValue "ALLOWED_HOSTS" "127.0.0.1,localhost,$ServerIp"
Set-EnvValue "CSRF_TRUSTED_ORIGINS" "http://$ServerIp`:$Port"

Push-Location $Root
try {
    & (Join-Path $Root "scripts\setup_local.ps1") -Python $PythonPath
    & (Join-Path $Root "scripts\install_local_server_service.ps1") -WinSWPath $WinSWPath -ExpectedSha256 $WinSWSha256 -Bind "0.0.0.0" -Port $Port -DatabaseEngine $DatabaseEngine -Force:$Force
    if (-not $SkipFirewall) {
        $ruleName = "DeTec Server - rede privada - porta $Port"
        Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Private -RemoteAddress LocalSubnet | Out-Null
    }
    & (Join-Path $Root "scripts\test_local_server_service.ps1") -HealthUrl "http://127.0.0.1`:$Port/login/"
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "DeTec Server instalado com sucesso."
Write-Host "Acesse nesta maquina: http://127.0.0.1:$Port/login/"
Write-Host "Acesse na rede interna: http://$ServerIp`:$Port/login/"
Write-Host "O PostgreSQL permanece restrito ao servidor; nao abra a porta 5432 na rede."
