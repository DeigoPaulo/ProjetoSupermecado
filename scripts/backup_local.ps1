param(
    [string]$Destino = "",
    [ValidateRange(1, 3650)]
    [int]$RetencaoDias = 30,
    [switch]$IncluirLogs,
    [string]$SenhaCriptografia = $env:BACKUP_ENCRYPTION_PASSPHRASE,
    [switch]$RemoverOriginalCriptografado,
    [string]$ServiceDirectory = "$env:ProgramData\DeigoVarejo\ServidorLocal",
    [string]$PgDumpPath = "",
    [switch]$ValidarSomente
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Manage = Join-Path $Root "manage.py"
if (-not $Destino.Trim()) {
    $Destino = if ($env:LOCAL_BACKUP_DIR) { $env:LOCAL_BACKUP_DIR } else { Join-Path $env:ProgramData "DeigoVarejo\Backups" }
}
$DestinoPath = if ([IO.Path]::IsPathRooted($Destino)) { [IO.Path]::GetFullPath($Destino) } else { [IO.Path]::GetFullPath((Join-Path $Root $Destino)) }

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
foreach ($required in @($Python, $Manage)) {
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
    configuracao_origem = if ($ServiceEnvironmentLoaded) { "winsw_service_xml" } else { "processo_ou_env_local" }
    servico_xml = $ServiceXml
}
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

try {
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
        observacao = "Restaure primeiro em ambiente separado e valide o healthcheck antes de promover."
    }
    [IO.File]::WriteAllText((Join-Path $Work "manifesto.json"), ($Manifesto | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))

    Compress-Archive -Path (Join-Path $Work "*") -DestinationPath $Zip -Force
    $Hash = Get-FileHash -LiteralPath $Zip -Algorithm SHA256
    [IO.File]::WriteAllText($Sha, "$($Hash.Hash)  $([IO.Path]::GetFileName($Zip))`n", [Text.Encoding]::ASCII)

    if ($SenhaCriptografia) {
        Protect-BackupFile -InputFile $Zip -OutputFile $Encrypted -Passphrase $SenhaCriptografia
        $EncryptedHash = Get-FileHash -LiteralPath $Encrypted -Algorithm SHA256
        [IO.File]::WriteAllText($EncryptedSha, "$($EncryptedHash.Hash)  $([IO.Path]::GetFileName($Encrypted))`n", [Text.Encoding]::ASCII)
        if ($RemoverOriginalCriptografado) {
            Remove-Item -LiteralPath $Zip, $Sha -Force
        }
    }
} finally {
    if (Test-Path -LiteralPath $Work) {
        Remove-Item -LiteralPath $Work -Recurse -Force
    }
}

Get-ChildItem -LiteralPath $DestinoPath -File -Filter "supermercado-local-*.zip*" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$RetencaoDias) } |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }

Write-Host "Backup concluido em: $DestinoPath"
Write-Host "Contrato: erp_local_backup_v2"
if ($SenhaCriptografia) {
    Write-Host "Arquivo criptografado: $Encrypted"
    Write-Host "SHA-256 criptografado: $($EncryptedHash.Hash)"
} else {
    Write-Host "Arquivo: $Zip"
    Write-Host "SHA-256: $($Hash.Hash)"
}