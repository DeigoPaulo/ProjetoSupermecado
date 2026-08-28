param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")]
    [string]$Version,
    [string]$SourceDirectory = "dist\detech_server_offline",
    [string]$Destination = "artifacts\DeTecServerOffline.zip",
    [string]$PythonPath = ".venv\Scripts\python.exe",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$SourceRoot = if ([IO.Path]::IsPathRooted($SourceDirectory)) { $SourceDirectory } else { Join-Path $Root $SourceDirectory }
$DestinationPath = if ([IO.Path]::IsPathRooted($Destination)) { $Destination } else { Join-Path $Root $Destination }
$SourceArchive = Join-Path $SourceRoot "DeTecServer-$Version-windows-offline.zip"
$SourceChecksum = "$SourceArchive.sha256"
$DestinationChecksum = "$DestinationPath.sha256"

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

function Invoke-OfflineValidation([string]$Path, [string]$ExpectedVersion, [string]$Python) {
    $code = "import json,sys; from pathlib import Path; from apps.configuracoes.offline_bundle import validar_pacote_servidor_offline; r=validar_pacote_servidor_offline(Path(sys.argv[1]), sys.argv[2]); print(json.dumps({k:v for k,v in r.items() if k != 'caminho'}, ensure_ascii=False, default=str)); sys.exit(0 if r['publicavel'] else 2)"
    $json = & $Python -c $code $Path $ExpectedVersion
    if ($LASTEXITCODE -ne 0) {
        throw "Pacote offline recusado pelo contrato de validacao: $json"
    }
    $validation = $json | ConvertFrom-Json
    if ($validation.contrato -ne "detech_server_offline_package_validation_v2" -or $validation.publicavel -ne $true) {
        throw "Resultado inesperado da validacao do pacote offline."
    }
    return $validation
}

if ([IO.Path]::GetExtension($DestinationPath).ToLowerInvariant() -ne ".zip") {
    throw "O destino publicado deve possuir extensao .zip."
}
foreach ($source in @($SourceArchive, $SourceChecksum)) {
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Artefato de origem obrigatorio nao encontrado."
    }
}
$Python = if ([IO.Path]::IsPathRooted($PythonPath)) { $PythonPath } else { Join-Path $Root $PythonPath }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python do projeto nao encontrado para validar o pacote."
}
$sourceFull = [IO.Path]::GetFullPath($SourceArchive)
$destinationFull = [IO.Path]::GetFullPath($DestinationPath)
if ($sourceFull.Equals($destinationFull, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Origem e destino da publicacao devem ser diferentes."
}

$sourceHash = Get-Sha256 $SourceArchive
$checksumLine = ([IO.File]::ReadAllText($SourceChecksum)).Trim()
$checksumMatch = [regex]::Match($checksumLine, "^([A-Fa-f0-9]{64})\s{2}(.+)$")
if (-not $checksumMatch.Success) {
    throw "Arquivo SHA-256 de origem invalido."
}
if ($checksumMatch.Groups[1].Value.ToUpperInvariant() -ne $sourceHash) {
    throw "SHA-256 de origem diverge do pacote."
}
if ($checksumMatch.Groups[2].Value -ne [IO.Path]::GetFileName($SourceArchive)) {
    throw "Nome vinculado ao SHA-256 de origem diverge do pacote."
}
$sourceValidation = Invoke-OfflineValidation $SourceArchive $Version $Python

$DestinationDirectory = Split-Path -Parent $DestinationPath
New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null
if (((Test-Path -LiteralPath $DestinationPath) -or (Test-Path -LiteralPath $DestinationChecksum)) -and -not $Force) {
    throw "Ja existe um pacote offline publicado. Use -Force para substituir."
}

$operation = [Guid]::NewGuid().ToString("N")
$archiveTemp = Join-Path $DestinationDirectory "$([IO.Path]::GetFileNameWithoutExtension($DestinationPath)).uploading-$operation.zip"
$checksumTemp = "$DestinationChecksum.uploading-$operation"
$archiveRollback = "$DestinationPath.rollback-$operation"
$checksumRollback = "$DestinationChecksum.rollback-$operation"
$hadArchive = Test-Path -LiteralPath $DestinationPath -PathType Leaf
$hadChecksum = Test-Path -LiteralPath $DestinationChecksum -PathType Leaf
$promotedArchive = $false
$promotedChecksum = $false

try {
    Copy-Item -LiteralPath $SourceArchive -Destination $archiveTemp -Force
    if ((Get-Sha256 $archiveTemp) -ne $sourceHash) {
        throw "Falha de integridade durante a copia para publicacao."
    }
    $copyValidation = Invoke-OfflineValidation $archiveTemp $Version $Python
    $checksumContent = "$sourceHash  $([IO.Path]::GetFileName($DestinationPath))" + [Environment]::NewLine
    [IO.File]::WriteAllText($checksumTemp, $checksumContent, [Text.UTF8Encoding]::new($false))

    if ($hadArchive) { Copy-Item -LiteralPath $DestinationPath -Destination $archiveRollback -Force }
    if ($hadChecksum) { Copy-Item -LiteralPath $DestinationChecksum -Destination $checksumRollback -Force }

    try {
        Move-Item -LiteralPath $archiveTemp -Destination $DestinationPath -Force
        $promotedArchive = $true
        Move-Item -LiteralPath $checksumTemp -Destination $DestinationChecksum -Force
        $promotedChecksum = $true
    } catch {
        if ($hadArchive -and (Test-Path -LiteralPath $archiveRollback -PathType Leaf)) {
            Move-Item -LiteralPath $archiveRollback -Destination $DestinationPath -Force
        } elseif ($promotedArchive) {
            Remove-Item -LiteralPath $DestinationPath -Force -ErrorAction SilentlyContinue
        }
        if ($hadChecksum -and (Test-Path -LiteralPath $checksumRollback -PathType Leaf)) {
            Move-Item -LiteralPath $checksumRollback -Destination $DestinationChecksum -Force
        } elseif ($promotedChecksum) {
            Remove-Item -LiteralPath $DestinationChecksum -Force -ErrorAction SilentlyContinue
        }
        throw
    }

    Write-Host "Pacote offline publicado e validado: $DestinationPath"
    Write-Host "Contrato: $($copyValidation.contrato)"
    Write-Host "SHA-256: $sourceHash"
} finally {
    foreach ($temporary in @($archiveTemp, $checksumTemp, $archiveRollback, $checksumRollback)) {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}
