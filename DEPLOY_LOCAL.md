# Local Deployment

## Recommended local setup

This project is set up to run locally on Windows using:

- Python
- SQLite
- the local `data` folder

The default local configuration is already stored in:

- `.env`

## One-time setup

From `C:\work\SmartSpreads`:

```powershell
python -m pip install -e .
```

## Verify the deployment

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify_local.ps1
```

This checks:

- package import
- environment loading
- database access
- newsletter count

## Start the MCP server locally

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local.ps1
```

This launches the MCP server with the local `.env` configuration.

## Notes

- The server uses the SQLite database at `C:\work\SmartSpreads\newsletters.db`
- Newsletter PDFs are read from `C:\work\SmartSpreads\data`
- Canonical exports are written under `C:\work\SmartSpreads\export`
- If you later move to Supabase, update `DATABASE_URL` in `.env`
