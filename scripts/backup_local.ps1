param(
    [string]$Destino = "",
    [ValidateRange(1, 3650)]
    [int]$RetencaoDias = 30,
    [switch]$IncluirLogs,
    [string]$SenhaCriptografia = $env:BACKUP_ENCRYPTION_PASSPHRASE,
    [switch]$RemoverOriginalCriptografado,
    [string]$DestinoSecundario = $env:LOCAL_BACKUP_SECONDARY_DIR,
    [ValidateRange(1, 3650)]
    [int]$RetencaoSecundariaDias = 90,
    [switch]$ConfirmarDestinoSecundario,
    [string]$ServiceDirectory = "$env:ProgramData\DeigoVarejo\ServidorLocal",
    [string]$PgDumpPath = "",
    [switch]$ValidarSomente
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Manage = Join-Path $Root "manage.py"
$EvidenceCommand = Join-Path $Root "apps\fiscal\management\commands\verificar_integridade_evidencias_fiscais.py"
if (-not $Destino.Trim()) {
    $Destino = if ($env:LOCAL_BACKUP_DIR) { $env:LOCAL_BACKUP_DIR } else { Join-Path $env:ProgramData "DeigoVarejo\Backups" }
}
$DestinoPath = if ([IO.Path]::IsPathRooted($Destino)) { [IO.Path]::GetFullPath($Destino) } else { [IO.Path]::GetFullPath((Join-Path $Root $Destino)) }
$EvidenceLatest = Join-Path $DestinoPath "fiscal-evidence-anchor-latest.json"
$SecondaryConfirmedByEnvironment = [string]$env:LOCAL_BACKUP_SECONDARY_CONFIRMED -match "^(?i:1|true|yes|sim)$"
$SecondaryConfirmed = [bool]($ConfirmarDestinoSecundario -or $SecondaryConfirmedByEnvironment)
$DestinoSecundarioPath = ""
if ($DestinoSecundario.Trim()) {
    $DestinoSecundarioPath = if ([IO.Path]::IsPathRooted($DestinoSecundario)) { [IO.Path]::GetFullPath($DestinoSecundario) } else { [IO.Path]::GetFullPath((Join-Path $Root $DestinoSecundario)) }
    $PrimaryNormalized = $DestinoPath.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    $SecondaryNormalized = $DestinoSecundarioPath.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    $PrimaryPrefix = $PrimaryNormalized + [IO.Path]::DirectorySeparatorChar
    $SecondaryPrefix = $SecondaryNormalized + [IO.Path]::DirectorySeparatorChar
    if (
        $PrimaryNormalized.Equals($SecondaryNormalized, [StringComparison]::OrdinalIgnoreCase) -or
        $SecondaryNormalized.StartsWith($PrimaryPrefix, [StringComparison]::OrdinalIgnoreCase) -or
        $PrimaryNormalized.StartsWith($SecondaryPrefix, [StringComparison]::OrdinalIgnoreCase)
    ) {
        throw "O destino secundario deve ser separado da pasta principal de backup."
    }
    if (-not $SecondaryConfirmed) {
        throw "Confirme explicitamente que o destino secundario pertence a NAS, rede ou disco externo."
    }
    if (-not $SenhaCriptografia) {
        throw "A copia secundaria exige BACKUP_ENCRYPTION_PASSPHRASE; arquivos abertos nao sao enviados ao destino externo."
    }
}

$ServiceEnvironmentLoaded = $false
$ServiceXml = Join-Path $ServiceDirectory "DeigoVarejoServidorLocal.xml"
if (Test-Path -LiteralPath $ServiceXml -PathType Leaf) {
    try {
        [xml]$ServiceConfig = Get-Content -LiteralPath $ServiceXml -Raw -Encoding UTF8
        $AllowedNames = @("SQLITE_PATH", "MEDIA_ROOT", "STATIC_ROOT", "LOG_DIR")
        foreach ($item in $ServiceConfig.service.env) {
            $name = [string]$item.name
            if ($AllowedNames -contains $name -and [string]$item.value) {
                [Environment]::SetEnvironmentVariable($name, [string]$item.value, "Process")
            }
        }
        $ServiceEnvironmentLoaded = $true
    } catch {
        throw "Configuracao do servico local invalida em $ServiceXml`: $($_.Exception.Message)"
    }
}
foreach ($required in @($Python, $Manage, $EvidenceCommand)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Arquivo obrigatorio nao encontrado: $required"
    }
}

