. (Join-Path $PSScriptRoot "mt5-gateway-common.ps1")

& (Join-Path $PSScriptRoot "stop-gateway.ps1")
& (Join-Path $PSScriptRoot "start-gateway.ps1")
