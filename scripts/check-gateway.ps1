. (Join-Path $PSScriptRoot "mt5-gateway-common.ps1")

$config = Get-GatewayConfig

Write-Output ("GET {0}/health" -f $config.BaseUrl)
$health = Invoke-RestMethod ("{0}/health" -f $config.BaseUrl) -TimeoutSec 15
$health | ConvertTo-Json -Depth 6

Write-Output ("GET {0}/ready" -f $config.BaseUrl)
$ready = Invoke-RestMethod ("{0}/ready" -f $config.BaseUrl) -TimeoutSec 15
$ready | ConvertTo-Json -Depth 6

Write-Output "Quote unitário PETR4 deve ser validado com um cliente HMAC da aplicação consumidora ou script local assinado."
