# Requires PowerShell 7, CMake, Git and Visual Studio 2022 C++ Build Tools.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$parkingRoot = Split-Path -Parent $PSScriptRoot
$parkingTools = Join-Path $parkingRoot '.tools'
$parkingVcpkg = Join-Path $parkingTools 'vcpkg'
$parkingDrogon = Join-Path $parkingTools 'drogon'
$parkingBaseline = '44ccfd88b3eca6929d6d16398c7b19945c29a5f6'
$parkingDrogonCommit = '3aae769cc405cf5abb9d477675c6430924f02c7c'

function Invoke-ParkingTool([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed with exit code $LASTEXITCODE" }
}

$parkingVswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $parkingVswhere)) { throw 'Install Visual Studio 2022 C++ Build Tools first; see README.' }
$parkingCompilerInstall = & $parkingVswhere -latest -products '*' -version '[17.0,18.0)' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $parkingCompilerInstall) { throw 'Visual Studio 2022 C++ tools are missing. Install Microsoft.VisualStudio.Workload.VCTools; see README.' }
New-Item -ItemType Directory -Path $parkingTools -Force | Out-Null

if (-not (Test-Path -LiteralPath $parkingVcpkg)) {
    Invoke-ParkingTool -Executable git -Arguments @('clone', '--no-checkout', '--filter=blob:none', 'https://github.com/microsoft/vcpkg.git', $parkingVcpkg)
    Invoke-ParkingTool -Executable git -Arguments @('-C', $parkingVcpkg, 'checkout', '--detach', $parkingBaseline)
}
$parkingActualBaseline = & git -C $parkingVcpkg rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $parkingActualBaseline -ne $parkingBaseline) { throw 'Existing .tools/vcpkg checkout does not match the pinned baseline; review it before proceeding.' }
if (-not (Test-Path -LiteralPath (Join-Path $parkingVcpkg 'vcpkg.exe'))) {
    Invoke-ParkingTool -Executable (Join-Path $parkingVcpkg 'bootstrap-vcpkg.bat') -Arguments @('-disableMetrics')
}
if (-not (Test-Path -LiteralPath $parkingDrogon)) {
    Invoke-ParkingTool -Executable git -Arguments @('clone', '--branch', 'v1.9.14', '--depth', '1', '--recurse-submodules', '--shallow-submodules', 'https://github.com/drogonframework/drogon.git', $parkingDrogon)
}
$parkingActualDrogon = & git -C $parkingDrogon rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $parkingActualDrogon -ne $parkingDrogonCommit) { throw 'Existing .tools/drogon checkout does not match the pinned release; review it before proceeding.' }
Invoke-ParkingTool -Executable git -Arguments @('-C', $parkingDrogon, 'submodule', 'update', '--init', '--recursive', '--depth', '1')

$parkingFrameworkBuild = Join-Path $parkingTools 'native-framework-build'
$parkingFrameworkInstall = Join-Path $parkingTools 'native-framework-installed'
$parkingAppBuild = Join-Path $parkingRoot 'build/native-windows'
$parkingCommon = @(
    '-G', 'Visual Studio 17 2022', '-A', 'x64',
    "-DCMAKE_GENERATOR_INSTANCE=$parkingCompilerInstall",
    "-DCMAKE_TOOLCHAIN_FILE=$parkingVcpkg/scripts/buildsystems/vcpkg.cmake",
    "-DVCPKG_MANIFEST_DIR=$parkingRoot/backend/native",
    "-DVCPKG_INSTALLED_DIR=$parkingTools/native-vcpkg-installed",
    '-DVCPKG_TARGET_TRIPLET=x64-windows'
)
Invoke-ParkingTool -Executable cmake -Arguments (@('-S', $parkingDrogon, '-B', $parkingFrameworkBuild) + $parkingCommon + @(
    "-DCMAKE_INSTALL_PREFIX=$parkingFrameworkInstall", '-DBUILD_SHARED_LIBS=OFF',
    '-DBUILD_CTL=OFF', '-DBUILD_EXAMPLES=OFF', '-DBUILD_TESTING=OFF',
    '-DBUILD_ORM=ON', '-DBUILD_POSTGRESQL=ON', '-DBUILD_MYSQL=OFF',
    '-DBUILD_SQLITE=OFF', '-DBUILD_REDIS=OFF', '-DBUILD_YAML_CONFIG=OFF'
))
Invoke-ParkingTool -Executable cmake -Arguments @('--build', $parkingFrameworkBuild, '--config', 'Release', '--parallel', '2')
Invoke-ParkingTool -Executable cmake -Arguments @('--install', $parkingFrameworkBuild, '--config', 'Release')
Invoke-ParkingTool -Executable cmake -Arguments (@('-S', "$parkingRoot/backend", '-B', $parkingAppBuild) + $parkingCommon + @("-DCMAKE_PREFIX_PATH=$parkingFrameworkInstall"))
Invoke-ParkingTool -Executable cmake -Arguments @('--build', $parkingAppBuild, '--config', 'Release', '--parallel', '2')
Write-Output "Native API built: $parkingAppBuild/Release/parking_api.exe"
