param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")]
    [string]$Version,
    [string]$Commit = "HEAD",
    [string]$OutputDirectory = "dist\server_local",
    [switch]$RequireSignedCommit,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git nao encontrado. O pacote deve ser gerado a partir de um commit rastreavel."
}
if ((git status --porcelain).Count -gt 0) {
    throw "A arvore Git possui alteracoes. Revise e crie um commit antes de empacotar o servidor local."
}
$CommitSha = (git rev-parse --verify "$Commit^{commit}").Trim()
if ($LASTEXITCODE -ne 0 -or -not $CommitSha) {
    throw "Commit invalido: $Commit"
}
if ($RequireSignedCommit) {
    git verify-commit $CommitSha
    if ($LASTEXITCODE -ne 0) { throw "O commit $CommitSha nao possui assinatura Git valida." }
}

$Output = if ([IO.Path]::IsPathRooted($OutputDirectory)) { $OutputDirectory } else { Join-Path $Root $OutputDirectory }
New-Item -ItemType Directory -Path $Output -Force | Out-Null
$BaseName = "DeigoVarejoServidorLocal-$Version"
$Archive = Join-Path $Output "$BaseName.zip"
$Manifest = Join-Path $Output "$BaseName.manifest.json"
$Checksum = Join-Path $Output "$BaseName.sha256"
foreach ($target in @($Archive, $Manifest, $Checksum)) {
    if ((Test-Path -LiteralPath $target) -and -not $Force) {
        throw "Artefato ja existe: $target. Use -Force para substituir."
    }
}

$TempArchive = "$Archive.tmp"
Remove-Item -LiteralPath $TempArchive -Force -ErrorAction SilentlyContinue
$Paths = @(
    ".env.example", "manage.py", "requirements.txt", "apps", "config", "templates",
    "static", "scripts", "server_local", "docs"
)
git archive --format=zip --output=$TempArchive $CommitSha -- $Paths
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $TempArchive -PathType Leaf)) {
    throw "Falha ao gerar o arquivo do servidor local."
}
Move-Item -LiteralPath $TempArchive -Destination $Archive -Force
$Hash = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash
$Payload = [ordered]@{
    contrato = "local_server_package_v1"
    versao = $Version
    commit = $CommitSha
    commit_assinado_exigido = [bool]$RequireSignedCommit
    gerado_em = (Get-Date).ToUniversalTime().ToString("o")
    arquivo = [IO.Path]::GetFileName($Archive)
    tamanho_bytes = (Get-Item -LiteralPath $Archive).Length
    sha256 = $Hash
    contem_dados_cliente = $false
    inclui = $Paths
    instalacao = [ordered]@{
        preparar = ".\scripts\setup_local.ps1"
        servico = ".\scripts\install_local_server_service.ps1"
        guia = "docs\IMPLANTACAO_SERVIDOR_LOCAL.md"
    }
}
$ManifestTemp = "$Manifest.tmp"
[IO.File]::WriteAllText($ManifestTemp, ($Payload | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $ManifestTemp -Destination $Manifest -Force
[IO.File]::WriteAllText($Checksum, "$Hash  $([IO.Path]::GetFileName($Archive))`n", [Text.UTF8Encoding]::new($false))

Write-Host "Pacote gerado: $Archive"
Write-Host "Manifesto: $Manifest"
Write-Host "SHA-256: $Hash"
