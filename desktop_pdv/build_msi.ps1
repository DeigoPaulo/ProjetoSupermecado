param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version,
    [string]$Source,
    [string]$Output,
    [string]$WixCommand = "wix",
    [switch]$RequireSignedExecutable,
    [string]$CertificateThumbprint,
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Template = Join-Path $Root "installer\Product.wxs.template"
if (-not $Source) {
    $Source = Join-Path $Root "dist\SupermercadoPDV.exe"
}
if (-not $Output) {
    $Output = Join-Path $Root "dist\SupermercadoPDV-$Version-x64.msi"
}
$Source = [System.IO.Path]::GetFullPath($Source)
$Output = [System.IO.Path]::GetFullPath($Output)

if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
    throw "Executavel nao encontrado em $Source. Execute build_windows.ps1 primeiro."
}
if (-not (Test-Path -LiteralPath $Template -PathType Leaf)) {
    throw "Template WiX nao encontrado em $Template."
}

$ExecutableSignature = Get-AuthenticodeSignature -LiteralPath $Source
if ($RequireSignedExecutable -and $ExecutableSignature.Status -ne "Valid") {
    throw "O executavel precisa estar assinado antes do empacotamento de producao. Status: $($ExecutableSignature.Status)."
}

$Wix = Get-Command $WixCommand -ErrorAction SilentlyContinue
$WixExecutable = if ($Wix) { $Wix.Source } else { $null }
if (-not $WixExecutable -and $WixCommand -eq "wix") {
    $GlobalWix = Join-Path $env:USERPROFILE ".dotnet\tools\wix.exe"
    if (Test-Path -LiteralPath $GlobalWix -PathType Leaf) {
        $WixExecutable = $GlobalWix
    }
}
if (-not $WixExecutable) {
    throw "WiX Toolset v4 nao encontrado. Instale o .NET SDK e execute 'dotnet tool install --global wix --version 4.0.6'."
}

$BuildDir = Join-Path $Root "build\installer"
New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null
New-Item -ItemType Directory -Path (Split-Path -Parent $Output) -Force | Out-Null
$GeneratedWxs = Join-Path $BuildDir "Product.generated.wxs"
$EscapedSource = [System.Security.SecurityElement]::Escape($Source)
$Content = Get-Content -LiteralPath $Template -Raw
$Content = $Content.Replace("__VERSION__", $Version).Replace("__SOURCE__", $EscapedSource)
[System.IO.File]::WriteAllText($GeneratedWxs, $Content, [System.Text.UTF8Encoding]::new($false))

& $WixExecutable build $GeneratedWxs -arch x64 -o $Output
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Output -PathType Leaf)) {
    throw "Falha ao gerar o instalador MSI."
}

if ($CertificateThumbprint) {
    $SignTool = Get-Command "signtool.exe" -ErrorAction SilentlyContinue
    if (-not $SignTool) {
        throw "signtool.exe nao encontrado para assinar o MSI."
    }
    & $SignTool.Source sign /sha1 $CertificateThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $Output
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao assinar o instalador MSI."
    }
}

$MsiSignature = Get-AuthenticodeSignature -LiteralPath $Output
$File = Get-Item -LiteralPath $Output
$Metadata = [ordered]@{
    version = $Version
    filename = $File.Name
    size_bytes = $File.Length
    sha256 = (Get-FileHash -LiteralPath $Output -Algorithm SHA256).Hash.ToLowerInvariant()
    executable_signature = $ExecutableSignature.Status.ToString()
    msi_signature = $MsiSignature.Status.ToString()
    built_at_utc = [DateTime]::UtcNow.ToString("o")
}
$Metadata | ConvertTo-Json | Set-Content -LiteralPath "$Output.version.json" -Encoding UTF8

Write-Host "MSI gerado em $Output"
Write-Host "SHA-256: $($Metadata.sha256)"
Write-Host "Assinatura MSI: $($Metadata.msi_signature)"
