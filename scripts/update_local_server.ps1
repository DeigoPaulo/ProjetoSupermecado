param(
    [Parameter(Mandatory = $true)]
    [string]$PackagePath,
    [string]$ManifestPath = "",
    [string]$ServiceDirectory = "$env:ProgramData\DeigoVarejo\ServidorLocal",
    [string]$UpdatesDirectory = "$env:ProgramData\DeigoVarejo\Atualizacoes",
    [string]$HealthHost = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [switch]$RequireSignedCommit,
    [switch]$SkipDependencyInstall,
    [switch]$ValidarSomente
)

$ErrorActionPreference = "Stop"
$ServiceName = "DeigoVarejoServidorLocal"
$PackagePath = [IO.Path]::GetFullPath($PackagePath)
if (-not $ManifestPath.Trim()) { $ManifestPath = [IO.Path]::ChangeExtension($PackagePath, "manifest.json") }
$ManifestPath = [IO.Path]::GetFullPath($ManifestPath)
foreach ($required in @($PackagePath, $ManifestPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Arquivo obrigatorio nao encontrado: $required" }
}
if ([IO.Path]::GetExtension($PackagePath).ToLowerInvariant() -ne ".zip") { throw "O pacote de atualizacao deve ser ZIP." }

try { $Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { throw "Manifesto invalido: $($_.Exception.Message)" }
$ActualHash = (Get-FileHash -LiteralPath $PackagePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Manifest.contrato -ne "local_server_package_v1") { throw "Contrato do pacote invalido." }
if ([string]$Manifest.sha256 -ne $ActualHash) { throw "SHA-256 do pacote diverge do manifesto." }
if ([long]$Manifest.tamanho_bytes -ne (Get-Item -LiteralPath $PackagePath).Length) { throw "Tamanho do pacote diverge do manifesto." }
if ([string]$Manifest.arquivo -ne [IO.Path]::GetFileName($PackagePath)) { throw "Nome do pacote diverge do manifesto." }
if ([string]$Manifest.commit -notmatch '^[0-9a-fA-F]{40}$') { throw "Commit de origem invalido." }
if ($Manifest.contem_dados_cliente -ne $false) { throw "Pacote recusado porque nao confirma ausencia de dados do cliente." }
if ($RequireSignedCommit -and $Manifest.commit_assinado_exigido -ne $true) { throw "Pacote nao foi gerado exigindo commit assinado." }
if ([string]$Manifest.versao -notmatch '^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$') { throw "Versao do pacote invalida." }

$CodePaths = @(".env.example", "manage.py", "requirements.txt", "apps", "config", "templates", "static", "scripts", "server_local", "docs")
$Archive = [IO.Compression.ZipFile]::OpenRead($PackagePath)
try {
    if ($Archive.Entries.Count -gt 20000) { throw "Pacote excede o limite de arquivos." }
    $TotalExpanded = [long]0
    $EntryNames = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in $Archive.Entries) {
        $name = $entry.FullName.Replace('\', '/')
        if (-not $name -or $name.StartsWith('/') -or $name -match '(^|/)\.\.(/|$)' -or $name -match '^[A-Za-z]:') { throw "Entrada insegura no ZIP: $name" }
        if ($entry.Length -gt 250MB) { throw "Entrada excede o limite individual: $name" }
        $TotalExpanded += $entry.Length
        if ($TotalExpanded -gt 2GB) { throw "Pacote excede o limite expandido." }
        [void]$EntryNames.Add($name.TrimEnd('/'))
    }
    foreach ($requiredPath in @("manage.py", "requirements.txt", "apps", "config", "templates", "scripts")) {
        $found = $EntryNames.Contains($requiredPath)
        if (-not $found) {
            foreach ($item in $EntryNames) {
                if ($item.StartsWith("$requiredPath/", [StringComparison]::OrdinalIgnoreCase)) { $found = $true; break }
            }
        }
        if (-not $found) { throw "Pacote incompleto: $requiredPath nao encontrado." }
    }
} finally { $Archive.Dispose() }

$Validation = [ordered]@{
    contrato = "local_server_update_validation_v1"
    versao = [string]$Manifest.versao
    commit = [string]$Manifest.commit
    sha256 = $ActualHash
    integridade = $true
    sem_dados_cliente = $true
    commit_assinado_exigido = [bool]$RequireSignedCommit
    commit_assinado_confirmado = [bool]($Manifest.commit_assinado_exigido -eq $true)
}
if ($ValidarSomente) { $Validation | ConvertTo-Json -Depth 4; exit 0 }

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw "Execute este script em um PowerShell aberto como administrador." }

$ServiceExe = Join-Path $ServiceDirectory "$ServiceName.exe"
$ServiceXml = Join-Path $ServiceDirectory "$ServiceName.xml"
foreach ($required in @($ServiceExe, $ServiceXml)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Servico local incompleto: $required" }
}
$Service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $Service) { throw "Servico $ServiceName nao instalado." }
if ($Service.Status -ne "Running") { throw "O servico precisa estar em execucao antes da atualizacao para confirmar seu estado inicial." }

