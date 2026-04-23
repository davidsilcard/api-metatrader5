param(
    [string[]]$Symbols = @("PETR4", "VALE3"),
    [string]$BaseUrl = "",
    [int]$Repeat = 1,
    [int]$DelaySeconds = 2,
    [int]$TimeoutSeconds = 120,
    [switch]$IncludeRaw,
    [switch]$SkipReady
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "mt5-gateway-common.ps1")

function ConvertTo-Hex {
    param([byte[]]$Bytes)
    return -join ($Bytes | ForEach-Object { $_.ToString("x2") })
}

function Get-Sha256Hex {
    param([string]$Text)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
        return ConvertTo-Hex -Bytes $sha.ComputeHash($bytes)
    } finally {
        $sha.Dispose()
    }
}

function Get-HmacSha256Hex {
    param(
        [string]$Secret,
        [string]$Message
    )
    $secretBytes = [System.Text.Encoding]::UTF8.GetBytes($Secret)
    $messageBytes = [System.Text.Encoding]::UTF8.GetBytes($Message)
    $hmac = [System.Security.Cryptography.HMACSHA256]::new($secretBytes)
    try {
        return ConvertTo-Hex -Bytes $hmac.ComputeHash($messageBytes)
    } finally {
        $hmac.Dispose()
    }
}

function Get-HmacCredential {
    $envMap = Get-EnvMap
    $keyId = if ($envMap.ContainsKey("MT5_GATEWAY_KEY_ID") -and $envMap["MT5_GATEWAY_KEY_ID"]) {
        $envMap["MT5_GATEWAY_KEY_ID"]
    } else {
        "edge-1"
    }

    if ($envMap.ContainsKey("HMAC_SHARED_KEYS") -and $envMap["HMAC_SHARED_KEYS"]) {
        $fallback = $null
        foreach ($chunk in $envMap["HMAC_SHARED_KEYS"].Split(",")) {
            $item = $chunk.Trim()
            if (-not $item -or -not $item.Contains("=")) {
                continue
            }
            $parts = $item.Split("=", 2)
            $candidateKeyId = $parts[0].Trim()
            $candidateSecret = $parts[1].Trim()
            if (-not $fallback) {
                $fallback = @{ KeyId = $candidateKeyId; Secret = $candidateSecret }
            }
            if ($candidateKeyId -eq $keyId) {
                return @{ KeyId = $candidateKeyId; Secret = $candidateSecret }
            }
        }
        if ($fallback) {
            return $fallback
        }
    }

    if ($envMap.ContainsKey("MT5_GATEWAY_SHARED_SECRET") -and $envMap["MT5_GATEWAY_SHARED_SECRET"]) {
        return @{ KeyId = $keyId; Secret = $envMap["MT5_GATEWAY_SHARED_SECRET"] }
    }

    throw "Configure HMAC_SHARED_KEYS ou MT5_GATEWAY_SHARED_SECRET no .env."
}

function Get-NormalizedSymbols {
    param([string[]]$Values)
    $items = New-Object System.Collections.Generic.List[string]
    foreach ($value in $Values) {
        foreach ($part in $value.Split(",")) {
            $symbol = $part.Trim().ToUpperInvariant()
            if ($symbol) {
                $items.Add($symbol)
            }
        }
    }
    return $items.ToArray()
}

function New-HmacHeaders {
    param(
        [hashtable]$Credential,
        [string]$Method,
        [string]$Path,
        [string]$Query,
        [string]$Body
    )
    $timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString()
    $nonce = [Guid]::NewGuid().ToString("N")
    $bodyHash = Get-Sha256Hex -Text $Body
    $canonical = @($Method.ToUpperInvariant(), $Path, $Query, $timestamp, $nonce, $bodyHash) -join "`n"
    $signature = Get-HmacSha256Hex -Secret $Credential.Secret -Message $canonical
    return @{
        "X-Key-Id" = $Credential.KeyId
        "X-Timestamp" = $timestamp
        "X-Nonce" = $nonce
        "X-Signature" = $signature
    }
}

function Invoke-ReadyProbe {
    param([string]$Url)
    try {
        $ready = Invoke-RestMethod ("{0}/ready" -f $Url) -TimeoutSec 15
        Write-Output ("READY status={0} provider={1} connected={2}" -f $ready.status, $ready.provider, $ready.connected)
    } catch {
        Write-Output ("READY failed error={0}" -f $_.Exception.Message)
    }
}

$config = Get-GatewayConfig
if (-not $BaseUrl) {
    $BaseUrl = $config.BaseUrl
}
$BaseUrl = $BaseUrl.TrimEnd("/")
$credential = Get-HmacCredential
$path = "/internal/v1/quotes/batch"
$normalizedSymbols = Get-NormalizedSymbols -Values $Symbols
if ($normalizedSymbols.Count -eq 0) {
    throw "Informe ao menos um ticker em -Symbols."
}

Write-Output ("BASE_URL={0}" -f $BaseUrl)
Write-Output ("SYMBOLS={0}" -f ($normalizedSymbols -join ","))
Write-Output ("REPEAT={0} DELAY_SECONDS={1} INCLUDE_RAW={2}" -f $Repeat, $DelaySeconds, [bool]$IncludeRaw)

if (-not $SkipReady) {
    Invoke-ReadyProbe -Url $BaseUrl
}

for ($iteration = 1; $iteration -le $Repeat; $iteration++) {
    $bodyObject = @{
        symbols = @($normalizedSymbols)
        include_raw = [bool]$IncludeRaw
    }
    $body = $bodyObject | ConvertTo-Json -Compress
    $headers = New-HmacHeaders -Credential $credential -Method "POST" -Path $path -Query "" -Body $body
    $started = Get-Date

    try {
        $response = Invoke-RestMethod `
            -Method Post `
            -Uri ("{0}{1}" -f $BaseUrl, $path) `
            -Headers $headers `
            -Body $body `
            -ContentType "application/json" `
            -TimeoutSec $TimeoutSeconds
        $elapsedMs = [int]((Get-Date) - $started).TotalMilliseconds
        Write-Output ("ITERATION={0} HTTP=200 total={1} success={2} error={3} partial={4} duration_ms={5}" -f $iteration, $response.count_total, $response.count_success, $response.count_error, $response.partial, $elapsedMs)

        foreach ($item in @($response.items)) {
            if ($item.ok) {
                Write-Output ("  OK  {0} last={1} bid={2} ask={3}" -f $item.requested_symbol, $item.quote.last, $item.quote.bid, $item.quote.ask)
            } else {
                Write-Output ("  ERR {0} code={1} message={2}" -f $item.requested_symbol, $item.error.code, $item.error.message)
            }
        }
    } catch {
        $elapsedMs = [int]((Get-Date) - $started).TotalMilliseconds
        Write-Output ("ITERATION={0} HTTP=failed duration_ms={1} error={2}" -f $iteration, $elapsedMs, $_.Exception.Message)
    }

    if ($iteration -lt $Repeat -and $DelaySeconds -gt 0) {
        Start-Sleep -Seconds $DelaySeconds
    }
}

if (-not $SkipReady) {
    Invoke-ReadyProbe -Url $BaseUrl
}
