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

    # Keep the public tunnel alive. The free trycloudflare connection can drop
    # (HTTP 530 / Cloudflare error 1033) while the process stays up, so the URL
    # itself is health-checked and the tunnel is restarted when it stops
    # answering. http2 is forced because this network blocks QUIC (port 7844).
    $tunnelOk = $false
    $tunnelUrl = $null
    $tunnelErr = Join-Path $proj "tunnel.err"
    $urlMatches = @()
    foreach ($lf in @($tunnelLog, $tunnelErr)) {
        if (Test-Path $lf) {
            $urlMatches += Select-String -Path $lf -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue
        }
    }
    if ($urlMatches.Count -gt 0) {
        $tunnelUrl = $urlMatches[-1]
        $url = $tunnelUrl.Matches[0].Value
        try {
            $tr = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8
            if ($tr.StatusCode -eq 200) { $tunnelOk = $true }
        } catch {
            $tunnelOk = $false
        }
        if ($tunnelOk -and $url) {
            Set-Content -LiteralPath (Join-Path $proj "live-url.txt") -Value $url
        }
    }

    $cf = Get-Process cloudflared -ErrorAction SilentlyContinue
    $failMark = Join-Path $proj ".tunnelfail"
    if (-not $cf) {
        Start-Process -FilePath $cloudflared -ArgumentList "tunnel", "--url", "http://127.0.0.1:8000", "--no-autoupdate", "--protocol", "http2" -WorkingDirectory $proj -RedirectStandardOutput $tunnelLog -RedirectStandardError (Join-Path $proj "tunnel.err")
    } elseif (-not $tunnelOk) {
        # Process alive but the tunnel is not answering. Only restart after TWO
        # consecutive failures so a single network hiccup does not churn the URL.
        $consecutive = 0
        if (Test-Path $failMark) { $consecutive = 2 }
        $cfAge = (Get-Date) - (Get-Process -Id $cf.Id).StartTime
        if ($consecutive -ge 2 -and $cfAge.TotalSeconds -gt 90) {
            Stop-Process -Id $cf.Id -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
            Start-Process -FilePath $cloudflared -ArgumentList "tunnel", "--url", "http://127.0.0.1:8000", "--no-autoupdate", "--protocol", "http2" -WorkingDirectory $proj -RedirectStandardOutput $tunnelLog -RedirectStandardError (Join-Path $proj "tunnel.err")
            Remove-Item -LiteralPath $failMark -Force -ErrorAction SilentlyContinue
        } else {
            Set-Content -LiteralPath $failMark -Value (Get-Date -Format "o")
        }
    } else {
        Remove-Item -LiteralPath $failMark -Force -ErrorAction SilentlyContinue
    }
}
finally {
    $mutex.ReleaseMutex()
}