[xml]$ServiceConfig = Get-Content -LiteralPath $ServiceXml -Raw -Encoding UTF8
$Root = [IO.Path]::GetFullPath([string]$ServiceConfig.service.workingdirectory)
$DriveRoot = [IO.Path]::GetPathRoot($Root).TrimEnd('\')
if (-not $Root -or $Root.TrimEnd('\') -eq $DriveRoot -or -not (Test-Path -LiteralPath (Join-Path $Root 'manage.py') -PathType Leaf)) { throw "Diretorio da aplicacao recusado: $Root" }
foreach ($item in $ServiceConfig.service.env) {
    if (@("SQLITE_PATH", "MEDIA_ROOT", "STATIC_ROOT", "LOG_DIR") -contains [string]$item.name) {
        [Environment]::SetEnvironmentVariable([string]$item.name, [string]$item.value, "Process")
    }
}
$SqlitePath = [Environment]::GetEnvironmentVariable("SQLITE_PATH", "Process")
if (-not $SqlitePath -or -not (Test-Path -LiteralPath $SqlitePath -PathType Leaf)) { throw "Atualizacao automatica exige o SQLite configurado e acessivel. Para PostgreSQL, use o procedimento assistido com DBA." }
$SqlitePath = [IO.Path]::GetFullPath($SqlitePath)
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python do ambiente virtual nao encontrado: $Python" }

New-Item -ItemType Directory -Path $UpdatesDirectory -Force | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$OperationRoot = Join-Path $UpdatesDirectory "update-$($Manifest.versao)-$Stamp"
$Staging = Join-Path $OperationRoot "staging"
$Rollback = Join-Path $OperationRoot "rollback"
$RollbackCode = Join-Path $Rollback "code"
New-Item -ItemType Directory -Path $Staging, $RollbackCode -Force | Out-Null
Expand-Archive -LiteralPath $PackagePath -DestinationPath $Staging -Force
foreach ($path in $CodePaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $Staging $path))) { throw "Pacote expandido incompleto: $path" }
}
$CurrentEnv = Join-Path $Root ".env"
if (Test-Path -LiteralPath $CurrentEnv -PathType Leaf) { Copy-Item -LiteralPath $CurrentEnv -Destination (Join-Path $Staging ".env") -Force }
Set-Location $Staging
& $Python -m compileall -q apps config
if ($LASTEXITCODE -ne 0) { throw "Pre-validacao Python do pacote falhou." }

function Assert-ChildPath([string]$Base, [string]$Candidate) {
    $baseFull = [IO.Path]::GetFullPath($Base).TrimEnd('\') + '\'
    $candidateFull = [IO.Path]::GetFullPath($Candidate)
    if (-not $candidateFull.StartsWith($baseFull, [StringComparison]::OrdinalIgnoreCase)) { throw "Operacao recusada fora do diretorio permitido: $candidateFull" }
}
function Copy-CodeLayout([string]$Source, [string]$Destination) {
    foreach ($path in $CodePaths) {
        $sourcePath = Join-Path $Source $path
        $destinationPath = Join-Path $Destination $path
        Assert-ChildPath $Source $sourcePath
        Assert-ChildPath $Destination $destinationPath
        if (-not (Test-Path -LiteralPath $sourcePath)) { throw "Arquivo de codigo ausente: $sourcePath" }
        $parent = Split-Path -Parent $destinationPath
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Recurse -Force
    }
}
function Replace-CodeLayout([string]$Source, [string]$Destination) {
    foreach ($path in $CodePaths) {
        $sourcePath = Join-Path $Source $path
        $destinationPath = Join-Path $Destination $path
        Assert-ChildPath $Source $sourcePath
        Assert-ChildPath $Destination $destinationPath
        if (Test-Path -LiteralPath $destinationPath) { Remove-Item -LiteralPath $destinationPath -Recurse -Force }
        $parent = Split-Path -Parent $destinationPath
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Recurse -Force
    }
}
function Wait-Health([string]$Url) {
    for ($attempt = 1; $attempt -le 20; $attempt++) {
        try { $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4; if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) { return $true } } catch {}
        Start-Sleep -Seconds 2
    }
    return $false
}

