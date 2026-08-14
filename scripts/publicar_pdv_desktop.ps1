param(
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version = '0.1.15',
    [string]$PythonVersion = '3.12'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$PdvApp = Join-Path $Root 'desktop_pdv'

Push-Location $PdvApp
try {
    & powershell -ExecutionPolicy Bypass -File .\build_windows.ps1 -PythonVersion $PythonVersion
    if ($LASTEXITCODE -ne 0) { throw "Build do PDV falhou com codigo $LASTEXITCODE." }
    & powershell -ExecutionPolicy Bypass -File .\publish_windows.ps1 -Version $Version
    if ($LASTEXITCODE -ne 0) { throw "Publicacao do PDV falhou com codigo $LASTEXITCODE." }
} finally {
    Pop-Location
}

$Artifact = Join-Path $Root 'artifacts\DeTecPDV.exe'
if (-not (Test-Path -LiteralPath $Artifact -PathType Leaf)) { throw 'Publicacao do PDV nao encontrou DeTecPDV.exe em artifacts.' }
Write-Host "PDV publicado: $Artifact"