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
    [string]$ServiceDirectory = "$env:ProgramData\MercaFlow\ServidorLocal",
    [switch]$SkipCollectStatic,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ServiceName = "MercaFlowServidorLocal"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Manage = Join-Path $Root "manage.py"
$Template = Join-Path $Root "server_local\windows\MercaFlowServidorLocal.xml.template"

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

Set-Location $Root
& $Python $Manage check
if ($LASTEXITCODE -ne 0) { throw "manage.py check falhou." }
& $Python $Manage migrate --noinput
if ($LASTEXITCODE -ne 0) { throw "A aplicacao das migrations falhou." }
if (-not $SkipCollectStatic) {
    & $Python $Manage collectstatic --noinput
    if ($LASTEXITCODE -ne 0) { throw "collectstatic falhou." }
}

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing -and -not $Force) {
    throw "O servico $ServiceName ja existe. Use -Force para reinstalar."
}

New-Item -ItemType Directory -Path $ServiceDirectory -Force | Out-Null
$ServiceExe = Join-Path $ServiceDirectory "$ServiceName.exe"
$ServiceXml = Join-Path $ServiceDirectory "$ServiceName.xml"
$LogPath = Join-Path $ServiceDirectory "logs"
New-Item -ItemType Directory -Path $LogPath -Force | Out-Null

if ($existing) {
    if ($existing.Status -ne "Stopped") {
        & $ServiceExe stop
    }
    & $ServiceExe uninstall
}

Copy-Item -LiteralPath $WinSWPath -Destination $ServiceExe -Force

function ConvertTo-XmlText([string]$Value) {
    return [Security.SecurityElement]::Escape($Value)
}

$xml = [IO.File]::ReadAllText($Template)
$xml = $xml.Replace("__PYTHON__", (ConvertTo-XmlText $Python))
$xml = $xml.Replace("__PROJECT_ROOT__", (ConvertTo-XmlText $Root))
$xml = $xml.Replace("__BIND__", (ConvertTo-XmlText $Bind))
$xml = $xml.Replace("__PORT__", $Port.ToString())
$xml = $xml.Replace("__LOG_PATH__", (ConvertTo-XmlText $LogPath))
[IO.File]::WriteAllText($ServiceXml, $xml, [Text.UTF8Encoding]::new($false))

& $ServiceExe install
if ($LASTEXITCODE -ne 0) { throw "A instalacao do servico Windows falhou." }
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
    throw "O servico iniciou, mas o healthcheck falhou em $HealthUrl. Consulte $LogPath."
}

Write-Host "Servico $ServiceName instalado e saudavel."
Write-Host "Healthcheck: $HealthUrl"
Write-Host "Logs: $LogPath"