# Uses the project's existing local .env without printing its credentials.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$parkingRoot = Split-Path -Parent $PSScriptRoot
$parkingExecutable = Join-Path $parkingRoot 'build/native-windows/Release/parking_api.exe'
if (-not (Test-Path -LiteralPath $parkingExecutable)) { throw 'Run scripts/build-native.ps1 first.' }
if (-not $env:API_DATABASE_URL) {
    $parkingEnvFile = Join-Path $parkingRoot '.env'
    if (-not (Test-Path -LiteralPath $parkingEnvFile)) { throw 'Create local .env as documented in README.' }
    $parkingConnection = Get-Content -LiteralPath $parkingEnvFile | Where-Object { $_ -match '^API_DATABASE_URL=' } | Select-Object -First 1
    if (-not $parkingConnection) { throw 'API_DATABASE_URL is missing from local .env.' }
    # Container DNS name db resolves only inside Docker; host uses its localhost port.
    $env:API_DATABASE_URL = $parkingConnection.Substring('API_DATABASE_URL='.Length) -replace '(^|\s)host=db(?=\s|$)', '${1}host=127.0.0.1'
}
if (Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8080 is already in use. Stop the Docker API with docker compose stop api before running the native API.'
}
& $parkingExecutable
if ($LASTEXITCODE -ne 0) { throw "Native API exited with code $LASTEXITCODE" }
