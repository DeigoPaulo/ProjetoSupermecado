param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [string]$Sha256Path = "",
    [string]$SenhaCriptografia = $env:BACKUP_ENCRYPTION_PASSPHRASE,
    [string]$ServiceDirectory = "$env:ProgramData\DeigoVarejo\ServidorLocal",
    [string]$RestoreDirectory = "$env:ProgramData\DeigoVarejo\Restauracoes",
    [string]$PgRestorePath = "",
    [string]$HealthHost = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [switch]$ValidarSomente,
    [switch]$ConfirmarRestauracao
)

$ErrorActionPreference = "Stop"
$ServiceName = "DeigoVarejoServidorLocal"
if (-not $PgRestorePath) {
    $PgRestorePath = $env:POSTGRES_PG_RESTORE_PATH
    $EnvFile = Join-Path (Join-Path $PSScriptRoot "..") ".env"
    if (-not $PgRestorePath -and (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
        $EnvLine = Get-Content -LiteralPath $EnvFile -Encoding UTF8 | Where-Object { $_ -match '^\s*POSTGRES_PG_RESTORE_PATH\s*=' } | Select-Object -Last 1
        if ($EnvLine) {
            $PgRestorePath = ($EnvLine -split '=', 2)[1].Trim().Trim('"').Trim("'")
        }
    }
}
$BackupPath = [IO.Path]::GetFullPath($BackupPath)
if (-not $Sha256Path.Trim()) { $Sha256Path = "$BackupPath.sha256" }
$Sha256Path = [IO.Path]::GetFullPath($Sha256Path)

foreach ($required in @($BackupPath, $Sha256Path)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Arquivo obrigatorio nao encontrado: $required"
    }
}

$ExpectedHashLine = (Get-Content -LiteralPath $Sha256Path -Raw -Encoding ASCII).Trim()
if ($ExpectedHashLine -notmatch '^(?<hash>[0-9a-fA-F]{64})(?:\s+\*?.+)?$') {
    throw "Arquivo SHA-256 invalido: $Sha256Path"
}
$ExpectedHash = $Matches.hash.ToLowerInvariant()
$ActualHash = (Get-FileHash -LiteralPath $BackupPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualHash -ne $ExpectedHash) {
    throw "SHA-256 do backup diverge do arquivo de integridade."
}

$Extension = [IO.Path]::GetExtension($BackupPath).ToLowerInvariant()
if ($Extension -notin @(".zip", ".aes")) {
    throw "O backup deve usar a extensao .zip ou .aes."
}
if ($Extension -eq ".aes" -and -not $SenhaCriptografia) {
    throw "Informe BACKUP_ENCRYPTION_PASSPHRASE ou -SenhaCriptografia para validar o backup criptografado."
}

$ValidationRoot = Join-Path ([IO.Path]::GetTempPath()) ("deigo-varejo-restore-validation-" + [Guid]::NewGuid().ToString("N"))
$ArchivePath = if ($Extension -eq ".zip") { $BackupPath } else { Join-Path $ValidationRoot "backup.zip" }
$Extracted = Join-Path $ValidationRoot "conteudo"
New-Item -ItemType Directory -Path $ValidationRoot, $Extracted -Force | Out-Null

