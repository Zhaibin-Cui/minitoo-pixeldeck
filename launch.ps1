param(
    [ValidateSet('Preview', 'Display', 'Interactive')][string]$Mode = 'Preview',
    [string]$Demo = 'dashboard',
    [string]$Python = '',
    [string]$Config = '',
    [string]$RuntimeDirectory = '',
    [ValidateRange(0, 86400)][int]$Duration = 600,
    [switch]$Check
)
$ErrorActionPreference = 'Stop'

if (-not $Python) {
    $localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $localPython) {
        $Python = $localPython
    } else {
        $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($launcher) { $Python = & $launcher.Source -3 -c 'import sys; print(sys.executable)' }
        if (-not $Python) {
            $candidate = Get-Command python.exe -ErrorAction SilentlyContinue
            if ($candidate -and $candidate.Source -notlike '*\Microsoft\WindowsApps\*') {
                $Python = $candidate.Source
            }
        }
    }
}
if (-not $Python -or -not (Test-Path -LiteralPath $Python)) {
    throw 'Python was not found. Install Python 3.10+ or pass -Python with an existing python.exe path.'
}
$entry = Join-Path $PSScriptRoot 'run.py'
$oldRuntime = $env:PIXELDECK_HOME
try {
    if ($RuntimeDirectory) { $env:PIXELDECK_HOME = [IO.Path]::GetFullPath($RuntimeDirectory) }
    $doctorArgs = @($entry, 'doctor')
    if ($Config) { $doctorArgs += @('--config', $Config) }
    $diagnostics = & $Python @doctorArgs
    if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed. Install this checkout with: python -m pip install -e ".[telemetry]"' }
    if ($Check) { $diagnostics; return }
    $report = ($diagnostics -join "`n") | ConvertFrom-Json
    if ($Mode -ne 'Preview') {
        if (-not $report.device_configured) { throw 'No device configured. Supply -Config with your private device.json or run configure first.' }
        if (-not $report.windows_backend_supported -or -not $report.python_rfcomm.available) {
            throw 'This Python/Windows environment does not expose the required Classic RFCOMM backend.'
        }
    }
    if ($Mode -eq 'Interactive' -and -not $report.media_input.bridge_built) {
        & $Python $entry build-input
        if ($LASTEXITCODE -ne 0) { throw 'Media bridge build failed. Use -Mode Display for desktop-only controls.' }
    }
    Write-Host "Pixeldeck mode: $Mode / demo: $Demo"
    if ($Mode -eq 'Preview') { Write-Host 'Desktop preview only. The MiniToo screen will not change.' }
    $runArgs = @($entry, 'run', $Demo, '--duration', $Duration)
    if ($Mode -ne 'Preview') { $runArgs += '--send' }
    if ($Mode -eq 'Interactive') { $runArgs += '--media' }
    if ($Config) { $runArgs += @('--config', $Config) }
    & $Python @runArgs
    if ($LASTEXITCODE -ne 0) { throw 'Pixeldeck stopped with an error. See the message above.' }
} finally {
    $env:PIXELDECK_HOME = $oldRuntime
}
