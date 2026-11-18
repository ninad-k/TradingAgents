# TradingAgents — C:\TradingAgents\TradingAgents

<#
.SYNOPSIS
    Runs the TradingAgents dashboard backend and frontend together.

.DESCRIPTION
    Starts the FastAPI backend (uvicorn, which also runs the watchlist
    scheduler and unattended auto-trade loop in-process) and the Vite
    frontend dev server, waits for the backend to report healthy, and opens
    the dashboard in a browser. Also starts two Cloudflare quick tunnels (one
    per server) so the dashboard is reachable from outside this machine —
    pass -NoTunnel to skip that and stay local-only. Ctrl+C stops everything.

    The backend is launched with its working directory set to the repo root
    (not backend\ — unlike AccountManagementSystem, TradingAgents keeps its
    package, .env, and .venv at the repo root) using
    .venv\Scripts\python.exe -m uvicorn tradingagents.api.dashboard_api:app.

    Quick tunnels get a new random *.trycloudflare.com hostname every run —
    there's no way to pin it in advance. The frontend reads its backend URL
    from tradingagents\frontend\.env's VITE_API_BASE, which this script
    rewrites to the backend tunnel hostname before starting the frontend (the
    backend's CORS check accepts any *.trycloudflare.com origin, so it
    doesn't need to know the frontend hostname ahead of time).

    The current public URL is written to Public-App-Link.url (a
    double-clickable shortcut) in the repo root, and — unless -NoBrowser is
    passed — opened directly instead of localhost. The shortcut is removed on
    shutdown, since the tunnel (and so the link) dies with it.

    SECURITY NOTE: the dashboard API has NO authentication and can execute
    real trades on the connected MT5 account (POST /api/watchlist/{symbol}
    /analyze?execute_trade=true, /api/codex/run/{symbol}?execute_trade=true,
    etc.). Anyone who obtains the public tunnel URL can trigger trades. The
    tunnel hostname is unguessable but not secret — treat it as sensitive,
    the same way the console warns at startup. Use -NoTunnel if you only want
    local access.

.PARAMETER SeparateWindows
    Launch each server in its own PowerShell window instead of sharing this
    console. This script then exits immediately and the servers keep running
    until you close their windows. Tunnels are not started in this mode.

.PARAMETER NoBrowser
    Don't open the browser once the backend is healthy.

.PARAMETER NoTunnel
    Skip the Cloudflare tunnels and run local-only (http://localhost only).

.PARAMETER SkipChecks
    Skip the dependency and port pre-flight checks.

.EXAMPLE
    .\run.ps1

.EXAMPLE
    .\run.ps1 -NoTunnel -NoBrowser

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\run.ps1
    Use this form if script execution is blocked on your machine.
#>

[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000,
    [switch]$SeparateWindows,
    [switch]$NoBrowser,
    [switch]$NoTunnel,
    [switch]$SkipChecks
)

$ErrorActionPreference = 'Stop'

$APP_NAME = 'TradingAgents'
$APP_ROOT = $PSScriptRoot

$Root        = $PSScriptRoot
$FrontendDir = Join-Path $Root 'tradingagents\frontend'
$VenvPython  = Join-Path $Root '.venv\Scripts\python.exe'

$FrontendUrl = "http://localhost:$FrontendPort"
$BackendUrl  = "http://127.0.0.1:$BackendPort"

function Write-Step  { param([string]$Message) Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Ok    { param([string]$Message) Write-Host "    $Message" -ForegroundColor Green }
function Write-Warn  { param([string]$Message) Write-Host "    $Message" -ForegroundColor Yellow }
function Write-Fail  { param([string]$Message) Write-Host "    $Message" -ForegroundColor Red }

# Name the console window so several stacks running side by side are
# tellable apart at a glance (taskbar included).
function Set-WindowTitle { param([string]$State) $Host.UI.RawUI.WindowTitle = "$APP_NAME - $State" }

# Same banner in every project's run.ps1, so which stack a console belongs to
# is readable from the scrollback as well as the title bar.
function Write-Banner {
    Write-Host ''
    Write-Host "  $APP_NAME" -ForegroundColor White
    Write-Host "  $('-' * $APP_NAME.Length)" -ForegroundColor DarkGray
    Write-Host "  $APP_ROOT" -ForegroundColor DarkGray
    Write-Host ''
}

# npm.cmd spawns node as a child, so killing only the process we started would leave the Vite
# server running and the port held. Walk the tree depth-first instead.
function Stop-ProcessTree {
    param([Parameter(Mandatory = $true)][int]$TargetId)

    try {
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$TargetId" -ErrorAction Stop |
            ForEach-Object { Stop-ProcessTree -TargetId $_.ProcessId }
    } catch {
        # No children, or CIM unavailable — fall through and kill the parent anyway.
    }

    try { Stop-Process -Id $TargetId -Force -ErrorAction Stop } catch { }
}

function Test-PortInUse {
    param([int]$Port)

    try {
        $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
        return $null -ne $listener
    } catch {
        # Get-NetTCPConnection throws when nothing is listening, and is missing on older hosts.
        return $false
    }
}

function Resolve-Cloudflared {
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    foreach ($candidate in @(
        "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe",
        "$env:ProgramFiles\cloudflared\cloudflared.exe"
    )) {
        if ($candidate -and (Test-Path $candidate)) { return $candidate }
    }
    return $null
}

# Starts a Cloudflare quick tunnel for a local port and blocks (up to $TimeoutSec) until the
# assigned https://*.trycloudflare.com URL shows up in its log. Returns @{ Process; Url } —
# Url is $null if the tunnel didn't announce a URL in time (process is left running regardless;
# caller decides whether to treat that as fatal).
function Start-Tunnel {
    param(
        [Parameter(Mandatory = $true)][string]$CloudflaredPath,
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][string]$LogPath,
        [int]$TimeoutSec = 30
    )

    if (Test-Path $LogPath) { Remove-Item $LogPath -Force }

    $proc = Start-Process -FilePath $CloudflaredPath `
        -ArgumentList @('tunnel', '--url', "http://127.0.0.1:$Port") `
        -NoNewWindow -PassThru -RedirectStandardError $LogPath -RedirectStandardOutput 'NUL'

    $url = $null
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if ($proc.HasExited) { break }
        if (Test-Path $LogPath) {
            $match = Select-String -Path $LogPath -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue |
                Select-Object -First 1
            if ($match) { $url = $match.Matches[0].Value; break }
        }
        Start-Sleep -Milliseconds 500
    }
    return @{ Process = $proc; Url = $url }
}

# Rewrites (or adds) a single KEY=value line in a .env file, leaving every other line alone.
function Set-EnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$EnvPath,
        [Parameter(Mandatory = $true)][string]$Key,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $line = "$Key=$Value"
    if (Test-Path $EnvPath) {
        $existing = Get-Content $EnvPath
        if ($existing -match "^$Key=") {
            $updated = $existing -replace "^$Key=.*$", $line
        } else {
            $updated = $existing + $line
        }
    } else {
        $updated = @($line)
    }

    # Set-Content -Encoding utf8 writes a BOM in Windows PowerShell, which can confuse readers
    # that expect plain UTF-8 — write with .NET directly to avoid it.
    $noBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($EnvPath, ($updated -join "`n") + "`n", $noBom)
}

