# Regression check: use the bundled runtime when Node/pnpm are absent from PATH.
$ErrorActionPreference = 'Stop'
$parkingRoot = Split-Path -Parent $PSScriptRoot
$parkingOriginalPath = $env:PATH
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\WindowsPowerShell\v1.0"
    $parkingMinimalPath = $env:PATH
    if (Get-Command node.exe -ErrorAction SilentlyContinue) { throw 'Regression test requires Node to be absent from PATH.' }
    $parkingNodeVersion = & (Join-Path $parkingRoot 'scripts/pnpm.ps1') exec node --version
    if ($parkingNodeVersion -notmatch '^v\d+\.\d+\.\d+$') { throw 'pnpm child process did not resolve Node.' }
    $parkingPnpmVersion = & (Join-Path $parkingRoot 'scripts/pnpm.ps1') --version
    if ($parkingPnpmVersion -notmatch '^\d+\.\d+\.\d+$') { throw 'Single-argument pnpm forwarding failed.' }
    if ($env:PATH -ne $parkingMinimalPath) { throw 'pnpm wrapper did not restore the caller PATH.' }
    Write-Output "Windows tooling regression passed: Node $parkingNodeVersion; pnpm $parkingPnpmVersion; caller PATH preserved."
} finally {
    $env:PATH = $parkingOriginalPath
}
