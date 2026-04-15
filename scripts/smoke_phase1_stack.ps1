$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $root "src"
$env:NEWSLETTER_DATA_DIR = Join-Path $root "data"
$env:DATABASE_URL = "sqlite:///C:/work/SmartSpreads/newsletters.db"

@'
from newsletter_mcp.server import get_watchlist, publish_issue

publish_result = publish_issue("2026-04-10")
watchlist = get_watchlist("2026-04-10")

print(f"published_version={publish_result['publication_version']}")
print(f"published_count={publish_result['watchlist_count']}")
print(f"watchlist_entries={len(watchlist['entries'])}")
print(f"watchlist_reference_present={watchlist.get('watchlist_reference') is not None}")
'@ | & "C:\Users\vsbra\AppData\Local\Programs\Python\Python314\python.exe" -

$schwabRoot = "C:\work\schwab-mcp-file"
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

watchlist = load_watchlist_config()
metadata = load_watchlist_metadata()

print(f"schwab_seen_entries={len(watchlist)}")
print(f"schwab_seen_week_ending={metadata.get('week_ending')}")
print(f"schwab_first_entry={watchlist[0]['name'] if watchlist else 'none'}")
'@ | & "C:\Users\vsbra\AppData\Local\Programs\Python\Python314\python.exe" -
