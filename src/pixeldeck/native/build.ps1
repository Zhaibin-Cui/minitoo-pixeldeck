param([string]$OutputDirectory, [ValidateSet('MediaBridge','InputProbe')][string]$BridgeName = 'MediaBridge')
$ErrorActionPreference = 'Stop'
$framework = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319'
$target = if ($OutputDirectory) { $OutputDirectory } else { Join-Path $PSScriptRoot 'bin' }
New-Item -ItemType Directory -Force -Path $target | Out-Null
$compilerArgs = @('/nologo', '/target:exe', ('/out:' + (Join-Path $target ($BridgeName + '.exe'))))
foreach ($name in @('System.Runtime.WindowsRuntime.dll','System.Runtime.dll','System.Runtime.InteropServices.WindowsRuntime.dll')) {
    $compilerArgs += '/reference:' + (Join-Path $framework $name)
}
foreach ($name in @('Windows.Foundation.winmd','Windows.Media.winmd','Windows.Devices.winmd')) {
    $compilerArgs += '/reference:' + (Join-Path (Join-Path $env:WINDIR 'System32\WinMetadata') $name)
}
$compilerArgs += Join-Path $PSScriptRoot ($BridgeName + '.cs')
& (Join-Path $framework 'csc.exe') @compilerArgs
if ($LASTEXITCODE -ne 0) { throw 'MediaBridge compilation failed' }
Write-Output (Join-Path $target ($BridgeName + '.exe'))
