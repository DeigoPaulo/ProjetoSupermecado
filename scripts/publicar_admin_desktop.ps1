param(
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version = '0.1.0',
    [string]$PythonVersion = '3.12'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$AdminApp = Join-Path $Root 'desktop_admin'
$Source = Join-Path $AdminApp 'dist\DeTecAdmin.exe'
$Artifacts = Join-Path $Root 'artifacts'
$Target = Join-Path $Artifacts 'DeTecAdmin.exe'

Push-Location $AdminApp
try {
    powershell -ExecutionPolicy Bypass -File .\build_windows.ps1 -PythonVersion $PythonVersion
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) { throw 'Build nao gerou DeTecAdmin.exe.' }
} finally {
    Pop-Location
}

New-Item -ItemType Directory -Force -Path $Artifacts | Out-Null
Copy-Item -LiteralPath $Source -Destination $Target -Force
$Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Target).Hash.ToLowerInvariant()
$Manifest = @{ version = $Version; filename = 'DeTecAdmin.exe'; sha256 = $Hash; signed = $false; generated_at = (Get-Date).ToUniversalTime().ToString('o') } | ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $Artifacts 'DeTecAdmin.exe.version.json'), $Manifest, [Text.UTF8Encoding]::new($false))
Write-Host "Publicado: $Target"
Write-Host "SHA-256: $Hash"