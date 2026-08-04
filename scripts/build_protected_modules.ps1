param(
    [string]$Commit = "HEAD",
    [string]$OutputDirectory = "dist\protected_modules",
    [string]$PythonPath = ".venv\Scripts\python.exe",
    [string[]]$Modules = @("apps.licenciamento.services"),
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
$Python = if ([IO.Path]::IsPathRooted($PythonPath)) { $PythonPath } else { Join-Path $Root $PythonPath }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python de build nao encontrado: $Python" }
if ((git status --porcelain).Count -gt 0) {
    throw "A arvore Git possui alteracoes. Crie um commit antes de compilar os modulos protegidos."
}
$CommitSha = (git rev-parse --verify "$Commit^{commit}").Trim()
if ($LASTEXITCODE -ne 0 -or -not $CommitSha) { throw "Commit invalido: $Commit" }
$Output = if ([IO.Path]::IsPathRooted($OutputDirectory)) { $OutputDirectory } else { Join-Path $Root $OutputDirectory }
if (Test-Path -LiteralPath $Output) {
    if (-not $Force) { throw "Saida ja existe: $Output. Use -Force para recriar." }
    Remove-Item -LiteralPath $Output -Recurse -Force
}
New-Item -ItemType Directory -Path $Output -Force | Out-Null
$Arguments = @("scripts/protected_modules.py", "build", "--root", $Root, "--overlay", $Output, "--commit", $CommitSha)
foreach ($Module in $Modules) { $Arguments += @("--module", $Module) }
& $Python @Arguments
if ($LASTEXITCODE -ne 0) {
    Remove-Item -LiteralPath $Output -Recurse -Force -ErrorAction SilentlyContinue
    throw "Falha ao compilar os modulos protegidos."
}
Write-Host "Overlay protegido gerado em: $Output"
