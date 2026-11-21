param([switch]$FetchDependencies, [switch]$RunTests, [string]$PythonExecutable)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$originalEnvironment = @{}
foreach ($name in @('DOTNET_CLI_HOME', 'NUGET_PACKAGES', 'DOTNET_CLI_TELEMETRY_OPTOUT', 'DOTNET_GENERATE_ASPNET_CERTIFICATE', 'TEMP', 'TMP')) {
    $originalEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
# Resolve an explicitly supplied interpreter relative to the caller, before changing directory.
if ($PythonExecutable) { $PythonExecutable = (Resolve-Path -LiteralPath $PythonExecutable).Path }
Push-Location -LiteralPath $root
try {
    $python = if ($PythonExecutable) { $PythonExecutable } else { Join-Path $root '.venv\Scripts\python.exe' }
    if (-not (Test-Path -LiteralPath $python)) { throw 'Create the Enhanced .venv and install requirements-dev.txt first, or pass -PythonExecutable. See Docs/NATIVE_BUILD.md.' }
    $env:DOTNET_CLI_HOME = Join-Path $root '.toolchain\dotnet-home'
    $env:NUGET_PACKAGES = Join-Path $root '.toolchain\nuget'
    $env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
    $env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'
    $env:TEMP = $env:TMP = Join-Path $root 'build\tmp'
    New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
    function Invoke-Checked([string]$Executable, [string[]]$Arguments) {
        & $Executable @Arguments
        if ($LASTEXITCODE -ne 0) { throw "$Executable failed (exit $LASTEXITCODE)." }
    }
    if ($FetchDependencies) { Invoke-Checked $python @('tools/fetch_native_dependencies.py') }
    Invoke-Checked $python @('tools/build_native.py')
    Invoke-Checked 'dotnet' @('restore', 'src/installer/SnowRunnerEnhanced.Setup.csproj', '--locked-mode')
    Invoke-Checked 'dotnet' @('publish', 'src/installer/SnowRunnerEnhanced.Setup.csproj', '--no-restore', '-c', 'Release',
        '-o', 'build/installer', '-p:DebugType=None', '-p:DebugSymbols=false')
    Invoke-Checked $python @('tools/package_release.py')
    if ($RunTests) {
        Invoke-Checked 'dotnet' @('run', '--project', 'tests/installer-menu/InstallerMenuTests.csproj', '-c', 'Release', '--no-launch-profile')
        Invoke-Checked $python @('-m', 'unittest', 'discover', '-s', 'tests', '-v')
        Invoke-Checked $python @('tools/test_native_compatibility.py')
        Invoke-Checked $python @('tools/test_native_v18.py')
        Invoke-Checked $python @('tools/test_native_loader.py')
    }
}
finally {
    foreach ($name in $originalEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $originalEnvironment[$name], 'Process')
    }
    Pop-Location
}
