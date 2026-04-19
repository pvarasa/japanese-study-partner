# Stop dev servers
$root = $PSScriptRoot
$pidFile = "$root\.dev-pids.json"

$killed = 0

# Kill saved PIDs and their child processes
if (Test-Path $pidFile) {
    $pids = Get-Content $pidFile | ConvertFrom-Json
    foreach ($name in @("backend", "frontend")) {
        $procId = $pids.$name
        if ($procId) {
            Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $procId -or $_.ProcessId -eq $procId } | ForEach-Object {
                Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
                $killed++
            }
        }
    }
    Remove-Item $pidFile -Force
}

# Also kill anything on ports 8000/5173 as fallback
foreach ($port in @(8000, 5173)) {
    $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Where-Object State -eq Listen
    foreach ($conn in $conns) {
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        $killed++
    }
}

if ($killed -gt 0) {
    Write-Host "Stopped dev servers." -ForegroundColor Yellow
} else {
    Write-Host "No dev servers running." -ForegroundColor DarkGray
}