# Polls $Url/health until it answers 200 or $TimeoutSec elapses.
function Wait-BackendHealthy {
    param(
        [Parameter(Mandatory = $true)]$Process,
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSec = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if ($Process.HasExited) { return $false }
        try {
            $resp = Invoke-WebRequest -Uri "$Url/health" -UseBasicParsing -TimeoutSec 2
            if ($resp.StatusCode -eq 200) { return $true }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $false
}

# Writes a double-clickable Windows internet shortcut pointing at the current public tunnel URL.
# Quick tunnels get a new random URL every run, so this file is overwritten (or removed, if no
# tunnel came up) each time — a leftover shortcut would otherwise point at a dead tunnel.
function Set-PublicLinkFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [string]$Url
    )

    if ($Url) {
        $noBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($Path, "[InternetShortcut]`nURL=$Url`n", $noBom)
    } elseif (Test-Path $Path) {
        Remove-Item $Path -Force -ErrorAction SilentlyContinue
    }
}

Set-WindowTitle 'starting...'
Write-Banner

if (-not $SkipChecks) {
    Write-Step 'Checking prerequisites'

    if (-not (Test-Path $VenvPython)) {
        Write-Fail "Python virtualenv not found at $VenvPython"
        Write-Host ''
        Write-Host '    Create it with (uv):' -ForegroundColor DarkGray
        Write-Host '      uv sync' -ForegroundColor DarkGray
        Write-Host ''
        exit 1
    }
    Write-Ok 'Python virtualenv found'

    if (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) {
        Write-Fail 'Frontend dependencies not installed'
        Write-Host ''
        Write-Host '    Install them with:' -ForegroundColor DarkGray
        Write-Host '      npm --prefix tradingagents\frontend install' -ForegroundColor DarkGray
        Write-Host ''
        exit 1
    }
    Write-Ok 'Frontend dependencies found'

    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Fail 'npm is not on PATH. Install Node.js, then reopen this terminal.'
        exit 1
    }
    Write-Ok 'npm found'

    if (-not (Test-Path (Join-Path $Root '.env'))) {
        Write-Warn '.env not found — copy .env.example to .env and configure it first.'
    } else {
        Write-Ok '.env found'
    }

    $busy = @()
    if (Test-PortInUse -Port $BackendPort)  { $busy += $BackendPort }
    if (Test-PortInUse -Port $FrontendPort) { $busy += $FrontendPort }
    if ($busy.Count -gt 0) {
        Write-Fail "Port(s) already in use: $($busy -join ', ')"
        Write-Host ''
        Write-Host '    Find the owner with:' -ForegroundColor DarkGray
        Write-Host "      Get-NetTCPConnection -LocalPort $($busy[0]) -State Listen | Select-Object OwningProcess" -ForegroundColor DarkGray
        Write-Host '    Or pass different ports:' -ForegroundColor DarkGray
        Write-Host '      .\run.ps1 -BackendPort 8001 -FrontendPort 3001' -ForegroundColor DarkGray
        Write-Host ''
        exit 1
    }
    Write-Ok "Ports $BackendPort and $FrontendPort are free"
}

