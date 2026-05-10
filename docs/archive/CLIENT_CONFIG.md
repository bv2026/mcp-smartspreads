# Client Config

This server is intended to be launched as a local stdio MCP process.

## Recommended command

Use this command as the MCP server launcher:

```powershell
powershell -ExecutionPolicy Bypass -File C:\work\SmartSpreads\scripts\start_local.ps1
```

That script:

- starts from the project root
- loads the local `.env`
- runs `python -m newsletter_mcp.server`

## Generic stdio config

Use this shape for any MCP client that accepts a command plus arguments:

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

## Claude Desktop style config

If your client uses a Claude Desktop style JSON config, use:

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

## Alternative direct Python config

If you prefer not to use the PowerShell wrapper:

```json
{
  "mcpServers": {
    "smartspreads-mcp": {
      "command": "python",
      "args": [
        "-m",
        "newsletter_mcp.server"
      ],
      "cwd": "C:\\work\\SmartSpreads"
    }
  }
}
```

This works best when:

- Python is on `PATH`
- dependencies are already installed
- the working directory is set to `C:\\work\\SmartSpreads`

## What to expect after connecting

Once the client launches the server, these MCP tools should be available:

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

## Local verification before connecting

Run this first:

```powershell
powershell -ExecutionPolicy Bypass -File C:\work\SmartSpreads\scripts\verify_local.ps1
```

Then start the server manually if you want to sanity-check the command:

```powershell
powershell -ExecutionPolicy Bypass -File C:\work\SmartSpreads\scripts\start_local.ps1
```
