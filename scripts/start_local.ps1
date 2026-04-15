$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$pythonCandidates = @(
    "C:\Users\vsbra\AppData\Local\Programs\Python\Python314\python.exe",
    "C:\Users\vsbra\AppData\Local\Programs\Python\Python313\python.exe",
    "C:\Users\vsbra\AppData\Local\Programs\Python\Python311\python.exe"
)

$pythonExe = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $pythonExe) {
    throw "No supported Python executable found for Newsletter MCP."
}

& $pythonExe -m newsletter_mcp.server
