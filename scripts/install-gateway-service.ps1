param(
    [string]$ServiceName = "mt5-gateway",
    [string]$DisplayName = "mt5-gateway",
    [string]$Description = "Private MetaTrader5 gateway for quotes and preview orders",
    [string]$NssmPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "mt5-gateway-common.ps1")

function Resolve-NssmPath {
    param([string]$RequestedPath)

    if ($RequestedPath -and (Test-Path $RequestedPath)) {
        return (Resolve-Path $RequestedPath).Path
    }

    $candidates = @(
        "C:\Program Files\nssm\win64\nssm.exe",
        "C:\Program Files\nssm\win32\nssm.exe",
        "C:\Program Files\NSSM\win64\nssm.exe",
        "C:\Program Files\NSSM\win32\nssm.exe",
        "C:\nssm\win64\nssm.exe",
        "C:\nssm\win32\nssm.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return (Resolve-Path $candidate).Path
        }
    }

    throw "NSSM não encontrado. Instale o NSSM e informe o caminho com -NssmPath."
}

$config = Get-GatewayConfig
$nssm = Resolve-NssmPath -RequestedPath $NssmPath

& $nssm install $ServiceName $config.Python "-m" "uvicorn" "api_metatrader5.app:create_app" "--factory" "--app-dir" "src" "--host" $config.Host "--port" "$($config.Port)"
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar o serviço no NSSM." }

& $nssm set $ServiceName DisplayName $DisplayName
& $nssm set $ServiceName Description $Description
& $nssm set $ServiceName AppDirectory $config.Root
& $nssm set $ServiceName AppStdout $config.StdoutLog
& $nssm set $ServiceName AppStderr $config.StderrLog
& $nssm set $ServiceName AppRotateFiles 1
& $nssm set $ServiceName AppRotateOnline 1
& $nssm set $ServiceName AppRotateBytes 10485760
& $nssm set $ServiceName Start SERVICE_AUTO_START
& $nssm set $ServiceName AppExit Default Restart
& $nssm set $ServiceName AppRestartDelay 5000

Start-Service -Name $ServiceName
Start-Sleep -Seconds 5

$health = Test-GatewayHealth
if (-not $health.Ok) {
    throw "Serviço instalado, mas o health check falhou: $($health.Error)"
}

Write-Output ("Serviço instalado e iniciado com sucesso. Name={0} URL={1}" -f $ServiceName, $config.BaseUrl)
