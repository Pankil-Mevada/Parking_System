# PowerShell bridge to Docker Engine in Ubuntu WSL, independent of Docker Desktop.
# Examples: .\scripts\docker-wsl.ps1 compose ps
#           .\scripts\docker-wsl.ps1 compose up --build -d
$ErrorActionPreference = 'Stop'
$parkingRoot = Split-Path -Parent $PSScriptRoot
$parkingLinuxRoot = & wsl -d Ubuntu --exec wslpath -u ($parkingRoot.Replace('\', '/'))
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve this project path in Ubuntu WSL.' }
[string[]]$parkingDockerArguments = @($args)
if (-not $parkingDockerArguments.Count) { $parkingDockerArguments = @('version') }
& wsl -d Ubuntu -u root --cd $parkingLinuxRoot --exec env -u DOCKER_HOST -u DOCKER_CONTEXT docker --host unix:///var/run/docker.sock @parkingDockerArguments
if ($LASTEXITCODE -ne 0) { throw "WSL Docker command failed with exit code $LASTEXITCODE" }
