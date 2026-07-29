param(
    [Parameter(Mandatory = $true)]
    [string]$WinSWPath,
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[A-Fa-f0-9]{64}$")]
    [string]$ExpectedSha256,
    [string]$Bind = "0.0.0.0",
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [string]$HealthHost = "127.0.0.1",
    [string]$ServiceDirectory = "$env:ProgramData\DeigoVarejo\ServidorLocal",
    [string]$DataDirectory = "$env:ProgramData\DeigoVarejo\Dados",
    [ValidateSet("PostgreSQL", "SQLite")]
    [string]$DatabaseEngine = "PostgreSQL",
    [string]$ServiceIdentity = "NT SERVICE\DeigoVarejoServidorLocal",
    [switch]$ImportExistingSqlite,
    [switch]$SkipCollectStatic,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ServiceName = "DeigoVarejoServidorLocal"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Manage = Join-Path $Root "manage.py"
$Template = Join-Path $Root "server_local\windows\DeigoVarejoServidorLocal.xml.template"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Execute este script em um PowerShell aberto como administrador."
}

foreach ($required in @($WinSWPath, $Python, $Manage, $Template)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Arquivo obrigatorio nao encontrado: $required"
    }
}

$actualHash = (Get-FileHash -LiteralPath $WinSWPath -Algorithm SHA256).Hash
if ($actualHash -ne $ExpectedSha256.ToUpperInvariant()) {
    throw "SHA-256 do WinSW divergente. Esperado $ExpectedSha256; recebido $actualHash."
}

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
$ServiceExe = Join-Path $ServiceDirectory "$ServiceName.exe"
if ($existing -and -not $Force) {
    throw "O servico $ServiceName ja existe. Use -Force para reinstalar."
}
if ($existing) {
    if ($existing.Status -ne "Stopped") {
        & $ServiceExe stop
    }
    & $ServiceExe uninstall
}

