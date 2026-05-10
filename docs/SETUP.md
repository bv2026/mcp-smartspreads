# Local Setup & MCP Configuration

## One-time setup

From `C:\work\SmartSpreads`:

```powershell
python -m pip install -e .
```

## Verify the deployment

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify_local.ps1
```

This checks: package import, environment loading, database access, newsletter count.

## Start the MCP server locally

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local.ps1
```

The script loads `.env` and runs `python -m newsletter_mcp.server`.

## MCP client configuration

### Recommended (PowerShell wrapper)

```json
{
  "mcpServers": {
    "smartspreads-mcp": {
      "command": "powershell",
      "args": [
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "C:\\work\\SmartSpreads\\scripts\\start_local.ps1"
      ]
    }
  }
}
```

### Alternative (direct Python)

```json
{
  "mcpServers": {
    "smartspreads-mcp": {
      "command": "python",
      "args": ["-m", "newsletter_mcp.server"],
      "cwd": "C:\\work\\SmartSpreads"
    }
  }
}
```

Works when Python is on `PATH` and dependencies are installed.

## Available MCP tools after connecting

- `ingest_newsletter`
- `ingest_pending_newsletters`
- `list_issues`
- `get_issue_summary`
- `get_watchlist`
- `export_watchlist_csv`
- `export_watchlist_package`
- `export_all_watchlists_csv`
- `export_watchlist_bundle`
- `get_watchlist_reference`
- `verify_newsletter_ingested`
- `get_validated_watchlist_report`
- `refresh_and_publish_issue`
- `publish_issue`
- `get_daily_exit_schedule`
- `import_strategy_manual`
- `list_strategy_principles`

## Local paths

| Path | Purpose |
|------|---------|
| `newsletters.db` | SQLite database |
| `data/` | Newsletter PDFs |
| `reference/strategy/` | Strategy manual PDF |
| `published/` | Shared contract consumed by schwab-mcp-file |
| `export/` | CSV/bundle exports |
