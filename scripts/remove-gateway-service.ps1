param(
    [string]$ServiceName = "mt5-gateway",
    [string]$NssmPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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

    throw "NSSM não encontrado. Informe o caminho com -NssmPath."
}

$nssm = Resolve-NssmPath -RequestedPath $NssmPath
$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $service) {
    Write-Output ("Serviço {0} não existe." -f $ServiceName)
    exit 0
}

if ($service.Status -ne "Stopped") {
    Stop-Service -Name $ServiceName -Force
    Start-Sleep -Seconds 3
}

& $nssm remove $ServiceName confirm
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao remover o serviço."
}

Write-Output ("Serviço removido com sucesso. Name={0}" -f $ServiceName)