$MediaDirectory = Join-Path $DataDirectory "media"
$StaticDirectory = Join-Path $DataDirectory "staticfiles"
$DjangoLogDirectory = Join-Path $DataDirectory "logs"
$SqlitePath = Join-Path $DataDirectory "db.sqlite3"
$WrapperLogDirectory = Join-Path $ServiceDirectory "logs"
foreach ($directory in @($ServiceDirectory, $DataDirectory, $MediaDirectory, $StaticDirectory, $DjangoLogDirectory, $WrapperLogDirectory)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

$ExistingSqlite = Join-Path $Root "db.sqlite3"
if ($ImportExistingSqlite -and -not (Test-Path -LiteralPath $SqlitePath) -and (Test-Path -LiteralPath $ExistingSqlite -PathType Leaf)) {
    Copy-Item -LiteralPath $ExistingSqlite -Destination $SqlitePath
}

$env:SQLITE_PATH = $SqlitePath
$env:MEDIA_ROOT = $MediaDirectory
$env:STATIC_ROOT = $StaticDirectory
$env:LOG_DIR = $DjangoLogDirectory

Set-Location $Root
$RuntimeEngineCode = "import json, os, django; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); django.setup(); from django.conf import settings; print(json.dumps({'engine': settings.DATABASES['default']['ENGINE'], 'pg_dump_path': os.getenv('POSTGRES_PG_DUMP_PATH', ''), 'pg_restore_path': os.getenv('POSTGRES_PG_RESTORE_PATH', '')}))"
$RuntimeInfoJson = (& $Python -c $RuntimeEngineCode | Select-Object -Last 1)
$RuntimeInfo = $RuntimeInfoJson | ConvertFrom-Json
$ExpectedEngine = if ($DatabaseEngine -eq "PostgreSQL") { "django.db.backends.postgresql" } else { "django.db.backends.sqlite3" }
if ([string]$RuntimeInfo.engine -ne $ExpectedEngine) {
    throw "Banco configurado no .env diverge da instalacao. Esperado $ExpectedEngine; recebido $($RuntimeInfo.engine)."
}
if ($DatabaseEngine -eq "PostgreSQL") {
    foreach ($tool in @(
        @{ Nome = "pg_dump"; Variavel = "POSTGRES_PG_DUMP_PATH" },
        @{ Nome = "pg_restore"; Variavel = "POSTGRES_PG_RESTORE_PATH" }
    )) {
        $command = [Environment]::GetEnvironmentVariable($tool.Variavel, "Process")
        if (-not $command) {
            $command = if ($tool.Nome -eq "pg_dump") { [string]$RuntimeInfo.pg_dump_path } else { [string]$RuntimeInfo.pg_restore_path }
        }
        if (-not $command) { $command = $tool.Nome }
        $resolved = Get-Command $command -ErrorAction SilentlyContinue
        if (-not $resolved) { throw "$($tool.Nome) nao encontrado. Instale PostgreSQL Client ou configure $($tool.Variavel)." }
        & $resolved.Source --version
        if ($LASTEXITCODE -ne 0) { throw "$($tool.Nome) foi encontrado, mas nao respondeu corretamente." }
    }
}
& $Python $Manage check
if ($LASTEXITCODE -ne 0) { throw "manage.py check falhou." }
& $Python $Manage migrate --noinput
if ($LASTEXITCODE -ne 0) { throw "A aplicacao das migrations falhou." }
if (-not $SkipCollectStatic) {
    & $Python $Manage collectstatic --noinput
    if ($LASTEXITCODE -ne 0) { throw "collectstatic falhou." }
}

Copy-Item -LiteralPath $WinSWPath -Destination $ServiceExe -Force
$ServiceXml = Join-Path $ServiceDirectory "$ServiceName.xml"

function ConvertTo-XmlText([string]$Value) {
    return [Security.SecurityElement]::Escape($Value)
}

$xml = [IO.File]::ReadAllText($Template)
$replacements = [ordered]@{
    "__PYTHON__" = $Python
    "__PROJECT_ROOT__" = $Root
    "__BIND__" = $Bind
    "__PORT__" = $Port.ToString()
    "__WRAPPER_LOG_PATH__" = $WrapperLogDirectory
    "__SQLITE_PATH__" = $SqlitePath
    "__MEDIA_ROOT__" = $MediaDirectory
    "__STATIC_ROOT__" = $StaticDirectory
    "__DJANGO_LOG_DIR__" = $DjangoLogDirectory
}
foreach ($item in $replacements.GetEnumerator()) {
    $xml = $xml.Replace($item.Key, (ConvertTo-XmlText ([string]$item.Value)))
}
[IO.File]::WriteAllText($ServiceXml, $xml, [Text.UTF8Encoding]::new($false))

& $ServiceExe install
if ($LASTEXITCODE -ne 0) { throw "A instalacao do servico Windows falhou." }

$sc = Join-Path $env:SystemRoot "System32\sc.exe"
& $sc config $ServiceName "obj=" $ServiceIdentity "password=" ""
if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel configurar a identidade dedicada $ServiceIdentity." }

& icacls.exe $Root /grant:r "${ServiceIdentity}:(OI)(CI)RX" /T /C | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel conceder leitura do ERP para $ServiceIdentity." }
foreach ($writable in @($ServiceDirectory, $DataDirectory)) {
    & icacls.exe $writable /grant:r "${ServiceIdentity}:(OI)(CI)M" /T /C | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel conceder escrita em $writable para $ServiceIdentity." }
}

& $ServiceExe start
if ($LASTEXITCODE -ne 0) { throw "O servico foi instalado, mas nao iniciou." }

$HealthUrl = "http://$HealthHost`:$Port/login/"
$healthy = $false
for ($attempt = 1; $attempt -le 15; $attempt++) {
    try {
        $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 4
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
            $healthy = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $healthy) {
    throw "O servico iniciou, mas o healthcheck falhou em $HealthUrl. Consulte $WrapperLogDirectory."
}

Write-Host "Servico $ServiceName instalado e saudavel."
Write-Host "Identidade: $ServiceIdentity"
Write-Host "Dados: $DataDirectory"
Write-Host "Banco: $DatabaseEngine"
Write-Host "Healthcheck: $HealthUrl"
Write-Host "Logs do wrapper: $WrapperLogDirectory"