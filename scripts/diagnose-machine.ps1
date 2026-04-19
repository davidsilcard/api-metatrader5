Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$processes = Get-Process | Select-Object `
    ProcessName,
    Id,
    CPU,
    WS,
    PM,
    @{ Name = "CPUSeconds"; Expression = {
        $cpu = $_.CPU
        if ($null -eq $cpu) { return 0 }
        if ($cpu -is [timespan]) { return $cpu.TotalSeconds }
        return [double]$cpu
    } }

$topCpu = $processes |
    Sort-Object CPUSeconds -Descending |
    Select-Object -First 8 ProcessName, Id, CPU, WS, PM, CPUSeconds

$topMemory = $processes |
    Sort-Object WS -Descending |
    Select-Object -First 8 ProcessName, Id, CPU, WS, PM, CPUSeconds

$os = $null
$computer = $null
$cpu = $null
$netAdapters = @()

try {
    $os = Get-CimInstance Win32_OperatingSystem
} catch {
}

try {
    $computer = Get-CimInstance Win32_ComputerSystem
} catch {
}

try {
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1 LoadPercentage, Name, NumberOfCores, NumberOfLogicalProcessors
} catch {
}

try {
    $netAdapters = Get-NetAdapter | Where-Object { $_.Status -eq "Up" } | Select-Object Name, InterfaceDescription, LinkSpeed
} catch {
}

$result = [ordered]@{
    computer_name = $env:COMPUTERNAME
    uptime_last_boot = if ($os) { $os.LastBootUpTime } else { $null }
    memory = @{
        total_physical_mb = if ($computer) { [math]::Round($computer.TotalPhysicalMemory / 1MB, 2) } else { $null }
        free_physical_mb = if ($os) { [math]::Round($os.FreePhysicalMemory / 1024, 2) } else { $null }
        free_virtual_mb = if ($os) { [math]::Round($os.FreeVirtualMemory / 1024, 2) } else { $null }
    }
    cpu = @{
        load_percent = if ($cpu) { $cpu.LoadPercentage } else { $null }
        name = if ($cpu) { $cpu.Name } else { $null }
        cores = if ($cpu) { $cpu.NumberOfCores } else { $null }
        logical_processors = if ($cpu) { $cpu.NumberOfLogicalProcessors } else { $null }
    }
    top_processes_cpu = $topCpu
    top_processes_memory = $topMemory
    active_network_adapters = $netAdapters
}

$result | ConvertTo-Json -Depth 6
