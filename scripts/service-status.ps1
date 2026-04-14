param(
    [string]$ServiceName = "mt5-gateway"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $service) {
    Write-Output ("SERVICE=missing NAME={0}" -f $ServiceName)
    exit 0
}

Write-Output ("SERVICE=present NAME={0} STATUS={1}" -f $service.Name, $service.Status)