$CloudflaredPath = $null
if (-not $NoTunnel -and -not $SeparateWindows) {
    $CloudflaredPath = Resolve-Cloudflared
    if (-not $CloudflaredPath) {
        Write-Warn 'cloudflared not found — skipping public tunnel, running local-only.'
        Write-Warn 'Install it with: winget install Cloudflare.cloudflared'
    }
}
$BackendTunnelLog  = Join-Path $Root 'backend-cloudflared-tunnel.log'
$FrontendTunnelLog = Join-Path $Root 'frontend-cloudflared-tunnel.log'
$FrontendEnvPath   = Join-Path $FrontendDir '.env'
$PublicLinkPath    = Join-Path $Root 'Public-App-Link.url'

$backendArgs  = @('-m', 'uvicorn', 'tradingagents.api.dashboard_api:app', '--host', '127.0.0.1', '--port', "$BackendPort")
$frontendArgs = @('run', 'dev', '--', '--host', '127.0.0.1', '--port', "$FrontendPort", '--strictPort')

if ($SeparateWindows) {
    Write-Step 'Starting both servers in separate windows'

    Start-Process -FilePath 'powershell' -WorkingDirectory $Root -ArgumentList @(
        '-NoExit', '-Command', "& '$VenvPython' $($backendArgs -join ' ')"
    ) | Out-Null
    Write-Ok "Backend  -> $BackendUrl"

    Start-Process -FilePath 'powershell' -WorkingDirectory $FrontendDir -ArgumentList @(
        '-NoExit', '-Command', "npm $($frontendArgs -join ' ')"
    ) | Out-Null
    Write-Ok "Frontend -> $FrontendUrl"

    Write-Host ''
    Write-Host 'Both servers are starting in their own windows. Close those windows to stop them.' -ForegroundColor DarkGray
    Write-Host ''
    Set-WindowTitle 'detached (servers in their own windows)'
    exit 0
}

$backend        = $null
$frontend       = $null
$backendTunnel  = $null
$frontendTunnel = $null
$publicBackendUrl  = $null
$publicFrontendUrl = $null

