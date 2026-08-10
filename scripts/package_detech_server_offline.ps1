param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")]
    [string]$Version,
    [Parameter(Mandatory = $true)]
    [string]$ServerPackagePath,
    [Parameter(Mandatory = $true)]
    [string]$PythonInstallerPath,
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[A-Fa-f0-9]{64}$")]
    [string]$PythonInstallerSha256,
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
    [string]$OutputDirectory = "dist\detech_server_offline",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Resolve-RequiredFile([string]$Path, [string]$Label) {
    $resolved = Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue
    if (-not $resolved -or -not (Test-Path -LiteralPath $resolved.Path -PathType Leaf)) {
        throw "$Label nao encontrado: $Path"
    }
    return $resolved.Path
}

function Assert-Hash([string]$Path, [string]$Expected, [string]$Label) {
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actual -ne $Expected.ToUpperInvariant()) { throw "SHA-256 invalido para $Label." }
    return $actual
}

$serverPackage = Resolve-RequiredFile $ServerPackagePath "Pacote do servidor"
$pythonInstaller = Resolve-RequiredFile $PythonInstallerPath "Instalador Python"
$postgresInstaller = Resolve-RequiredFile $PostgreSqlInstallerPath "Instalador PostgreSQL"
$winsw = Resolve-RequiredFile $WinSWPath "WinSW"
$launcherPath = if ([IO.Path]::IsPathRooted($InstallerLauncherPath)) { $InstallerLauncherPath } else { Join-Path $Root $InstallerLauncherPath }
$launcher = Resolve-RequiredFile $launcherPath "Instalador executavel"
Assert-Hash $pythonInstaller $PythonInstallerSha256 "Python" | Out-Null
Assert-Hash $postgresInstaller $PostgreSqlInstallerSha256 "PostgreSQL" | Out-Null
Assert-Hash $winsw $WinSWSha256 "WinSW" | Out-Null

$output = if ([IO.Path]::IsPathRooted($OutputDirectory)) { $OutputDirectory } else { Join-Path $Root $OutputDirectory }
New-Item -ItemType Directory -Path $output -Force | Out-Null
$archive = Join-Path $output "DeTecServer-$Version-windows-offline.zip"
if ((Test-Path -LiteralPath $archive) -and -not $Force) { throw "Pacote ja existe: $archive. Use -Force para substituir." }

$stage = Join-Path $env:TEMP "detech-server-package-$([Guid]::NewGuid().ToString('N'))"
$payload = Join-Path $stage "payload"
New-Item -ItemType Directory -Path $payload -Force | Out-Null
try {
    $files = @(
        @{ origem = $serverPackage; destino = "server.zip"; tipo = "servidor" },
        @{ origem = $pythonInstaller; destino = "python-installer$([IO.Path]::GetExtension($pythonInstaller))"; tipo = "python" },
        @{ origem = $postgresInstaller; destino = "postgresql-installer$([IO.Path]::GetExtension($postgresInstaller))"; tipo = "postgresql" },
        @{ origem = $winsw; destino = "WinSW$([IO.Path]::GetExtension($winsw))"; tipo = "winsw" },
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
            sha256 = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
        }
    }
    Copy-Item -LiteralPath (Join-Path $Root "scripts\install_detech_server_bundle.ps1") -Destination (Join-Path $stage "Install-DeTecServer.ps1")
    $manifest = [ordered]@{
        contrato = "detech_server_offline_bundle_v1"
        versao = $Version
        gerado_em = (Get-Date).ToUniversalTime().ToString("o")
        instalador_executavel = "Instalar DeTec Server.exe"
        instalador = "Install-DeTecServer.ps1"
        arquivos = $manifestFiles
        observacao = "Pacote sem banco, arquivos de clientes, .env ou certificados fiscais."
    }
    [IO.File]::WriteAllText((Join-Path $stage "bundle.manifest.json"), ($manifest | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $archive -CompressionLevel Optimal
    $hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
    [IO.File]::WriteAllText("$archive.sha256", "$hash  $([IO.Path]::GetFileName($archive))`n", [Text.UTF8Encoding]::new($false))
    Write-Host "Pacote offline gerado: $archive"
    Write-Host "SHA-256: $hash"
} finally {
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
