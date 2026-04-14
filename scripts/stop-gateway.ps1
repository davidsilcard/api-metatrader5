. (Join-Path $PSScriptRoot "mt5-gateway-common.ps1")

$config = Get-GatewayConfig
$existing = Get-RunningGatewayProcess
if (-not $existing) {
    Write-Output "Gateway não está em execução."
    if (Test-Path $config.PidFile) {
        Remove-Item -LiteralPath $config.PidFile -Force
    }
    exit 0
}

Stop-Process -Id $existing.Id -Force
Start-Sleep -Seconds 2

if (Test-Path $config.PidFile) {
    Remove-Item -LiteralPath $config.PidFile -Force
}

Write-Output ("Gateway parado. PID={0}" -f $existing.Id)
