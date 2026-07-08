param(
    [string]$Version = "0.1.0",
    [string]$Destination
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $Root
$Source = Join-Path $Root "dist\SupermercadoPDV.exe"
if (-not $Destination) {
    $Destination = Join-Path $ProjectRoot "artifacts\SupermercadoPDV.exe"
}

if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
    throw "Build nao encontrado em $Source. Execute build_windows.ps1 primeiro."
}

$Destination = [System.IO.Path]::GetFullPath($Destination)
$DestinationDir = Split-Path -Parent $Destination
New-Item -ItemType Directory -Path $DestinationDir -Force | Out-Null

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
    published_at_utc = [DateTime]::UtcNow.ToString("o")
}
$Metadata | ConvertTo-Json | Set-Content -LiteralPath "$Destination.version.json" -Encoding UTF8

Write-Host "PDV Desktop $Version publicado em $Destination"
Write-Host "SHA-256: $SourceHash"