Set-Location $Root
$RuntimeCode = "import json, os, django; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); django.setup(); from django.conf import settings; db=settings.DATABASES['default']; print(json.dumps({'db_engine': str(db.get('ENGINE') or ''), 'db_name': str(db.get('NAME') or ''), 'db_user': str(db.get('USER') or ''), 'db_password': str(db.get('PASSWORD') or ''), 'db_host': str(db.get('HOST') or ''), 'db_port': str(db.get('PORT') or ''), 'pg_dump_path': str(os.getenv('POSTGRES_PG_DUMP_PATH') or ''), 'media_root': str(settings.MEDIA_ROOT), 'log_dir': str(settings.LOG_DIR)}))"
$RuntimeJson = & $Python -c $RuntimeCode
if ($LASTEXITCODE -ne 0 -or -not $RuntimeJson) {
    throw "Nao foi possivel descobrir as fontes de dados pela configuracao do Django."
}
try {
    $Runtime = $RuntimeJson | ConvertFrom-Json
} catch {
    throw "Diagnostico das fontes de backup invalido: $($_.Exception.Message)"
}

$IsSqlite = [string]$Runtime.db_engine -match "sqlite3$"
$IsPostgres = [string]$Runtime.db_engine -match "postgresql$"
if (-not $IsSqlite -and -not $IsPostgres) { throw "Banco nao suportado pelo backup local: $($Runtime.db_engine)" }
$PgDump = ""
$PgDumpVersion = ""
if ($IsPostgres) {
    $PgDumpCommand = if ($PgDumpPath) { $PgDumpPath } elseif ([string]$Runtime.pg_dump_path) { [string]$Runtime.pg_dump_path } elseif ($env:POSTGRES_PG_DUMP_PATH) { $env:POSTGRES_PG_DUMP_PATH } else { "pg_dump" }
    $PgDumpInfo = Get-Command $PgDumpCommand -ErrorAction SilentlyContinue
    if (-not $PgDumpInfo) { throw "pg_dump nao encontrado. Instale as ferramentas cliente do PostgreSQL ou configure POSTGRES_PG_DUMP_PATH." }
    $PgDump = $PgDumpInfo.Source
    $PgDumpVersion = (& $PgDump --version | Select-Object -First 1)
}
$Sqlite = if ($IsSqlite -and $Runtime.db_name) { [IO.Path]::GetFullPath([string]$Runtime.db_name) } else { "" }
$Media = if ($Runtime.media_root) { [IO.Path]::GetFullPath([string]$Runtime.media_root) } else { "" }
$Logs = if ($Runtime.log_dir) { [IO.Path]::GetFullPath([string]$Runtime.log_dir) } else { "" }
$Sources = [ordered]@{
    contrato = "local_backup_sources_v1"
    banco_engine = [string]$Runtime.db_engine
    sqlite = $Sqlite
    postgresql = $IsPostgres
    postgresql_banco = if ($IsPostgres) { [string]$Runtime.db_name } else { "" }
    postgresql_host = if ($IsPostgres) { [string]$Runtime.db_host } else { "" }
    postgresql_porta = if ($IsPostgres) { [string]$Runtime.db_port } else { "" }
    pg_dump_encontrado = [bool]$PgDump
    pg_dump_versao = [string]$PgDumpVersion
    sqlite_encontrado = [bool]($Sqlite -and (Test-Path -LiteralPath $Sqlite -PathType Leaf))
    media = $Media
    media_encontrada = [bool]($Media -and (Test-Path -LiteralPath $Media -PathType Container))
    logs = $Logs
    logs_encontrados = [bool]($Logs -and (Test-Path -LiteralPath $Logs -PathType Container))
    destino = $DestinoPath
    criptografia_configurada = [bool]$SenhaCriptografia
    copia_secundaria_configurada = [bool]$DestinoSecundarioPath
    copia_secundaria_destino = $DestinoSecundarioPath
    copia_secundaria_confirmada_externa = $SecondaryConfirmed
    copia_secundaria_somente_criptografada = $true
    copia_secundaria_retencao_dias = $RetencaoSecundariaDias
    configuracao_origem = if ($ServiceEnvironmentLoaded) { "winsw_service_xml" } else { "processo_ou_env_local" }
    servico_xml = $ServiceXml
    evidencia_fiscal_comando = $EvidenceCommand
    evidencia_fiscal_comando_encontrado = [bool](Test-Path -LiteralPath $EvidenceCommand -PathType Leaf)
    evidencia_fiscal_ancora_externa = $EvidenceLatest
    evidencia_fiscal_ancora_externa_encontrada = [bool](Test-Path -LiteralPath $EvidenceLatest -PathType Leaf)
}
$EvidenceValidationArgs = @("verificar_integridade_evidencias_fiscais", "--estrito", "--registrar-alerta", "--origem", "backup")
if (Test-Path -LiteralPath $EvidenceLatest -PathType Leaf) {
    $EvidenceValidationArgs += @("--comparar-arquivo", $EvidenceLatest)
}
$EvidenceValidationOutput = & $Python $Manage @EvidenceValidationArgs
if ($LASTEXITCODE -ne 0 -or -not $EvidenceValidationOutput) {
    throw "A cadeia de evidencias fiscais possui divergencia ou nao pode ser verificada."
}
try {
    $EvidenceValidation = $EvidenceValidationOutput | ConvertFrom-Json
} catch {
    throw "O verificador de evidencias fiscais nao retornou JSON valido."
}
if ($EvidenceValidation.contrato -ne "fiscal_evidence_anchor_v1" -or -not $EvidenceValidation.integra) {
    throw "O contrato de integridade das evidencias fiscais e invalido ou divergente."
}
$Sources.evidencias_fiscais_integras = $true
$Sources.evidencias_fiscais_total = [int]$EvidenceValidation.total_evidencias
$Sources.evidencias_fiscais_documentos = [int]$EvidenceValidation.total_documentos
if ($ValidarSomente) {
    $Sources | ConvertTo-Json -Depth 4
    exit 0
}