function Unprotect-BackupFile {
    param(
        [Parameter(Mandatory = $true)][string]$InputFile,
        [Parameter(Mandatory = $true)][string]$OutputFile,
        [Parameter(Mandatory = $true)][string]$Passphrase
    )
    $Input = [IO.File]::OpenRead($InputFile)
    try {
        $Header = New-Object byte[] 9
        if ($Input.Read($Header, 0, $Header.Length) -ne $Header.Length -or [Text.Encoding]::ASCII.GetString($Header) -ne "MFLOWAES1") {
            throw "Cabecalho do backup criptografado invalido."
        }
        $Salt = New-Object byte[] 16
        $Iv = New-Object byte[] 16
        if ($Input.Read($Salt, 0, 16) -ne 16 -or $Input.Read($Iv, 0, 16) -ne 16) {
            throw "Backup criptografado incompleto."
        }
        $Kdf = [Security.Cryptography.Rfc2898DeriveBytes]::new($Passphrase, $Salt, 200000, [Security.Cryptography.HashAlgorithmName]::SHA256)
        $Aes = [Security.Cryptography.Aes]::Create()
        $Aes.KeySize = 256
        $Aes.Mode = [Security.Cryptography.CipherMode]::CBC
        $Aes.Padding = [Security.Cryptography.PaddingMode]::PKCS7
        $Aes.Key = $Kdf.GetBytes(32)
        $Aes.IV = $Iv
        $Output = [IO.File]::Create($OutputFile)
        try {
            $Crypto = [Security.Cryptography.CryptoStream]::new($Input, $Aes.CreateDecryptor(), [Security.Cryptography.CryptoStreamMode]::Read)
            try { $Crypto.CopyTo($Output) } finally { $Crypto.Dispose() }
        } finally {
            $Output.Dispose()
            $Aes.Dispose()
            $Kdf.Dispose()
        }
    } catch {
        if (Test-Path -LiteralPath $OutputFile) { Remove-Item -LiteralPath $OutputFile -Force }
        throw "Nao foi possivel descriptografar o backup. Verifique a senha e a integridade. $($_.Exception.Message)"
    } finally {
        $Input.Dispose()
    }
}

function Assert-SafeArchive {
    param([Parameter(Mandatory = $true)][string]$Path)
    $Archive = [IO.Compression.ZipFile]::OpenRead($Path)
    try {
        if ($Archive.Entries.Count -gt 100000) { throw "Backup excede o limite de arquivos." }
        $TotalExpanded = [long]0
        foreach ($entry in $Archive.Entries) {
            $name = $entry.FullName.Replace('\', '/')
            if (-not $name -or $name.StartsWith('/') -or $name -match '(^|/)\.\.(/|$)' -or $name -match '^[A-Za-z]:') {
                throw "Entrada insegura no backup: $name"
            }
            if ($entry.Length -gt 5GB) { throw "Entrada excede o limite individual: $name" }
            $TotalExpanded += $entry.Length
            if ($TotalExpanded -gt 100GB) { throw "Backup excede o limite expandido de seguranca." }
        }
    } finally {
        $Archive.Dispose()
    }
}

function Wait-Health {
    param([Parameter(Mandatory = $true)][string]$Url)
    for ($attempt = 1; $attempt -le 20; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) { return $true }
        } catch {}
        Start-Sleep -Seconds 2
    }
    return $false
}

function Assert-SafeDataPath {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][string]$Label)
    if (-not $Path) { throw "$Label nao configurado." }
    $Full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    $Drive = [IO.Path]::GetPathRoot($Full).TrimEnd('\')
    if (-not $Full -or $Full -eq $Drive) { throw "$Label recusado por apontar para a raiz: $Full" }
    return $Full
}

