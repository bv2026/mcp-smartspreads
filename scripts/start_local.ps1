$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Starting Newsletter MCP server from $root"
Write-Host "Using .env from $root\\.env"

python -m newsletter_mcp.server