New-Item -ItemType Directory -Force -Path $DestinoPath | Out-Null
$TempRoot = Join-Path $DestinoPath "_tmp"
$Agora = Get-Date -Format "yyyyMMdd-HHmmss"
$NomeBase = "supermercado-local-$Agora"
$Work = Join-Path $TempRoot $NomeBase
$Zip = Join-Path $DestinoPath "$NomeBase.zip"
$Sha = "$Zip.sha256"
$Encrypted = "$Zip.aes"
$EncryptedSha = "$Encrypted.sha256"
New-Item -ItemType Directory -Force -Path $Work | Out-Null

function Protect-BackupFile {
    param(
        [Parameter(Mandatory=$true)][string]$InputFile,
        [Parameter(Mandatory=$true)][string]$OutputFile,
        [Parameter(Mandatory=$true)][string]$Passphrase
    )
    $Salt = New-Object byte[] 16
    $Iv = New-Object byte[] 16
    $Rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $Rng.GetBytes($Salt)
        $Rng.GetBytes($Iv)
    } finally {
        $Rng.Dispose()
    }
    $Kdf = [Security.Cryptography.Rfc2898DeriveBytes]::new($Passphrase, $Salt, 200000, [Security.Cryptography.HashAlgorithmName]::SHA256)
    $Aes = [Security.Cryptography.Aes]::Create()
    $Aes.KeySize = 256
    $Aes.Mode = [Security.Cryptography.CipherMode]::CBC
    $Aes.Padding = [Security.Cryptography.PaddingMode]::PKCS7
    $Aes.Key = $Kdf.GetBytes(32)
    $Aes.IV = $Iv
    $Input = [IO.File]::OpenRead($InputFile)
    $Output = [IO.File]::Create($OutputFile)
    try {
        $Header = [Text.Encoding]::ASCII.GetBytes("MFLOWAES1")
        $Output.Write($Header, 0, $Header.Length)
        $Output.Write($Salt, 0, $Salt.Length)
        $Output.Write($Iv, 0, $Iv.Length)
        $Crypto = [Security.Cryptography.CryptoStream]::new($Output, $Aes.CreateEncryptor(), [Security.Cryptography.CryptoStreamMode]::Write)
        try {
            $Input.CopyTo($Crypto)
            $Crypto.FlushFinalBlock()
        } finally {
            $Crypto.Dispose()
        }
    } finally {
        $Input.Dispose()
        $Output.Dispose()
        $Aes.Dispose()
        $Kdf.Dispose()
    }
}

