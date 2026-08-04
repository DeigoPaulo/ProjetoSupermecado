param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")]
    [string]$Version,
    [string]$SourceDirectory = "dist\server_local",
    [string]$Destination = "artifacts\DeigoVarejoServidorLocal.zip",
    [string]$PythonPath = ".venv\Scripts\python.exe",
    [switch]$RequireSignedCommit,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$SourceRoot = if ([IO.Path]::IsPathRooted($SourceDirectory)) { $SourceDirectory } else { Join-Path $Root $SourceDirectory }
$DestinationPath = if ([IO.Path]::IsPathRooted($Destination)) { $Destination } else { Join-Path $Root $Destination }
$SourceBase = "DeigoVarejoServidorLocal-$Version"
$SourceArchive = Join-Path $SourceRoot "$SourceBase.zip"
$SourceManifest = Join-Path $SourceRoot "$SourceBase.manifest.json"
$DestinationManifest = [IO.Path]::ChangeExtension($DestinationPath, "manifest.json")

if ([IO.Path]::GetExtension($DestinationPath).ToLowerInvariant() -ne ".zip") {
    throw "O destino publicado deve possuir extensao .zip."
}
foreach ($source in @($SourceArchive, $SourceManifest)) {
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Artefato de origem nao encontrado: $source"
    }
}

try {
    $Manifest = Get-Content -LiteralPath $SourceManifest -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    throw "Manifesto de origem invalido: $($_.Exception.Message)"
}
$ActualHash = (Get-FileHash -LiteralPath $SourceArchive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Manifest.contrato -ne "local_server_package_v1") { throw "Contrato do pacote invalido." }
if ([string]$Manifest.versao -ne $Version) { throw "Versao do manifesto diverge da versao solicitada." }
if ([string]$Manifest.arquivo -ne [IO.Path]::GetFileName($SourceArchive)) { throw "Nome do arquivo diverge do manifesto." }
if ([string]$Manifest.sha256 -ne $ActualHash) { throw "SHA-256 do pacote diverge do manifesto." }
if ([long]$Manifest.tamanho_bytes -ne (Get-Item -LiteralPath $SourceArchive).Length) { throw "Tamanho do pacote diverge do manifesto." }
if ($Manifest.contem_dados_cliente -ne $false) { throw "O pacote nao confirma ausencia de dados do cliente." }
$Python = if ([IO.Path]::IsPathRooted($PythonPath)) { $PythonPath } else { Join-Path $Root $PythonPath }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python do projeto nao encontrado para validar o pacote: $Python" }
$ValidationCode = "import json,sys; from pathlib import Path; from apps.configuracoes.artifacts import validar_conteudo_pacote_servidor; r=validar_conteudo_pacote_servidor(Path(sys.argv[1])); print(json.dumps(r, ensure_ascii=False)); sys.exit(0 if r['valido'] else 2)"
$ValidationJson = & $Python -c $ValidationCode $SourceArchive
if ($LASTEXITCODE -ne 0) { throw "Conteudo do pacote recusado antes da publicacao: $ValidationJson" }
$ContentValidation = $ValidationJson | ConvertFrom-Json
if ($ContentValidation.contrato -ne "local_server_package_content_v1" -or $ContentValidation.valido -ne $true) {
    throw "Contrato de validacao do conteudo do pacote invalido."
}
if ($RequireSignedCommit -and $Manifest.commit_assinado_exigido -ne $true) {
    throw "O pacote nao foi gerado exigindo commit Git assinado."
}

$DestinationDirectory = Split-Path -Parent $DestinationPath
New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null
if (((Test-Path -LiteralPath $DestinationPath) -or (Test-Path -LiteralPath $DestinationManifest)) -and -not $Force) {
    throw "Ja existe um pacote publicado. Use -Force para substituir."
}

$ArchiveTemp = "$DestinationPath.uploading"
$ManifestTemp = "$DestinationManifest.uploading"
Remove-Item -LiteralPath $ArchiveTemp, $ManifestTemp -Force -ErrorAction SilentlyContinue
Copy-Item -LiteralPath $SourceArchive -Destination $ArchiveTemp -Force
if ((Get-FileHash -LiteralPath $ArchiveTemp -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ActualHash) {
    Remove-Item -LiteralPath $ArchiveTemp -Force -ErrorAction SilentlyContinue
    throw "Falha de integridade durante a copia para publicacao."
}

$PublishedManifest = [ordered]@{}
$Manifest.psobject.Properties | ForEach-Object { $PublishedManifest[$_.Name] = $_.Value }
$PublishedManifest["arquivo_origem"] = [IO.Path]::GetFileName($SourceArchive)
$PublishedManifest["arquivo"] = [IO.Path]::GetFileName($DestinationPath)
$PublishedManifest["publicado_em"] = (Get-Date).ToUniversalTime().ToString("o")
[IO.File]::WriteAllText($ManifestTemp, ($PublishedManifest | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))

Move-Item -LiteralPath $ArchiveTemp -Destination $DestinationPath -Force
Move-Item -LiteralPath $ManifestTemp -Destination $DestinationManifest -Force
Write-Host "Pacote publicado: $DestinationPath"
Write-Host "Manifesto publicado: $DestinationManifest"
Write-Host "SHA-256: $ActualHash"
