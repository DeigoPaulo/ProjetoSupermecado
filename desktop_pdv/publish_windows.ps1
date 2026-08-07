param(
    [string]$Version = "0.1.9",
    [string]$Source,
    [string]$Destination,
    [switch]$RequireSignature
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $Root
if (-not $Source) {
    $Msi = Join-Path $Root "dist\DeTecPDV-$Version-x64.msi"
    $Source = if (Test-Path -LiteralPath $Msi -PathType Leaf) {
        $Msi
    } else {
        Join-Path $Root "dist\DeTecPDV.exe"
    }
}
if (-not $Destination) {
    $Extension = [System.IO.Path]::GetExtension($Source)
    $Destination = Join-Path $ProjectRoot "artifacts\DeTecPDV$Extension"
}

$Source = [System.IO.Path]::GetFullPath($Source)
if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
    throw "Build nao encontrado em $Source. Execute build_windows.ps1 e, para MSI, build_msi.ps1 primeiro."
}

$Destination = [System.IO.Path]::GetFullPath($Destination)
$DestinationDir = Split-Path -Parent $Destination
New-Item -ItemType Directory -Path $DestinationDir -Force | Out-Null

$SourceExtension = [System.IO.Path]::GetExtension($Source).ToLowerInvariant()
$SourceMetadataPath = "$Source.version.json"
$SourceMetadata = if (Test-Path -LiteralPath $SourceMetadataPath -PathType Leaf) {
    Get-Content -LiteralPath $SourceMetadataPath -Raw | ConvertFrom-Json
} else {
    $null
}
$PublishedSignature = (Get-AuthenticodeSignature -LiteralPath $Source).Status.ToString()
$ExecutableSignature = if ($SourceExtension -eq ".msi") {
    if ($SourceMetadata) { [string]$SourceMetadata.executable_signature } else { "Unknown" }
} else {
    $PublishedSignature
}
$MsiSignature = if ($SourceExtension -eq ".msi") { $PublishedSignature } else { "" }
if ($RequireSignature -and ($PublishedSignature -ne "Valid" -or ($SourceExtension -eq ".msi" -and $ExecutableSignature -ne "Valid"))) {
    throw "O artefato publicado nao possui todas as assinaturas digitais validas."
}
$Temporary = "$Destination.uploading"
Copy-Item -LiteralPath $Source -Destination $Temporary -Force
$SourceHash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash
$TemporaryHash = (Get-FileHash -LiteralPath $Temporary -Algorithm SHA256).Hash
if ($SourceHash -ne $TemporaryHash) {
    Remove-Item -LiteralPath $Temporary -Force
    throw "Falha de integridade ao publicar o executavel."
}

Move-Item -LiteralPath $Temporary -Destination $Destination -Force
$File = Get-Item -LiteralPath $Destination
$Metadata = [ordered]@{
    version = $Version
    filename = $File.Name
    size_bytes = $File.Length
    sha256 = $SourceHash.ToLowerInvariant()
    executable_signature = $ExecutableSignature
    msi_signature = $MsiSignature
    published_at_utc = [DateTime]::UtcNow.ToString("o")
}
$Metadata | ConvertTo-Json | Set-Content -LiteralPath "$Destination.version.json" -Encoding UTF8

Write-Host "PDV Desktop $Version publicado em $Destination"
Write-Host "SHA-256: $SourceHash"
