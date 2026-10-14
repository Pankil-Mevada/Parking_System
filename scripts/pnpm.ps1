# Runs project pnpm commands with Node available to pnpm's child processes.
# Changes PATH only for this invocation; does not modify Windows/user settings.
$ErrorActionPreference = 'Stop'
$parkingRuntime = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies'
$parkingNodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
$parkingNode = if ($parkingNodeCommand) { $parkingNodeCommand.Source } else {
    Join-Path $parkingRuntime 'node/bin/node.exe'
}
$parkingPnpmCommand = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
$parkingPnpm = if ($parkingPnpmCommand) { $parkingPnpmCommand.Source } else {
    Join-Path $parkingRuntime 'bin/fallback/pnpm.cmd'
}
if (-not (Test-Path -LiteralPath $parkingNode)) { throw 'Node.js is missing. Install Node.js 24 LTS or restore the bundled runtime; see README.' }
if (-not (Test-Path -LiteralPath $parkingPnpm)) { throw 'pnpm is missing. Install pnpm 11.25.0 or restore the bundled runtime; see README.' }
$parkingOriginalPath = $env:PATH
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $env:PATH = (Split-Path -Parent $parkingNode) + [IO.Path]::PathSeparator + (Split-Path -Parent $parkingPnpm) + [IO.Path]::PathSeparator + $parkingOriginalPath
    [string[]]$parkingPnpmArguments = @($args)
    if (-not $parkingPnpmArguments.Count) { $parkingPnpmArguments = @('--version') }
    & $parkingPnpm @parkingPnpmArguments
    if ($LASTEXITCODE -ne 0) { throw "pnpm command exited with code $LASTEXITCODE" }
} finally {
    $env:PATH = $parkingOriginalPath
    Pop-Location
}
