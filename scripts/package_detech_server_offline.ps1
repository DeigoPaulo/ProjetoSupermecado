param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")]
    [string]$Version,
    [Parameter(Mandatory = $true)]
    [string]$ServerPackagePath,
    [Parameter(Mandatory = $true)]
    [string]$PythonRuntimePath,
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[A-Fa-f0-9]{64}$")]
    [string]$PythonRuntimeSha256,
    [Parameter(Mandatory = $true)]
    [string]$PostgreSqlInstallerPath,
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[A-Fa-f0-9]{64}$")]
    [string]$PostgreSqlInstallerSha256,
    [Parameter(Mandatory = $true)]
    [string]$WinSWPath,
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[A-Fa-f0-9]{64}$")]
    [string]$WinSWSha256,
    [string]$InstallerLauncherPath = "server_installer\dist\Instalar DeTec Server.exe",
    [string]$WheelhouseDirectory = "dist\offline_sources\wheelhouse",
    [string]$PdvDesktopPath = "artifacts\DeTecPDV.exe",
    [string]$PdvDesktopManifestPath = "artifacts\DeTecPDV.exe.version.json",
    [string]$AdminDesktopPath = "artifacts\DeTecAdmin.exe",
    [string]$AdminDesktopManifestPath = "artifacts\DeTecAdmin.exe.version.json",
    [string]$OutputDirectory = "dist\detech_server_offline",
    [string]$PythonPath = ".venv\Scripts\python.exe",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Resolve-RequiredFile([string]$Path, [string]$Label) {
    $candidate = if ([IO.Path]::IsPathRooted($Path)) { $Path } else { Join-Path $Root $Path }
    $resolved = Resolve-Path -LiteralPath $candidate -ErrorAction SilentlyContinue
    if (-not $resolved -or -not (Test-Path -LiteralPath $resolved.Path -PathType Leaf)) {
        throw "$Label nao encontrado: $Path"
    }
    return $resolved.Path
}