try {
    Write-Step 'Starting backend'
    $backend = Start-Process -FilePath $VenvPython -ArgumentList $backendArgs `
        -WorkingDirectory $Root -NoNewWindow -PassThru
    Write-Ok "uvicorn (pid $($backend.Id)) -> $BackendUrl"

    Write-Step 'Waiting for backend to report healthy'
    $healthy = Wait-BackendHealthy -Process $backend -Url $BackendUrl
    if (-not $healthy -and $backend.HasExited) {
        Write-Fail "Backend exited during startup (code $($backend.ExitCode))."
        exit 1
    }
    if ($healthy) {
        Write-Ok 'Backend healthy'
    } else {
        Write-Warn 'Backend did not answer /health in time — starting the frontend anyway.'
    }

    if ($CloudflaredPath -and $healthy) {
        Write-Step 'Starting backend tunnel'
        $result = Start-Tunnel -CloudflaredPath $CloudflaredPath -Port $BackendPort -LogPath $BackendTunnelLog
        $backendTunnel = $result.Process
        if ($result.Url) {
            $publicBackendUrl = $result.Url
            Write-Ok "Backend tunnel -> $publicBackendUrl"
            Set-EnvValue -EnvPath $FrontendEnvPath -Key 'VITE_API_BASE' -Value $publicBackendUrl
            Write-Ok 'Updated tradingagents\frontend\.env VITE_API_BASE to the tunnel URL'
        } else {
            Write-Warn "Backend tunnel didn't report a URL in time — frontend will use $BackendUrl instead (local-only)."
        }
    }

    Write-Step 'Starting frontend'
    $frontend = Start-Process -FilePath 'npm.cmd' -ArgumentList $frontendArgs `
        -WorkingDirectory $FrontendDir -NoNewWindow -PassThru
    Write-Ok "vite (pid $($frontend.Id)) -> $FrontendUrl"

    if ($CloudflaredPath -and $publicBackendUrl) {
        Write-Step 'Starting frontend tunnel'
        $result = Start-Tunnel -CloudflaredPath $CloudflaredPath -Port $FrontendPort -LogPath $FrontendTunnelLog
        $frontendTunnel = $result.Process
        if ($result.Url) {
            $publicFrontendUrl = $result.Url
            Write-Ok "Frontend tunnel -> $publicFrontendUrl"
        } else {
            Write-Warn "Frontend tunnel didn't report a URL in time."
        }
    }

    Set-PublicLinkFile -Path $PublicLinkPath -Url $publicFrontendUrl

    if (-not $NoBrowser) {
        Start-Sleep -Seconds 3
        Start-Process ($(if ($publicFrontendUrl) { $publicFrontendUrl } else { $FrontendUrl })) | Out-Null
    }

    Write-Host ''
    Write-Host "  App (local)   $FrontendUrl" -ForegroundColor White
    Write-Host "  API (local)   $BackendUrl" -ForegroundColor White
    Write-Host "  Docs          $BackendUrl/docs" -ForegroundColor White
    if ($publicFrontendUrl) {
        Write-Host ''
        Write-Host "  App (public)  $publicFrontendUrl" -ForegroundColor Green
        Write-Host "  API (public)  $publicBackendUrl" -ForegroundColor Green
        Write-Host "  Link file     $PublicLinkPath" -ForegroundColor DarkGray
        Write-Host '  Anyone with the public URL can reach this app AND trigger trades' -ForegroundColor Yellow
        Write-Host '  (there is no login). Treat the link as sensitive.' -ForegroundColor Yellow
    } elseif ($CloudflaredPath) {
        Write-Host ''
        Write-Host '  Public tunnel did not come up — see warnings above.' -ForegroundColor Yellow
    }
    Write-Host ''
    Write-Host '  Press Ctrl+C to stop everything.' -ForegroundColor DarkGray
    Write-Host ''

    Set-WindowTitle 'running'

    while ($true) {
        if ($backend.HasExited) {
            Write-Host ''
            Write-Fail "Backend stopped (exit code $($backend.ExitCode)). Shutting down."
            break
        }
        if ($frontend.HasExited) {
            Write-Host ''
            Write-Fail "Frontend stopped (exit code $($frontend.ExitCode)). Shutting down."
            break
        }
        Start-Sleep -Milliseconds 500
    }
} finally {
    Write-Host ''
    Write-Step 'Stopping servers'
    Set-WindowTitle 'stopping...'
    foreach ($proc in @($frontend, $backend, $frontendTunnel, $backendTunnel)) {
        if ($null -ne $proc -and -not $proc.HasExited) {
            Stop-ProcessTree -TargetId $proc.Id
        }
    }
    # The tunnel dies with this process, so a leftover shortcut would point at a dead link.
    Set-PublicLinkFile -Path $PublicLinkPath -Url $null
    Write-Ok 'Stopped'
    Set-WindowTitle 'stopped'
    Write-Host ''
}