try {
    if ($Extension -eq ".aes") {
        Unprotect-BackupFile -InputFile $BackupPath -OutputFile $ArchivePath -Passphrase $SenhaCriptografia
    }
    Assert-SafeArchive -Path $ArchivePath
    [IO.Compression.ZipFile]::ExtractToDirectory($ArchivePath, $Extracted)

    $ManifestPath = Join-Path $Extracted "manifesto.json"
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) { throw "Manifesto do backup nao encontrado." }
    try { $Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch {
        throw "Manifesto do backup invalido: $($_.Exception.Message)"
    }
    if ($Manifest.contrato -ne "erp_local_backup_v2") { throw "Contrato do backup invalido." }
    if ($Manifest.inclui_dados_json -ne $true -or -not (Test-Path -LiteralPath (Join-Path $Extracted "dados.json") -PathType Leaf)) {
        throw "Backup logico dados.json ausente."
    }
    if ($Manifest.inclui_sqlite -eq $true) {
        if ($Manifest.sqlite_snapshot_consistente -ne $true -or -not (Test-Path -LiteralPath (Join-Path $Extracted "db.sqlite3") -PathType Leaf)) {
            throw "Snapshot SQLite consistente ausente."
        }
    }
    $BackupDatabaseType = if ([string]$Manifest.banco_tipo) { [string]$Manifest.banco_tipo } elseif ($Manifest.inclui_sqlite -eq $true) { "sqlite" } elseif ($Manifest.inclui_postgresql -eq $true) { "postgresql" } else { "" }
    if ($BackupDatabaseType -notin @("sqlite", "postgresql")) { throw "Tipo de banco do backup ausente ou invalido." }
    $PgRestore = ""
    $PgRestoreVersion = ""
    if ($BackupDatabaseType -eq "postgresql") {
        $PgDumpFile = Join-Path $Extracted "database.dump"
        if ($Manifest.inclui_postgresql -ne $true -or $Manifest.postgresql_dump_formato -ne "custom" -or -not (Test-Path -LiteralPath $PgDumpFile -PathType Leaf)) {
            throw "Dump PostgreSQL custom declarado no manifesto nao foi encontrado."
        }
        $PgRestoreCommand = if ($PgRestorePath) { $PgRestorePath } else { "pg_restore" }
        $PgRestoreInfo = Get-Command $PgRestoreCommand -ErrorAction SilentlyContinue
        if (-not $PgRestoreInfo) { throw "pg_restore nao encontrado. Instale as ferramentas cliente do PostgreSQL ou configure POSTGRES_PG_RESTORE_PATH." }
        $PgRestore = $PgRestoreInfo.Source
        $PgRestoreVersion = (& $PgRestore --version | Select-Object -First 1)
        & $PgRestore --list $PgDumpFile | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "pg_restore recusou o dump PostgreSQL." }
    }
    if ($Manifest.inclui_media -eq $true -and -not (Test-Path -LiteralPath (Join-Path $Extracted "media") -PathType Container)) {
        throw "Diretorio de midia declarado no manifesto nao foi encontrado."
    }

    $Validation = [ordered]@{
        contrato = "local_restore_validation_v1"
        backup_contrato = [string]$Manifest.contrato
        arquivo = [IO.Path]::GetFileName($BackupPath)
        sha256 = $ActualHash
        integridade = $true
        criptografado = [bool]($Extension -eq ".aes")
        gerado_em = [string]$Manifest.gerado_em
        banco_tipo = $BackupDatabaseType
        inclui_sqlite = [bool]$Manifest.inclui_sqlite
        inclui_postgresql = [bool]$Manifest.inclui_postgresql
        pg_restore_versao = [string]$PgRestoreVersion
        inclui_media = [bool]$Manifest.inclui_media
        inclui_logs = [bool]$Manifest.inclui_logs
        pronto_para_restaurar = [bool]($BackupDatabaseType -in @("sqlite", "postgresql"))
    }
    if ($ValidarSomente) {
        $Validation | ConvertTo-Json -Depth 4
        exit 0
    }
    if (-not $ConfirmarRestauracao) {
        throw "Restaure somente apos validar. Repita com -ConfirmarRestauracao para autorizar a alteracao dos dados."
    }

    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Execute a restauracao em um PowerShell aberto como administrador."
    }

    $ServiceExe = Join-Path $ServiceDirectory "$ServiceName.exe"
    $ServiceXml = Join-Path $ServiceDirectory "$ServiceName.xml"
    foreach ($required in @($ServiceExe, $ServiceXml)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Servico local incompleto: $required" }
    }
    $Service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $Service -or $Service.Status -ne "Running") { throw "O servico $ServiceName precisa estar em execucao antes da restauracao." }

    [xml]$ServiceConfig = Get-Content -LiteralPath $ServiceXml -Raw -Encoding UTF8
    $Root = Assert-SafeDataPath -Path ([string]$ServiceConfig.service.workingdirectory) -Label "Diretorio da aplicacao"
    if (-not (Test-Path -LiteralPath (Join-Path $Root "manage.py") -PathType Leaf)) { throw "Aplicacao local nao encontrada em $Root" }
    foreach ($item in $ServiceConfig.service.env) {
        if (@("SQLITE_PATH", "MEDIA_ROOT", "STATIC_ROOT", "LOG_DIR") -contains [string]$item.name) {
            [Environment]::SetEnvironmentVariable([string]$item.name, [string]$item.value, "Process")
        }
    }
    $Python = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python do ambiente local nao encontrado: $Python" }
    Set-Location $Root
    $RuntimeCode = "import json, os, django; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); django.setup(); from django.conf import settings; db=settings.DATABASES['default']; print(json.dumps({'db_engine': str(db.get('ENGINE') or ''), 'db_name': str(db.get('NAME') or ''), 'db_user': str(db.get('USER') or ''), 'db_password': str(db.get('PASSWORD') or ''), 'db_host': str(db.get('HOST') or ''), 'db_port': str(db.get('PORT') or ''), 'media_root': str(settings.MEDIA_ROOT)}))"
    $RuntimeJson = & $Python -c $RuntimeCode
    if ($LASTEXITCODE -ne 0 -or -not $RuntimeJson) { throw "Nao foi possivel descobrir o banco configurado no servidor local." }
    try { $Runtime = $RuntimeJson | ConvertFrom-Json } catch { throw "Diagnostico do banco local invalido: $($_.Exception.Message)" }
    $TargetIsSqlite = [string]$Runtime.db_engine -match "sqlite3$"
    $TargetIsPostgres = [string]$Runtime.db_engine -match "postgresql$"
    $TargetDatabaseType = if ($TargetIsPostgres) { "postgresql" } elseif ($TargetIsSqlite) { "sqlite" } else { "" }
    if ($TargetDatabaseType -ne $BackupDatabaseType) { throw "O backup usa $BackupDatabaseType, mas o servidor esta configurado com $TargetDatabaseType. Restauracao cruzada foi recusada." }
    $SqlitePath = if ($TargetIsSqlite) { Assert-SafeDataPath -Path ([string]$Runtime.db_name) -Label "SQLITE_PATH" } else { "" }
    $MediaPath = Assert-SafeDataPath -Path ([string]$Runtime.media_root) -Label "MEDIA_ROOT"
    function Invoke-PostgresRestoreFile {
        param([Parameter(Mandatory = $true)][string]$DumpPath)
        $PgRestoreArgs = @("--clean", "--if-exists", "--no-owner", "--no-acl", "--exit-on-error", "--single-transaction")
        if ([string]$Runtime.db_host) { $PgRestoreArgs += "--host=$($Runtime.db_host)" }
        if ([string]$Runtime.db_port) { $PgRestoreArgs += "--port=$($Runtime.db_port)" }
        if ([string]$Runtime.db_user) { $PgRestoreArgs += "--username=$($Runtime.db_user)" }
        $PgRestoreArgs += "--dbname=$($Runtime.db_name)"
        $PgRestoreArgs += $DumpPath
        $PreviousPgPassword = $env:PGPASSWORD
        try {
            if ([string]$Runtime.db_password) { $env:PGPASSWORD = [string]$Runtime.db_password }
            & $PgRestore @PgRestoreArgs
            if ($LASTEXITCODE -ne 0) { throw "pg_restore falhou para $DumpPath" }
        } finally {
            $env:PGPASSWORD = $PreviousPgPassword
        }
    }

    New-Item -ItemType Directory -Path $RestoreDirectory -Force | Out-Null
    $Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OperationRoot = Join-Path $RestoreDirectory "restore-$Stamp"
    $SafetyDirectory = Join-Path $OperationRoot "antes-da-restauracao"
    New-Item -ItemType Directory -Path $SafetyDirectory -Force | Out-Null
    $BackupScript = Join-Path $Root "scripts\backup_local.ps1"
    & $BackupScript -Destino $SafetyDirectory -ServiceDirectory $ServiceDirectory
    if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel criar o backup de seguranca anterior a restauracao." }
    $SafetyZip = Get-ChildItem -LiteralPath $SafetyDirectory -File -Filter "*.zip" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $SafetyZip) { throw "Backup de seguranca anterior nao foi localizado." }
    $SafetyExtracted = Join-Path $OperationRoot "rollback"
    [IO.Compression.ZipFile]::ExtractToDirectory($SafetyZip.FullName, $SafetyExtracted)

    $HealthUrl = "http://$HealthHost`:$Port/login/"
    $DataChanged = $false
    $MediaExistedBefore = Test-Path -LiteralPath $MediaPath -PathType Container
    try {
        & $ServiceExe stop
        if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel parar o servico." }
        (Get-Service -Name $ServiceName).WaitForStatus("Stopped", (New-TimeSpan -Seconds 30))
        if ($TargetIsSqlite) {
            foreach ($suffix in @("-wal", "-shm")) {
                $sidecar = "$SqlitePath$suffix"
                if (Test-Path -LiteralPath $sidecar) { Remove-Item -LiteralPath $sidecar -Force }
            }
            New-Item -ItemType Directory -Path (Split-Path -Parent $SqlitePath) -Force | Out-Null
            Copy-Item -LiteralPath (Join-Path $Extracted "db.sqlite3") -Destination $SqlitePath -Force
        } else {
            Invoke-PostgresRestoreFile -DumpPath (Join-Path $Extracted "database.dump")
        }
        $DataChanged = $true
        if ($Manifest.inclui_media -eq $true) {
            if (Test-Path -LiteralPath $MediaPath) { Remove-Item -LiteralPath $MediaPath -Recurse -Force }
            Copy-Item -LiteralPath (Join-Path $Extracted "media") -Destination $MediaPath -Recurse -Force
        }
        Set-Location $Root
        & $Python manage.py migrate --noinput
        if ($LASTEXITCODE -ne 0) { throw "Migrations falharam sobre o banco restaurado." }
        & $Python manage.py check
        if ($LASTEXITCODE -ne 0) { throw "Django check falhou apos a restauracao." }
        & $ServiceExe start
        if ($LASTEXITCODE -ne 0 -or -not (Wait-Health -Url $HealthUrl)) { throw "Healthcheck falhou apos a restauracao." }
        $History = [ordered]@{ contrato = "local_restore_history_v1"; restaurado_em = (Get-Date).ToUniversalTime().ToString("o"); arquivo = [IO.Path]::GetFileName($BackupPath); sha256 = $ActualHash; resultado = "sucesso"; backup_seguranca = $SafetyZip.FullName }
        [IO.File]::WriteAllText((Join-Path $OperationRoot "resultado.json"), ($History | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
        Write-Host "Restauracao concluida e healthcheck aprovado."
        Write-Host "Backup anterior preservado em: $($SafetyZip.FullName)"
    } catch {
        $RestoreError = $_.Exception.Message
        $RollbackError = ""
        try {
            $current = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
            if ($current -and $current.Status -ne "Stopped") {
                & $ServiceExe stop | Out-Null
                $current.WaitForStatus("Stopped", (New-TimeSpan -Seconds 30))
            }
            if ($DataChanged) {
                if ($TargetIsSqlite) {
                    Copy-Item -LiteralPath (Join-Path $SafetyExtracted "db.sqlite3") -Destination $SqlitePath -Force
                } else {
                    Invoke-PostgresRestoreFile -DumpPath (Join-Path $SafetyExtracted "database.dump")
                }
                $SafetyMedia = Join-Path $SafetyExtracted "media"
                if (Test-Path -LiteralPath $SafetyMedia -PathType Container) {
                    if (Test-Path -LiteralPath $MediaPath) { Remove-Item -LiteralPath $MediaPath -Recurse -Force }
                    Copy-Item -LiteralPath $SafetyMedia -Destination $MediaPath -Recurse -Force
                } elseif (-not $MediaExistedBefore -and (Test-Path -LiteralPath $MediaPath)) {
                    Remove-Item -LiteralPath $MediaPath -Recurse -Force
                }
            }
            & $ServiceExe start
            if ($LASTEXITCODE -ne 0 -or -not (Wait-Health -Url $HealthUrl)) { throw "Servico nao voltou saudavel depois do rollback." }
        } catch {
            $RollbackError = $_.Exception.Message
        }
        if ($RollbackError) {
            throw "Falha critica na restauracao. Erro original: $RestoreError. Rollback tambem falhou: $RollbackError. Use $($SafetyZip.FullName)."
        }
        throw "Restauracao cancelada e dados anteriores recuperados. Motivo: $RestoreError"
    }
} finally {
    if (Test-Path -LiteralPath $ValidationRoot) { Remove-Item -LiteralPath $ValidationRoot -Recurse -Force }
}