function Copy-VerifiedEncryptedBackup {
    param(
        [Parameter(Mandatory=$true)][string]$SourceFile,
        [Parameter(Mandatory=$true)][string]$DestinationDirectory,
        [Parameter(Mandatory=$true)][string]$ExpectedHash
    )
    New-Item -ItemType Directory -Force -Path $DestinationDirectory | Out-Null
    $FileName = [IO.Path]::GetFileName($SourceFile)
    $FinalFile = Join-Path $DestinationDirectory $FileName
    $FinalHashFile = "$FinalFile.sha256"
    if (Test-Path -LiteralPath $FinalFile -PathType Leaf) {
        throw "O arquivo secundario ja existe e nao sera sobrescrito: $FinalFile"
    }
    $Token = [Guid]::NewGuid().ToString("N")
    $PartialFile = Join-Path $DestinationDirectory ".$FileName.$Token.partial"
    $PartialHashFile = "$PartialFile.sha256"
    $Promoted = $false
    $FinalFileMoved = $false
    $FinalHashMoved = $false
    try {
        Copy-Item -LiteralPath $SourceFile -Destination $PartialFile
        $CopiedHash = (Get-FileHash -LiteralPath $PartialFile -Algorithm SHA256).Hash
        if (-not $CopiedHash.Equals($ExpectedHash, [StringComparison]::OrdinalIgnoreCase)) {
            throw "A copia secundaria falhou na verificacao SHA-256."
        }
        [IO.File]::WriteAllText(
            $PartialHashFile,
            "$CopiedHash  $FileName`n",
            [Text.Encoding]::ASCII
        )
        Move-Item -LiteralPath $PartialFile -Destination $FinalFile
        $FinalFileMoved = $true
        Move-Item -LiteralPath $PartialHashFile -Destination $FinalHashFile
        $FinalHashMoved = $true
        $Promoted = $true
        return [pscustomobject]@{
            arquivo = $FinalFile
            sha256 = $CopiedHash
            checksum = $FinalHashFile
        }
    } finally {
        foreach ($TemporaryFile in @($PartialFile, $PartialHashFile)) {
            if (Test-Path -LiteralPath $TemporaryFile -PathType Leaf) {
                Remove-Item -LiteralPath $TemporaryFile -Force
            }
        }
        if (-not $Promoted) {
            if ($FinalFileMoved -and (Test-Path -LiteralPath $FinalFile -PathType Leaf)) {
                Remove-Item -LiteralPath $FinalFile -Force
            }
            if ($FinalHashMoved -and (Test-Path -LiteralPath $FinalHashFile -PathType Leaf)) {
                Remove-Item -LiteralPath $FinalHashFile -Force
            }
        }
    }
}

$SecondaryCopy = $null
$BackupExecutionId = [Guid]::NewGuid().ToString("N")
$BackupStage = "integridade_fiscal"
$BackupHashValidated = $false
function Register-BackupOperationalResult {
    param(
        [Parameter(Mandatory=$true)][ValidateSet("sucesso", "falha")][string]$Status,
        [Parameter(Mandatory=$true)][string]$Stage,
        [string]$FailureCode = "erro_operacional"
    )
    $HistoryArgs = @(
        "registrar_resultado_backup_operacional",
        "--execucao-id", $BackupExecutionId,
        "--status", $Status,
        "--etapa", $Stage,
        "--codigo-falha", $FailureCode
    )
    if ($SenhaCriptografia) { $HistoryArgs += "--criptografado" }
    if ($DestinoSecundarioPath) { $HistoryArgs += "--copia-secundaria" }
    if ($BackupHashValidated) { $HistoryArgs += "--hash-validado" }
    try {
        & $Python $Manage @HistoryArgs 2>$null | Out-Null
    } catch {
        # O histórico é auxiliar e nunca deve esconder o resultado real do backup.
    }
}