function Assert-DesktopArtifact([string]$ArtifactPath, [string]$ManifestPath, [string]$Label) {
    $metadata = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $declaredHash = ([string]$metadata.sha256).Trim().ToUpperInvariant()
    if ($declaredHash -notmatch '^[A-F0-9]{64}$') { throw "Manifesto sem SHA-256 valido para $Label." }
    Assert-Hash $ArtifactPath $declaredHash $Label | Out-Null
    if (-not ([string]$metadata.version).Trim()) { throw "Manifesto sem versao para $Label." }
}

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    try {
        $sha = [Security.Cryptography.SHA256]::Create()
        try {
            return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace("-", "")
        } finally {
            $sha.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

function Assert-Hash([string]$Path, [string]$Expected, [string]$Label) {
    $actual = Get-Sha256 $Path
    if ($actual -ne $Expected.ToUpperInvariant()) { throw "SHA-256 invalido para $Label." }
    return $actual
}

$validationPython = Resolve-RequiredFile $PythonPath "Python de validacao"
$serverPackage = Resolve-RequiredFile $ServerPackagePath "Pacote do servidor"
$pythonRuntime = Resolve-RequiredFile $PythonRuntimePath "Runtime Python"
$postgresInstaller = Resolve-RequiredFile $PostgreSqlInstallerPath "Instalador PostgreSQL"
$winsw = Resolve-RequiredFile $WinSWPath "WinSW"
$pdvDesktop = Resolve-RequiredFile $PdvDesktopPath "App DeTec PDV"
$pdvDesktopManifest = Resolve-RequiredFile $PdvDesktopManifestPath "Manifesto do DeTec PDV"
$adminDesktop = Resolve-RequiredFile $AdminDesktopPath "App DeTec Admin"
$adminDesktopManifest = Resolve-RequiredFile $AdminDesktopManifestPath "Manifesto do DeTec Admin"
$launcherPath = if ([IO.Path]::IsPathRooted($InstallerLauncherPath)) { $InstallerLauncherPath } else { Join-Path $Root $InstallerLauncherPath }
$launcher = Resolve-RequiredFile $launcherPath "Instalador executavel"
$wheelhousePath = if ([IO.Path]::IsPathRooted($WheelhouseDirectory)) { $WheelhouseDirectory } else { Join-Path $Root $WheelhouseDirectory }
if (-not (Test-Path -LiteralPath $wheelhousePath -PathType Container)) { throw "Wheelhouse Python nao encontrado: $wheelhousePath" }
$wheels = @(Get-ChildItem -LiteralPath $wheelhousePath -Filter "*.whl" -File)
if (-not $wheels) { throw "Nenhum pacote .whl encontrado em $wheelhousePath" }
Assert-Hash $pythonRuntime $PythonRuntimeSha256 "Runtime Python" | Out-Null
Assert-Hash $postgresInstaller $PostgreSqlInstallerSha256 "PostgreSQL" | Out-Null
Assert-Hash $winsw $WinSWSha256 "WinSW" | Out-Null
Assert-DesktopArtifact $pdvDesktop $pdvDesktopManifest "DeTec PDV"
Assert-DesktopArtifact $adminDesktop $adminDesktopManifest "DeTec Admin"

$output = if ([IO.Path]::IsPathRooted($OutputDirectory)) { $OutputDirectory } else { Join-Path $Root $OutputDirectory }
New-Item -ItemType Directory -Path $output -Force | Out-Null
$archive = Join-Path $output "DeTecServer-$Version-windows-offline.zip"
if ((Test-Path -LiteralPath $archive) -and -not $Force) { throw "Pacote ja existe: $archive. Use -Force para substituir." }

$stage = Join-Path $env:TEMP "detech-server-package-$([Guid]::NewGuid().ToString('N'))"
$payload = Join-Path $stage "payload"
$archiveTemp = $null
$checksumTemp = $null
New-Item -ItemType Directory -Path $payload -Force | Out-Null
try {
    $wheelhouseArchive = Join-Path $stage "wheelhouse.zip"
    Compress-Archive -Path (Join-Path $wheelhousePath "*") -DestinationPath $wheelhouseArchive -CompressionLevel Optimal -Force
    $files = @(
        @{ origem = $wheelhouseArchive; destino = "wheelhouse.zip"; tipo = "python-wheelhouse" },
        @{ origem = $serverPackage; destino = "server.zip"; tipo = "servidor" },
        @{ origem = $pythonRuntime; destino = "python-runtime.zip"; tipo = "python-runtime" },
        @{ origem = $postgresInstaller; destino = "postgresql-installer$([IO.Path]::GetExtension($postgresInstaller))"; tipo = "postgresql" },
        @{ origem = $winsw; destino = "WinSW$([IO.Path]::GetExtension($winsw))"; tipo = "winsw" },
        @{ origem = $pdvDesktop; destino = "DeTecPDV.exe"; tipo = "pdv-desktop" },
        @{ origem = $pdvDesktopManifest; destino = "DeTecPDV.exe.version.json"; tipo = "pdv-desktop-manifest" },
        @{ origem = $adminDesktop; destino = "DeTecAdmin.exe"; tipo = "admin-desktop" },
        @{ origem = $adminDesktopManifest; destino = "DeTecAdmin.exe.version.json"; tipo = "admin-desktop-manifest" },
        @{ origem = $launcher; destino = "..\Instalar DeTec Server.exe"; tipo = "launcher" }
    )
    $manifestFiles = @()
    foreach ($file in $files) {
        $destination = Join-Path $payload $file.destino
        Copy-Item -LiteralPath $file.origem -Destination $destination
        $manifestFiles += [ordered]@{
            tipo = $file.tipo
            caminho = if ($file.tipo -eq "launcher") { "Instalar DeTec Server.exe" } else { "payload/$($file.destino)" }
            nome_origem = [IO.Path]::GetFileName($file.origem)
            tamanho_bytes = (Get-Item -LiteralPath $destination).Length
            sha256 = Get-Sha256 $destination
        }
    }
    Remove-Item -LiteralPath $wheelhouseArchive -Force
    Copy-Item -LiteralPath (Join-Path $Root "scripts\install_detech_server_bundle.ps1") -Destination (Join-Path $stage "Install-DeTecServer.ps1")
    $manifest = [ordered]@{
        contrato = "detech_server_offline_bundle_v1"
        versao = $Version
        gerado_em = (Get-Date).ToUniversalTime().ToString("o")
        instalador_executavel = "Instalar DeTec Server.exe"
        instalador = "Install-DeTecServer.ps1"
        arquivos = $manifestFiles
        observacao = "Pacote sem banco, arquivos de clientes, .env ou certificados fiscais. Inclui os apps desktop validados para publicacao local."
    }
    [IO.File]::WriteAllText((Join-Path $stage "bundle.manifest.json"), ($manifest | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
    $archiveTemp = "$archive.tmp.zip"
    Remove-Item -LiteralPath $archiveTemp -Force -ErrorAction SilentlyContinue
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $archiveTemp -CompressionLevel Optimal
    $validationCode = "import json,sys; from pathlib import Path; from apps.configuracoes.offline_bundle import validar_pacote_servidor_offline; r=validar_pacote_servidor_offline(Path(sys.argv[1]), sys.argv[2]); print(json.dumps({k:v for k,v in r.items() if k != 'caminho'}, ensure_ascii=False, default=str)); sys.exit(0 if r['publicavel'] else 2)"
    $validationJson = & $validationPython -c $validationCode $archiveTemp $Version
    if ($LASTEXITCODE -ne 0) {
        Remove-Item -LiteralPath $archiveTemp -Force -ErrorAction SilentlyContinue
        throw "Pacote offline recusado pelo contrato de validacao: $validationJson"
    }
    $validation = $validationJson | ConvertFrom-Json
    if ($validation.contrato -ne "detech_server_offline_package_validation_v2" -or $validation.publicavel -ne $true) {
        Remove-Item -LiteralPath $archiveTemp -Force -ErrorAction SilentlyContinue
        throw "Resultado inesperado da validacao do pacote offline."
    }
    $hash = Get-Sha256 $archiveTemp
    $checksum = "$archive.sha256"
    $checksumTemp = "$checksum.tmp"
    [IO.File]::WriteAllText($checksumTemp, "$hash  $([IO.Path]::GetFileName($archive))`n", [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $archiveTemp -Destination $archive -Force
    Move-Item -LiteralPath $checksumTemp -Destination $checksum -Force
    Write-Host "Pacote offline validado e gerado: $archive"
    Write-Host "Contrato: $($validation.contrato)"
    Write-Host "SHA-256: $hash"
} finally {
    if ($archiveTemp) { Remove-Item -LiteralPath $archiveTemp -Force -ErrorAction SilentlyContinue }
    if ($checksumTemp) { Remove-Item -LiteralPath $checksumTemp -Force -ErrorAction SilentlyContinue }
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
