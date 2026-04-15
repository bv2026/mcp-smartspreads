$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$runDir = Join-Path $root "run"
$schwabRoot = "C:\work\schwab-mcp-file"

function Show-ProcessStatus {
    param([string]$Name)

    $statePath = Join-Path $runDir "$Name.json"
    if (-not (Test-Path $statePath)) {
        Write-Output "$Name tracked=False running=False"
        return
    }

    $state = Get-Content $statePath | ConvertFrom-Json
    try {
        $proc = Get-Process -Id $state.pid -ErrorAction Stop
        Write-Output "$Name tracked=True running=True pid=$($proc.Id)"
    } catch {
        Write-Output "$Name tracked=True running=False pid=$($state.pid)"
    }
}

Show-ProcessStatus "newsletter-mcp"
Show-ProcessStatus "schwab-smartspreads-file"

$env:PYTHONPATH = Join-Path $root "src"
$env:NEWSLETTER_DATA_DIR = Join-Path $root "data"
$env:DATABASE_URL = "sqlite:///C:/work/SmartSpreads/newsletters.db"

@'
from newsletter_mcp.config import Settings
from newsletter_mcp.database import Database, Newsletter
from sqlalchemy import select, func

settings = Settings.from_env()
database = Database(settings.database_url)
database.create_schema()

with database.session() as session:
    count = session.execute(select(func.count(Newsletter.id))).scalar_one()

print(f"newsletter_count={count}")
print(f"newsletter_data_dir={settings.data_dir}")
'@ | & "C:\Users\vsbra\AppData\Local\Programs\Python\Python314\python.exe" -

$env:PYTHONPATH = Join-Path $schwabRoot "src"
$env:SCHWAB_WATCHLIST_CONFIG = Join-Path $root "published\watchlist.yaml"
$env:SCHWAB_DB_PATH = Join-Path $schwabRoot "config\smartspreads.db"
$env:SCHWAB_DASHBOARD_PORT = "8766"
$env:SCHWAB_TOKEN_PATH = "C:\Users\vsbra\.schwab\token.json"
$env:SCHWAB_TOS_STATEMENT_PATH = "C:\work\schwab-smartspreads-mcp\config\tos-statement.csv"
$env:TOS_STATEMENT_PATH = "C:\work\schwab-smartspreads-mcp\config\tos-statement.csv"

$envFile = "C:\work\schwab-smartspreads-mcp\.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^export\s+([^=]+)=["'']?(.*?)["'']?$') {
            [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
}

@'
from schwab_mcp.config import load_watchlist_config, load_watchlist_metadata
from schwab_mcp.auth import check_token_age

watchlist = load_watchlist_config()
metadata = load_watchlist_metadata()
token = check_token_age()

print(f"schwab_watchlist_entries={len(watchlist)}")
print(f"schwab_week_ending={metadata.get('week_ending')}")
print(f"schwab_updated={metadata.get('updated')}")
print(f"schwab_token_exists={token.get('exists')}")
print(f"schwab_token_needs_reauth={token.get('needs_reauth')}")
'@ | & "C:\Users\vsbra\AppData\Local\Programs\Python\Python314\python.exe" -

try {
    $statusCode = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8766/dashboard -TimeoutSec 5).StatusCode
    Write-Output "schwab_dashboard_status=$statusCode"
} catch {
    Write-Output "schwab_dashboard_status=unreachable"
}
