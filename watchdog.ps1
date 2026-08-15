$ErrorActionPreference = "SilentlyContinue"

$proj = "C:\Users\User\OneDrive\Documents\Default Project"
$pythonw = Join-Path $proj ".venv\Scripts\pythonw.exe"
$cloudflared = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
if (-not (Test-Path $cloudflared)) { $cloudflared = "cloudflared.exe" }
$tunnelLog = Join-Path $proj "tunnel.log"
$lastStart = Join-Path $proj ".lastserverstart"

# Atomic lock: only ONE watchdog instance acts at a time.
$mutex = New-Object System.Threading.Mutex($false, "TaskFlow_Watchdog")
if (-not $mutex.WaitOne(0)) { exit }

try {
    $serverUp = $false
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -UseBasicParsing -TimeoutSec 4
        if ($resp.StatusCode -eq 200) { $serverUp = $true }
    } catch {
        $serverUp = $false
    }

    if (-not $serverUp) {
        $servers = @(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
            Where-Object { $_.CommandLine -match 'run_server' })

        $stale = $true
        if (Test-Path $lastStart) {
            $age = (Get-Date) - (Get-Item $lastStart).LastWriteTime
            if ($age.TotalSeconds -lt 60) { $stale = $false }
        }

        if ($servers.Count -eq 0) {
            # Nothing running and port down: start one.
            Start-Process -FilePath $pythonw -ArgumentList "run_server.py" -WorkingDirectory $proj -WindowStyle Hidden
            Set-Content -LiteralPath $lastStart -Value (Get-Date -Format "o")
        } elseif ($stale) {
            # Port still down after 60s: the process is wedged. Clear it and retry.
            foreach ($s in $servers) { Stop-Process -Id $s.ProcessId -Force -ErrorAction SilentlyContinue }
            Start-Sleep -Seconds 1
            Start-Process -FilePath $pythonw -ArgumentList "run_server.py" -WorkingDirectory $proj -WindowStyle Hidden
            Set-Content -LiteralPath $lastStart -Value (Get-Date -Format "o")
        }
        # else: still booting, leave it alone.
    }

    # Keep the public tunnel alive.
    $cf = Get-Process cloudflared -ErrorAction SilentlyContinue
    if (-not $cf) {
        Start-Process -FilePath $cloudflared -ArgumentList "tunnel", "--url", "http://127.0.0.1:8000", "--no-autoupdate" -WorkingDirectory $proj -RedirectStandardOutput $tunnelLog -RedirectStandardError (Join-Path $proj "tunnel.err")
    }
}
finally {
    $mutex.ReleaseMutex()
}
