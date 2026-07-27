param(
    [string]$ServiceName = "MercaFlowServidorLocal",
    [string]$HealthUrl = "http://127.0.0.1:8000/login/"
)

$ErrorActionPreference = "Stop"
$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
$health = "indisponivel"
$statusCode = $null

if ($service -and $service.Status -eq "Running") {
    try {
        $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 5
        $statusCode = $response.StatusCode
        if ($statusCode -ge 200 -and $statusCode -lt 400) {
            $health = "saudavel"
        } else {
            $health = "resposta_invalida"
        }
    } catch {
        $health = "sem_resposta"
    }
}

$result = [ordered]@{
    contrato = "local_server_service_diagnostic_v1"
    servico = $ServiceName
    instalado = [bool]$service
    status = if ($service) { $service.Status.ToString() } else { "Nao instalado" }
    health_url = $HealthUrl
    health = $health
    http_status = $statusCode
    verificado_em = (Get-Date).ToString("o")
}

$result | ConvertTo-Json
if (-not $service -or $service.Status -ne "Running" -or $health -ne "saudavel") {
    exit 1
}