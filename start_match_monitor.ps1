$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $ProjectRoot "outputs"
$LogPath = Join-Path $LogDir "match_monitor.log"
$PidPath = Join-Path $LogDir "match_monitor.pid"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$existing = $null
if (Test-Path -LiteralPath $PidPath) {
    $existingPid = Get-Content -LiteralPath $PidPath -ErrorAction SilentlyContinue
    if ($existingPid) {
        $existing = Get-Process -Id ([int]$existingPid) -ErrorAction SilentlyContinue
    }
}

if ($existing) {
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "Match monitor already running with PID $($existing.Id)."
    exit 0
}

$python = "python"
$args = ".\match_monitor.py --poll-seconds 300 --final-whistle-buffer 110"
$process = Start-Process -FilePath $python -ArgumentList $args -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
$process.Id | Set-Content -LiteralPath $PidPath
Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "Started match monitor with PID $($process.Id)."
"Started match monitor with PID $($process.Id)."
