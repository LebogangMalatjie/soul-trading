# Stops the Soul Trading backend (port 8000) and dashboard (port 3000).
# Finds the processes listening on those ports and stops them. Does NOT close
# any open broker positions - use the dashboard kill switch for that.
$ErrorActionPreference = 'SilentlyContinue'

$stopped = @()
foreach ($port in 8000, 3000) {
    $connections = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $pids) {
        try {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            $name = if ($proc) { $proc.ProcessName } else { "pid $procId" }
            $stopped += "port ${port}: stopped $name (pid $procId)"
        } catch {
            $stopped += "port ${port}: could not stop pid $procId"
        }
    }
}

if ($stopped.Count -eq 0) {
    Write-Host "Soul Trading is not running (nothing listening on 8000/3000)."
} else {
    Write-Host "Soul Trading stopped:"
    $stopped | ForEach-Object { Write-Host "  $_" }
}
