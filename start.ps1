# Start both backend and frontend for development
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# Find uv
$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    $uv = "$env:USERPROFILE\.local\bin\uv.exe"
    if (-not (Test-Path $uv)) {
        Write-Error "uv not found. Install from https://docs.astral.sh/uv/"
        exit 1
    }
} else {
    $uv = $uv.Source
}

# Kill any existing processes on our ports
& "$root\stop.ps1" 2>$null

Write-Host ""
Write-Host "Starting backend on :8000 ..." -ForegroundColor Cyan
$backend = Start-Process -PassThru -NoNewWindow -FilePath $uv `
    -ArgumentList "run", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000" `
    -WorkingDirectory "$root\backend"

Write-Host "Starting frontend on :5173 ..." -ForegroundColor Cyan
$npmCmd = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
if (-not $npmCmd) { $npmCmd = "npm.cmd" }
$frontend = Start-Process -PassThru -NoNewWindow -FilePath $npmCmd `
    -ArgumentList "run", "dev", "--", "--host", "0.0.0.0" `
    -WorkingDirectory "$root\frontend"

# Save PIDs for stop script
@{
    backend = $backend.Id
    frontend = $frontend.Id
} | ConvertTo-Json | Set-Content "$root\.dev-pids.json"

Write-Host ""
Write-Host "  Backend:  http://localhost:8000" -ForegroundColor Green
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor Green
Write-Host ""
Write-Host "  Press Ctrl+C to stop both servers" -ForegroundColor DarkGray
Write-Host ""

# Keep the script in the foreground so Ctrl+C reaches us, then kill the full
# process trees on exit. taskkill /T is required because uvicorn --reload and
# npm -> node spawn grandchildren that plain Stop-Process won't reach.
try {
    while ($true) {
        if ($backend.HasExited -and $frontend.HasExited) { break }
        Start-Sleep -Milliseconds 500
    }
} finally {
    Write-Host ""
    Write-Host "Stopping servers..." -ForegroundColor Yellow
    foreach ($p in @($backend, $frontend)) {
        if ($p -and -not $p.HasExited) {
            & taskkill /F /T /PID $p.Id 2>$null | Out-Null
        }
    }
    Remove-Item "$root\.dev-pids.json" -ErrorAction SilentlyContinue
}