try {
    try {
        $EvidenceAnchor = Join-Path $Work "fiscal-evidence-anchor.json"
    & $Python $Manage verificar_integridade_evidencias_fiscais --estrito --registrar-alerta --origem backup --arquivo $EvidenceLatest | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $EvidenceLatest -PathType Leaf)) {
        throw "Falha ao validar ou promover a ancora externa das evidencias fiscais."
    }
    Copy-Item -LiteralPath $EvidenceLatest -Destination $EvidenceAnchor -Force
    $EvidenceAnchorHash = (Get-FileHash -LiteralPath $EvidenceAnchor -Algorithm SHA256).Hash

    $BackupStage = "geracao"
    & $Python $Manage dumpdata --exclude auth.permission --exclude contenttypes --indent 2 --output (Join-Path $Work "dados.json")
    if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o backup logico do Django." }

    if ($Sources.sqlite_encontrado) {
        $SqliteSnapshot = Join-Path $Work "db.sqlite3"
        $SqliteBackupCode = 'import sqlite3, sys; source=sqlite3.connect(sys.argv[1], timeout=30); target=sqlite3.connect(sys.argv[2]); source.backup(target); target.close(); source.close()'
        & $Python -c $SqliteBackupCode $Sqlite $SqliteSnapshot
        if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar snapshot consistente do SQLite." }
    }
    if ($IsPostgres) {
        $PgDumpFile = Join-Path $Work "database.dump"
        $PgDumpArgs = @("--format=custom", "--no-owner", "--no-acl", "--file=$PgDumpFile")
        if ([string]$Runtime.db_host) { $PgDumpArgs += "--host=$($Runtime.db_host)" }
        if ([string]$Runtime.db_port) { $PgDumpArgs += "--port=$($Runtime.db_port)" }
        if ([string]$Runtime.db_user) { $PgDumpArgs += "--username=$($Runtime.db_user)" }
        $PgDumpArgs += [string]$Runtime.db_name
        $PreviousPgPassword = $env:PGPASSWORD
        try {
            if ([string]$Runtime.db_password) { $env:PGPASSWORD = [string]$Runtime.db_password }
            & $PgDump @PgDumpArgs
            if ($LASTEXITCODE -ne 0) { throw "pg_dump falhou ao gerar o backup PostgreSQL." }
        } finally {
            $env:PGPASSWORD = $PreviousPgPassword
        }
    }
    if ($Sources.media_encontrada) {
        Copy-Item -LiteralPath $Media -Destination (Join-Path $Work "media") -Recurse -Force
    }
    if ($IncluirLogs -and $Sources.logs_encontrados) {
        Copy-Item -LiteralPath $Logs -Destination (Join-Path $Work "logs") -Recurse -Force
    }
    foreach ($file in @(".env.example", "README.md")) {
        $path = Join-Path $Root $file
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            Copy-Item -LiteralPath $path -Destination (Join-Path $Work $file) -Force
        }
    }

    $Manifesto = [ordered]@{
        contrato = "erp_local_backup_v2"
        gerado_em = (Get-Date).ToUniversalTime().ToString("o")
        fontes = $Sources
        inclui_dados_json = $true
        banco_tipo = if ($IsPostgres) { "postgresql" } else { "sqlite" }
        inclui_sqlite = [bool]$Sources.sqlite_encontrado
        inclui_postgresql = [bool]$IsPostgres
        postgresql_dump_formato = if ($IsPostgres) { "custom" } else { "" }
        postgresql_pg_dump_versao = if ($IsPostgres) { [string]$PgDumpVersion } else { "" }
        sqlite_snapshot_consistente = [bool]$Sources.sqlite_encontrado
        inclui_media = [bool]$Sources.media_encontrada
        inclui_logs = [bool]($IncluirLogs -and $Sources.logs_encontrados)
        inclui_ancora_evidencias_fiscais = $true
        evidencias_fiscais_contrato = "fiscal_evidence_anchor_v1"
        evidencias_fiscais_arquivo = "fiscal-evidence-anchor.json"
        evidencias_fiscais_sha256 = $EvidenceAnchorHash
        observacao = "Restaure primeiro em ambiente separado e valide o healthcheck antes de promover."
    }
    [IO.File]::WriteAllText((Join-Path $Work "manifesto.json"), ($Manifesto | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))

    $EmptyArchiveDirectories = @()
    foreach ($relativeDirectory in @("media", "logs")) {
        $directoryPath = Join-Path $Work $relativeDirectory
        if (
            (Test-Path -LiteralPath $directoryPath -PathType Container) -and
            -not (Get-ChildItem -LiteralPath $directoryPath -Force | Select-Object -First 1)
        ) {
            $EmptyArchiveDirectories += "$relativeDirectory/"
        }
    }
    Compress-Archive -Path (Join-Path $Work "*") -DestinationPath $Zip -Force
    if ($EmptyArchiveDirectories) {
        $ArchiveUpdate = [IO.Compression.ZipFile]::Open($Zip, [IO.Compression.ZipArchiveMode]::Update)
        try {
            foreach ($entryName in $EmptyArchiveDirectories) {
                if (-not $ArchiveUpdate.GetEntry($entryName)) {
                    [void]$ArchiveUpdate.CreateEntry($entryName)
                }
            }
        } finally {
            $ArchiveUpdate.Dispose()
        }
    }
    $Hash = Get-FileHash -LiteralPath $Zip -Algorithm SHA256
    [IO.File]::WriteAllText($Sha, "$($Hash.Hash)  $([IO.Path]::GetFileName($Zip))`n", [Text.Encoding]::ASCII)
    $BackupHashValidated = $true

    if ($SenhaCriptografia) {
        $BackupStage = "criptografia"
        Protect-BackupFile -InputFile $Zip -OutputFile $Encrypted -Passphrase $SenhaCriptografia
        $EncryptedHash = Get-FileHash -LiteralPath $Encrypted -Algorithm SHA256
        [IO.File]::WriteAllText($EncryptedSha, "$($EncryptedHash.Hash)  $([IO.Path]::GetFileName($Encrypted))`n", [Text.Encoding]::ASCII)
        $BackupHashValidated = $true
        if ($RemoverOriginalCriptografado) {
            Remove-Item -LiteralPath $Zip, $Sha -Force
        }
    }
    if ($DestinoSecundarioPath) {
        $BackupStage = "copia_secundaria"
        if (-not $SenhaCriptografia -or -not (Test-Path -LiteralPath $Encrypted -PathType Leaf)) {
            throw "A copia secundaria exige um pacote criptografado valido."
        }
        $SecondaryCopy = Copy-VerifiedEncryptedBackup `
            -SourceFile $Encrypted `
            -DestinationDirectory $DestinoSecundarioPath `
            -ExpectedHash $EncryptedHash.Hash
    }
    } finally {
        if (Test-Path -LiteralPath $Work) {
            Remove-Item -LiteralPath $Work -Recurse -Force
        }
    }

    $BackupStage = "retencao"
    Get-ChildItem -LiteralPath $DestinoPath -File -Filter "supermercado-local-*.zip*" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$RetencaoDias) } |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
    if ($DestinoSecundarioPath -and (Test-Path -LiteralPath $DestinoSecundarioPath -PathType Container)) {
        Get-ChildItem -LiteralPath $DestinoSecundarioPath -File -Filter "supermercado-local-*.zip.aes*" |
            Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$RetencaoSecundariaDias) } |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
    }
} catch {
    $FailureCode = switch ($BackupStage) {
        "integridade_fiscal" { "integridade_fiscal" }
        "geracao" { "geracao_pacote" }
        "criptografia" { "criptografia" }
        "copia_secundaria" { "copia_secundaria" }
        "retencao" { "retencao" }
        default { "erro_operacional" }
    }
    Register-BackupOperationalResult -Status "falha" -Stage $BackupStage -FailureCode $FailureCode
    throw
}
$BackupStage = "concluido"
Register-BackupOperationalResult -Status "sucesso" -Stage $BackupStage

Write-Host "Backup concluido em: $DestinoPath"
Write-Host "Contrato: erp_local_backup_v2"
if ($SenhaCriptografia) {
    Write-Host "Arquivo criptografado: $Encrypted"
    Write-Host "SHA-256 criptografado: $($EncryptedHash.Hash)"
    if ($SecondaryCopy) {
        Write-Host "Copia secundaria verificada: $($SecondaryCopy.arquivo)"
        Write-Host "SHA-256 secundario: $($SecondaryCopy.sha256)"
    }
} else {
    Write-Host "Arquivo: $Zip"
    Write-Host "SHA-256: $($Hash.Hash)"
}