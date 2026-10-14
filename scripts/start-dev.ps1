# Starts the local WSL backend/database and keeps the frontend running in this terminal.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$parkingRoot = Split-Path -Parent $PSScriptRoot
$parkingListeners = @(Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue)
if ($parkingListeners.Count) {
    Write-Warning 'Port 5173 is already in use. If the parking website is running, reload http://127.0.0.1:5173. To restart it, press Ctrl+C in its existing frontend terminal first, then run this script again. No existing process has been stopped.'
    return
}
$parkingPnpm = Join-Path $PSScriptRoot 'pnpm.ps1'
& $parkingPnpm --version | Out-Null
Push-Location $parkingRoot
$parkingWslSession = $null
try {
    if (-not (Test-Path -LiteralPath '.env')) { throw 'Local .env is missing; follow README setup first.' }
    # systemd services do not keep a WSL distribution alive on their own.
    $parkingWslSession = Start-Process -FilePath (Get-Command wsl.exe).Source -ArgumentList @('-d', 'Ubuntu', '--exec', 'sleep', 'infinity') -WindowStyle Hidden -PassThru
    & wsl -d Ubuntu -u root --exec systemctl start docker
    if ($LASTEXITCODE -ne 0) { throw 'Could not start Docker Engine in Ubuntu WSL.' }
    & (Join-Path $PSScriptRoot 'docker-wsl.ps1') compose up -d
    if (-not (Test-Path -LiteralPath 'node_modules')) {
        & $parkingPnpm install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    }
    Write-Output 'Open http://127.0.0.1:5173. Keep this terminal open; Ctrl+C stops the frontend.'
    & $parkingPnpm dev
    if ($LASTEXITCODE -ne 0) { throw "Frontend exited with code $LASTEXITCODE" }
} finally {
    if ($parkingWslSession -and -not $parkingWslSession.HasExited) {
        $parkingWslSession.Kill()
        $parkingWslSession.WaitForExit()
    }
    Pop-Location
}
