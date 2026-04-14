. (Join-Path $PSScriptRoot "mt5-gateway-common.ps1")

$config = Get-GatewayConfig
$existing = Get-RunningGatewayProcess
$health = Test-GatewayHealth -TimeoutSeconds 10
$tailscaleIp = Get-TailscaleIpv4

Write-Output ("URL={0}" -f $config.BaseUrl)
Write-Output ("TAILSCALE_IP={0}" -f ($(if ($tailscaleIp) { $tailscaleIp } else { "indisponível" })))

if ($existing) {
    Write-Output ("PROCESS=running PID={0}" -f $existing.Id)
} elseif ($health.Ok) {
    Write-Output "PROCESS=running-external"
} else {
    Write-Output "PROCESS=stopped"
}

if ($health.Ok) {
    Write-Output ("HEALTH=ok STATUS={0}" -f $health.Body.status)
} else {
    Write-Output ("HEALTH=failed ERROR={0}" -f $health.Error)
}
