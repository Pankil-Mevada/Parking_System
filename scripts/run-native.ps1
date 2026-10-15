# Compatibility entry point; Python loads all required configuration.
$ErrorActionPreference = 'Stop'
py (Join-Path $PSScriptRoot 'run_native.py') @args
if ($LASTEXITCODE -ne 0) { throw 'Native API launcher failed. See the Python error above.' }
