param(
    [string]$Destino = "backups",
    [int]$RetencaoDias = 30,
    [switch]$IncluirLogs,
    [string]$SenhaCriptografia = $env:BACKUP_ENCRYPTION_PASSPHRASE,
    [switch]$RemoverOriginalCriptografado
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Manage = Join-Path $Root "manage.py"
$DestinoPath = Join-Path $Root $Destino
$TempRoot = Join-Path $DestinoPath "_tmp"
$Agora = Get-Date -Format "yyyyMMdd-HHmmss"
$NomeBase = "supermercado-local-$Agora"
$Work = Join-Path $TempRoot $NomeBase
$Zip = Join-Path $DestinoPath "$NomeBase.zip"
$Sha = "$Zip.sha256"
$Encrypted = "$Zip.aes"
$EncryptedSha = "$Encrypted.sha256"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python do ambiente virtual nao encontrado em $Python."
}
if (-not (Test-Path -LiteralPath $Manage)) {
    throw "manage.py nao encontrado em $Manage."
}

New-Item -ItemType Directory -Force -Path $Work | Out-Null

Set-Location $Root

& $Python $Manage dumpdata --exclude auth.permission --exclude contenttypes --indent 2 --output (Join-Path $Work "dados.json")

$Sqlite = Join-Path $Root "db.sqlite3"
if (Test-Path -LiteralPath $Sqlite) {
    Copy-Item -LiteralPath $Sqlite -Destination (Join-Path $Work "db.sqlite3") -Force
}

$Media = Join-Path $Root "media"
if (Test-Path -LiteralPath $Media) {
    Copy-Item -LiteralPath $Media -Destination (Join-Path $Work "media") -Recurse -Force
}

foreach ($file in @(".env.example", "README.md")) {
    $path = Join-Path $Root $file
    if (Test-Path -LiteralPath $path) {
        Copy-Item -LiteralPath $path -Destination (Join-Path $Work $file) -Force
    }
}

if ($IncluirLogs) {
    $Logs = Join-Path $Root "logs"
    if (Test-Path -LiteralPath $Logs) {
        Copy-Item -LiteralPath $Logs -Destination (Join-Path $Work "logs") -Recurse -Force
    }
}

function Protect-BackupFile {
    param(
        [Parameter(Mandatory=$true)][string]$InputFile,
        [Parameter(Mandatory=$true)][string]$OutputFile,
        [Parameter(Mandatory=$true)][string]$Passphrase
    )
    $Salt = New-Object byte[] 16
    $Iv = New-Object byte[] 16
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($Salt)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($Iv)
    $Kdf = [System.Security.Cryptography.Rfc2898DeriveBytes]::new($Passphrase, $Salt, 200000, [System.Security.Cryptography.HashAlgorithmName]::SHA256)
    $Aes = [System.Security.Cryptography.Aes]::Create()
    $Aes.KeySize = 256
    $Aes.Mode = [System.Security.Cryptography.CipherMode]::CBC
    $Aes.Padding = [System.Security.Cryptography.PaddingMode]::PKCS7
    $Aes.Key = $Kdf.GetBytes(32)
    $Aes.IV = $Iv
    $Input = [System.IO.File]::OpenRead($InputFile)
    $Output = [System.IO.File]::Create($OutputFile)
    try {
        $Header = [System.Text.Encoding]::ASCII.GetBytes("MFLOWAES1")
        $Output.Write($Header, 0, $Header.Length)
        $Output.Write($Salt, 0, $Salt.Length)
        $Output.Write($Iv, 0, $Iv.Length)
        $Crypto = [System.Security.Cryptography.CryptoStream]::new($Output, $Aes.CreateEncryptor(), [System.Security.Cryptography.CryptoStreamMode]::Write)
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

$Manifesto = [ordered]@{
    gerado_em = (Get-Date).ToString("s")
    contrato = "erp_local_backup_v1"
    inclui_dados_json = $true
    inclui_sqlite = (Test-Path -LiteralPath $Sqlite)
    inclui_media = (Test-Path -LiteralPath $Media)
    inclui_logs = [bool]$IncluirLogs
    observacao = "Nao restaure em producao sem testar antes em ambiente separado."
}
$Manifesto | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $Work "manifesto.json") -Encoding UTF8

Compress-Archive -Path (Join-Path $Work "*") -DestinationPath $Zip -Force
$Hash = Get-FileHash -LiteralPath $Zip -Algorithm SHA256
"$($Hash.Hash)  $([System.IO.Path]::GetFileName($Zip))" | Set-Content -LiteralPath $Sha -Encoding ASCII

if ($SenhaCriptografia) {
    Protect-BackupFile -InputFile $Zip -OutputFile $Encrypted -Passphrase $SenhaCriptografia
    $EncryptedHash = Get-FileHash -LiteralPath $Encrypted -Algorithm SHA256
    "$($EncryptedHash.Hash)  $([System.IO.Path]::GetFileName($Encrypted))" | Set-Content -LiteralPath $EncryptedSha -Encoding ASCII
    if ($RemoverOriginalCriptografado) {
        Remove-Item -LiteralPath $Zip -Force
        Remove-Item -LiteralPath $Sha -Force
    }
}

Remove-Item -LiteralPath $Work -Recurse -Force

Get-ChildItem -LiteralPath $DestinoPath -Filter "supermercado-local-*.zip" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$RetencaoDias) } |
    ForEach-Object {
        $hashFile = "$($_.FullName).sha256"
        Remove-Item -LiteralPath $_.FullName -Force
        if (Test-Path -LiteralPath $hashFile) {
            Remove-Item -LiteralPath $hashFile -Force
        }
    }
Get-ChildItem -LiteralPath $DestinoPath -Filter "supermercado-local-*.zip.aes" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$RetencaoDias) } |
    ForEach-Object {
        $hashFile = "$($_.FullName).sha256"
        Remove-Item -LiteralPath $_.FullName -Force
        if (Test-Path -LiteralPath $hashFile) {
            Remove-Item -LiteralPath $hashFile -Force
        }
    }

Write-Host "Backup gerado: $Zip"
Write-Host "SHA-256: $($Hash.Hash)"
if ($SenhaCriptografia) {
    Write-Host "Backup criptografado: $Encrypted"
    Write-Host "SHA-256 criptografado: $($EncryptedHash.Hash)"
}
