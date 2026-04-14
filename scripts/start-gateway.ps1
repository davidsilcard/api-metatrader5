. (Join-Path $PSScriptRoot "mt5-gateway-common.ps1")

$config = Get-GatewayConfig
$existing = Get-RunningGatewayProcess
$health = Test-GatewayHealth
if ($existing) {
    Write-Output ("Gateway já está em execução. PID={0} URL={1}" -f $existing.Id, $config.BaseUrl)
    exit 0
}
if ($health.Ok) {
    Write-Output ("Gateway já está respondendo em {0}. Processo atual não está sob controle do PID file." -f $config.BaseUrl)
    exit 0
}

if (Test-Path $config.StdoutLog) { Remove-Item -LiteralPath $config.StdoutLog -Force }
if (Test-Path $config.StderrLog) { Remove-Item -LiteralPath $config.StderrLog -Force }

$process = Start-Process `
    -FilePath $config.Python `
    -ArgumentList "-m", "uvicorn", "api_metatrader5.app:create_app", "--factory", "--app-dir", "src", "--host", $config.Host, "--port", "$($config.Port)" `
    -WorkingDirectory $config.Root `
    -RedirectStandardOutput $config.StdoutLog `
    -RedirectStandardError $config.StderrLog `
    -PassThru

Set-Content -Path $config.PidFile -Value $process.Id
Start-Sleep -Seconds 4

$health = Test-GatewayHealth
if (-not $health.Ok) {
    Write-Output ("Gateway iniciou mas o health check falhou em {0}: {1}" -f $config.BaseUrl, $health.Error)
    exit 1
}

Write-Output ("Gateway iniciado. PID={0} URL={1}" -f $process.Id, $config.BaseUrl)
