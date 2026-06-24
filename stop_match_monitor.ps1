$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidPath = Join-Path $ProjectRoot "outputs\match_monitor.pid"

if (-not (Test-Path -LiteralPath $PidPath)) {
    "No match monitor PID file found."
    exit 0
}

$pidValue = Get-Content -LiteralPath $PidPath -ErrorAction SilentlyContinue
if (-not $pidValue) {
    Remove-Item -LiteralPath $PidPath -Force
    "Empty PID file removed."
    exit 0
}

$process = Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
if ($process) {
    Stop-Process -Id $process.Id -Force
    "Stopped match monitor PID $($process.Id)."
} else {
    "Match monitor process was not running."
}

Remove-Item -LiteralPath $PidPath -Force
