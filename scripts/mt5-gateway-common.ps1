Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-ProjectRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-EnvMap {
    $root = Get-ProjectRoot
    $envPath = Join-Path $root ".env"
    if (-not (Test-Path $envPath)) {
        throw "Arquivo .env não encontrado em $envPath"
    }

    $map = @{}
    foreach ($line in Get-Content $envPath) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }
        $parts = $trimmed.Split("=", 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($value.Length -ge 2) {
            if (($value.StartsWith("'") -and $value.EndsWith("'")) -or ($value.StartsWith('"') -and $value.EndsWith('"'))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }
        $map[$key] = $value
    }
    return $map
}

function Get-GatewayConfig {
    $root = Get-ProjectRoot
    $envMap = Get-EnvMap
    $logsDir = Join-Path $root "logs"
    if (-not (Test-Path $logsDir)) {
        New-Item -ItemType Directory -Path $logsDir | Out-Null
    }

    $bindHost = if ($envMap.ContainsKey("APP_HOST") -and $envMap["APP_HOST"]) { $envMap["APP_HOST"] } else { "127.0.0.1" }
    $port = if ($envMap.ContainsKey("APP_PORT") -and $envMap["APP_PORT"]) { [int]$envMap["APP_PORT"] } else { 8000 }
    $python = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        throw "Python da virtualenv não encontrado em $python"
    }

    return @{
        Root = $root
        Host = $bindHost
        Port = $port
        BaseUrl = "http://{0}:{1}" -f $bindHost, $port
        Python = $python
        PidFile = Join-Path $logsDir "mt5-gateway.pid"
        StdoutLog = Join-Path $logsDir "mt5-gateway-stdout.log"
        StderrLog = Join-Path $logsDir "mt5-gateway-stderr.log"
        TailscaleCli = "C:\Program Files\Tailscale\tailscale.exe"
    }
}

function Get-RunningGatewayProcess {
    $config = Get-GatewayConfig
    if (-not (Test-Path $config.PidFile)) {
        return $null
    }
    $rawPid = (Get-Content $config.PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $rawPid) {
        return $null
    }
    try {
        $pid = [int]$rawPid
        return Get-Process -Id $pid -ErrorAction Stop
    } catch {
        return $null
    }
}

function Test-GatewayHealth {
    param(
        [int]$TimeoutSeconds = 15
    )
    $config = Get-GatewayConfig
    try {
        $response = Invoke-RestMethod ("{0}/health" -f $config.BaseUrl) -TimeoutSec $TimeoutSeconds
        return @{
            Ok = $true
            Body = $response
        }
    } catch {
        return @{
            Ok = $false
            Error = $_.Exception.Message
        }
    }
}

function Get-TailscaleIpv4 {
    $config = Get-GatewayConfig
    if (-not (Test-Path $config.TailscaleCli)) {
        return $null
    }
    try {
        $value = & $config.TailscaleCli ip -4 2>$null
        if ($LASTEXITCODE -ne 0) {
            return $null
        }
        return ($value | Select-Object -First 1)
    } catch {
        return $null
    }
}
