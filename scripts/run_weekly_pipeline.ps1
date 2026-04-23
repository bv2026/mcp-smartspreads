$ErrorActionPreference = "Stop"

param(
    [string]$WeekEnded
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:PYTHONPATH = (Join-Path $root "src")
$env:SMARTSPREADS_ROOT = $root
$env:SCHWAB_ROOT = "C:\work\schwab-mcp-file"
if ($WeekEnded) {
    $env:WEEK_ENDED_OVERRIDE = $WeekEnded
}

$pythonCandidates = @(
    "C:\Users\vsbra\AppData\Local\Programs\Python\Python314\python.exe",
    "C:\Users\vsbra\AppData\Local\Programs\Python\Python313\python.exe",
    "C:\Users\vsbra\AppData\Local\Programs\Python\Python311\python.exe"
)

$pythonExe = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $pythonExe) {
    throw "No supported Python executable found for Newsletter MCP weekly pipeline."
}

@'
import importlib.util
import json
import os
from pathlib import Path

root = Path(os.environ["SMARTSPREADS_ROOT"])
schwab_root = Path(os.environ["SCHWAB_ROOT"])
week_override = os.environ.get("WEEK_ENDED_OVERRIDE")

from newsletter_mcp import server

ingest_result = server.ingest_pending_newsletters()
issues = server.list_issues(limit=1)
if not issues:
    raise RuntimeError("No newsletters available after ingestion.")

target_week = week_override or issues[0]["week_ended"]
publish_result = server.refresh_and_publish_issue(
    week_ended=target_week,
    output_dir=str(root / "published"),
    published_by="weekly-pipeline",
)

validation_path = root / "published" / "publication_validation.json"
validation_report = json.loads(validation_path.read_text(encoding="utf-8"))

schwab_config_path = schwab_root / "src" / "schwab_mcp" / "config.py"
if not schwab_config_path.exists():
    raise RuntimeError(f"Missing Schwab config module at {schwab_config_path}")

spec = importlib.util.spec_from_file_location("schwab_file_config", schwab_config_path)
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load Schwab config module.")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

previous_watchlist_path = os.environ.get("SCHWAB_WATCHLIST_CONFIG")
os.environ["SCHWAB_WATCHLIST_CONFIG"] = str(root / "published" / "watchlist.yaml")
try:
    schwab_watchlist = module.load_watchlist_config()
    schwab_metadata = module.load_watchlist_metadata()
    schwab_validation = module.load_watchlist_validation()
finally:
    if previous_watchlist_path is None:
        os.environ.pop("SCHWAB_WATCHLIST_CONFIG", None)
    else:
        os.environ["SCHWAB_WATCHLIST_CONFIG"] = previous_watchlist_path

summary = {
    "ingest": ingest_result,
    "published": publish_result,
    "publication_validation": validation_report,
    "schwab_watchlist_entry_count": len(schwab_watchlist),
    "schwab_watchlist_metadata": schwab_metadata,
    "schwab_watchlist_validation": schwab_validation,
}

print(json.dumps(summary, indent=2))
'@ | & $pythonExe -
