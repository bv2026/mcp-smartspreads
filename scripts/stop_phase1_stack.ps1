$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$runDir = Join-Path $root "run"

foreach ($name in @("smartspreads-mcp", "schwab-smartspreads-file")) {
    $statePath = Join-Path $runDir "$name.json"
    if (-not (Test-Path $statePath)) {
        Write-Output "$name is not tracked."
        continue
    }

    $state = Get-Content $statePath | ConvertFrom-Json
    try {
        Stop-Process -Id $state.pid -ErrorAction Stop
        Write-Output "$name stopped (PID $($state.pid))"
    } catch {
        Write-Output "$name was not running."
    }
    Remove-Item $statePath -ErrorAction SilentlyContinue
}