Copy-CodeLayout -Source $Root -Destination $RollbackCode
$RollbackDb = Join-Path $Rollback "db.sqlite3"
$RollbackMetadata = [ordered]@{ contrato="local_server_rollback_v1"; versao_destino=[string]$Manifest.versao; commit_destino=[string]$Manifest.commit; criado_em=(Get-Date).ToUniversalTime().ToString("o"); raiz=$Root; sqlite=$SqlitePath; status="preparado" }
[IO.File]::WriteAllText((Join-Path $Rollback "manifest.json"), ($RollbackMetadata | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
$HealthUrl = "http://$HealthHost`:$Port/login/"
$RollbackDbReady = $false
$CodeDeploymentStarted = $false
try {
    & $ServiceExe stop
    if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel parar o servico." }
    (Get-Service -Name $ServiceName).WaitForStatus("Stopped", (New-TimeSpan -Seconds 30))

    $SqliteBackupCode = 'import sqlite3, sys; source=sqlite3.connect(sys.argv[1], timeout=30); target=sqlite3.connect(sys.argv[2]); source.backup(target); target.close(); source.close()'
    & $Python -c $SqliteBackupCode $SqlitePath $RollbackDb
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar snapshot de rollback do SQLite." }
    $RollbackDbReady = $true

    $CodeDeploymentStarted = $true
    Replace-CodeLayout -Source $Staging -Destination $Root
    Set-Location $Root
    if (-not $SkipDependencyInstall) {
        & $Python -m pip install -r (Join-Path $Root "requirements.txt")
        if ($LASTEXITCODE -ne 0) { throw "Instalacao de dependencias falhou." }
    }
    & $Python manage.py check
    if ($LASTEXITCODE -ne 0) { throw "Django check falhou apos atualizar o codigo." }
    & $Python manage.py makemigrations --check --dry-run
    if ($LASTEXITCODE -ne 0) { throw "Pacote possui models sem migration." }
    & $Python manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw "Migrations falharam." }
    & $Python manage.py collectstatic --noinput
    if ($LASTEXITCODE -ne 0) { throw "Collectstatic falhou." }

    & $ServiceExe start
    if ($LASTEXITCODE -ne 0) { throw "Servico nao iniciou apos a atualizacao." }
    if (-not (Wait-Health $HealthUrl)) { throw "Healthcheck falhou apos a atualizacao." }

    $RollbackMetadata.status = "atualizacao_concluida"
    $RollbackMetadata.concluido_em = (Get-Date).ToUniversalTime().ToString("o")
    [IO.File]::WriteAllText((Join-Path $Rollback "manifest.json"), ($RollbackMetadata | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
    $History = [ordered]@{ contrato="local_server_update_history_v1"; versao=[string]$Manifest.versao; commit=[string]$Manifest.commit; sha256=$ActualHash; aplicado_em=(Get-Date).ToUniversalTime().ToString("o"); resultado="sucesso"; rollback=$Rollback }
    Add-Content -LiteralPath (Join-Path $UpdatesDirectory "history.jsonl") -Value ($History | ConvertTo-Json -Compress) -Encoding UTF8
    Write-Host "Atualizacao concluida para a versao $($Manifest.versao)."
    Write-Host "Healthcheck: $HealthUrl"
    Write-Host "Rollback preservado em: $Rollback"
} catch {
    $UpdateError = $_.Exception.Message
    $RollbackError = ""
    try {
        $current = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($current -and $current.Status -ne "Stopped") {
            & $ServiceExe stop | Out-Null
            $current.WaitForStatus("Stopped", (New-TimeSpan -Seconds 30))
        }
        if ($CodeDeploymentStarted) {
            Replace-CodeLayout -Source $RollbackCode -Destination $Root
        }
        if ($RollbackDbReady) {
            foreach ($suffix in @("-wal", "-shm")) {
                $sidecar = "$SqlitePath$suffix"
                if (Test-Path -LiteralPath $sidecar) { Remove-Item -LiteralPath $sidecar -Force }
            }
            Copy-Item -LiteralPath $RollbackDb -Destination $SqlitePath -Force
        }
        Set-Location $Root
        if ($CodeDeploymentStarted -and -not $SkipDependencyInstall) {
            & $Python -m pip install -r (Join-Path $Root "requirements.txt") | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Dependencias anteriores nao foram restauradas." }
        }
        & $ServiceExe start
        if ($LASTEXITCODE -ne 0 -or -not (Wait-Health $HealthUrl)) { throw "O servico nao voltou saudavel depois do rollback." }
        $RollbackMetadata.status = "rollback_concluido"
        $RollbackMetadata.erro_atualizacao = $UpdateError
        $RollbackMetadata.rollback_em = (Get-Date).ToUniversalTime().ToString("o")
        [IO.File]::WriteAllText((Join-Path $Rollback "manifest.json"), ($RollbackMetadata | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
        $History = [ordered]@{ contrato="local_server_update_history_v1"; versao=[string]$Manifest.versao; commit=[string]$Manifest.commit; aplicado_em=(Get-Date).ToUniversalTime().ToString("o"); resultado="rollback"; erro=$UpdateError; rollback=$Rollback }
        Add-Content -LiteralPath (Join-Path $UpdatesDirectory "history.jsonl") -Value ($History | ConvertTo-Json -Compress) -Encoding UTF8
    } catch {
        $RollbackError = $_.Exception.Message
    }
    if ($RollbackError) {
        throw "Falha critica na atualizacao. Erro original: $UpdateError. Rollback tambem falhou: $RollbackError. Use o snapshot em $Rollback."
    }
    throw "Atualizacao cancelada e rollback concluido. Motivo: $UpdateError"} finally {
    if (Test-Path -LiteralPath $Staging) { Remove-Item -LiteralPath $Staging -Recurse -Force }
}