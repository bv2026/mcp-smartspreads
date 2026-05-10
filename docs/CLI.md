# SmartSpreads Unified CLI

Menu-driven offline access to both the SmartSpreads and Schwab MCP servers. Use this when Claude Code is unavailable (rate limits, outages, etc.).

## Quick Start

```
cd C:\work\SmartSpreads
python scripts/smartspreads_cli.py
```

## Requirements

- Python with `newsletter_mcp` installed (`pip install -e .` from SmartSpreads root)
- `.env` in SmartSpreads root with `DATABASE_URL`
- For Schwab layers (D/E): `schwab-mcp-file` repo at `C:\work\schwab-mcp-file` (or set `SCHWAB_ROOT` env var), with `.env` containing Schwab credentials

## Menu Structure

```
============================================================
  SmartSpreads Unified CLI
============================================================
    A. Setup & Management        (SmartSpreads)
    B. Sunday Pipeline            (SmartSpreads)
    C. Daily Bridge               (SmartSpreads)
    D. Positions & Quotes         (Schwab)
    E. Trade History & Import     (Schwab)

    q. Quit    ?. Help
============================================================
```

### Navigation

- Type a letter (A-E) to enter a layer
- Type a number to run an option within a layer
- `b` — back to top menu
- `q` — quit
- Enter to accept default values shown in `[brackets]`

---

## Layer A — Setup & Management

SmartSpreads database and catalog maintenance. Reports save to `reports/management/`.

| # | Option | What it does |
|---|---|---|
| 1 | List issues | Show recently imported newsletter issues |
| 2 | Verify newsletter ingested | Confirm a specific issue exists in the database |
| 3 | Ingest single newsletter PDF | Parse and store one PDF |
| 4 | Ingest all pending newsletters | Batch-ingest every PDF in `data/` not yet stored |
| 5 | Backfill intelligence | Seed parser, brief, delta, and publication records |
| 6 | Import Schwab futures catalog | Load futures symbol catalog from CSV |
| 7 | View Schwab futures catalog | Browse the symbol catalog |
| 8 | View commodity catalog | Newsletter commodity name mappings |
| 9 | View contract month codes | Month code reference (F=Jan, G=Feb, ...) |
| 10 | Import strategy manual | Parse strategy PDF into principles |
| 11 | View strategy principles | Browse stored strategy principles |

---

## Layer B — Sunday Pipeline

Weekly newsletter processing. Reports save to `reports/<week_ended>/`.

| # | Option | What it does |
|---|---|---|
| 1 | Full Sunday pipeline | Ingest → verify → publish → validate → CSV export. Produces `sunday_pipeline.md` + `<date>-watchlist.csv` |
| 2 | Ingest & verify only | Steps 1-2 only (no publish) |
| 3 | Publish issue | Refresh and republish a specific issue |
| 4 | Validated watchlist report | Run verify → validated report chain |
| 5 | Issue analysis | Consolidated brief + watchlist + principles → `issue_analysis.md` |
| 6 | Export watchlist CSV | Standalone CSV export with optional section filter |

### Typical Sunday Workflow

1. Drop the new newsletter PDF into `data/`
2. Run **B > 1** (full pipeline)
3. Review `reports/<week_ended>/sunday_pipeline.md`
4. Optionally run **B > 5** for deeper analysis

---

## Layer C — Daily Bridge

SmartSpreads-side daily operations. Screen output only (no saved reports — daily reporting lives with the Schwab MCP).

| # | Option | What it does |
|---|---|---|
| 1 | Exit schedule (manual) | Enter positions as JSON, get exit dates |
| 2 | Exit schedule (from file) | Load Schwab positions JSON, get exit dates |
| 3 | Tradeable ideas only | Show only tradeable watchlist entries |
| 4 | Weekly intelligence context | Key themes, risks, and opportunities |

---

## Layer D — Schwab Positions & Quotes

REST-based Schwab account data. No streaming required. Reports save to `reports/schwab/<today>/`.

| # | Option | What it does |
|---|---|---|
| 1 | Auth check | Verify Schwab OAuth token is valid |
| 2 | Account summary | Balances, margin, buying power |
| 3 | Futures positions | All legs with marks, dollar P&L, spread linkage |
| 4 | Equity positions | ETF/stock positions |
| 5 | Morning brief | All spreads sorted by urgency with P&L |
| 6 | Quote single symbol | REST quote for one futures contract |
| 7 | Quote batch | REST quotes for multiple symbols |
| 8 | Spread value (calendar) | Near − far month calculation |
| 9 | Butterfly value | Front − 2*middle + back calculation |
| 10 | Target distance check | How far a spread is from target/stop |
| 11 | Seasonal days remaining | Days left in the seasonal window |
| 12 | Market hours | Is the futures market open? |
| 13 | Transactions | Account transaction history (up to 60 days) |
| 14 | Check positions.yaml dates | Flag spreads missing enter/exit dates |

### Typical Morning Workflow

1. Run **D > 1** (auth check)
2. Run **D > 5** (morning brief) — all spreads at a glance
3. Run **D > 3** (futures positions) — detailed leg-level view

---

## Layer E — Schwab Trade History & Import

Trade log and TOS statement import. Reports save to `reports/schwab/<today>/`.

| # | Option | What it does |
|---|---|---|
| 1 | Trade history | Realized P&L with spread/symbol/asset filters |
| 2 | Import TOS P&L | Import closed positions from TOS CSV |
| 3 | Seed stream positions | One-time migration from TOS CSV to stream tracking |

---

## Report Directory Structure

```
reports/
  management/              # Layer A — overwritten each run
    list_issues.md
    verify_newsletter_ingested.md
    ...
  2026-05-08/              # Layer B — one folder per newsletter week
    sunday_pipeline.md
    issue_analysis.md
    2026-05-08-watchlist.csv
  schwab/
    2026-05-10/            # Layers D & E — one folder per calendar day
      futures_positions.md
      morning_brief.md
      trade_history.md
      ...
```

## Streaming Tools

The CLI uses REST-based Schwab tools (no WebSocket stream). For streaming tools (`get_live_quote`, `get_spread_value_live`, `get_watchlist_quotes`, `get_recent_bars`), use the full Schwab MCP server via Claude Code or Claude Desktop.

## Troubleshooting

**"Schwab MCP not found"** — Set `SCHWAB_ROOT` env var to the schwab-mcp-file repo path, or ensure it exists at `C:\work\schwab-mcp-file`.

**"SCHWAB_REAUTH_REQUIRED"** — Token expired or missing credentials. Ensure `C:\work\schwab-mcp-file\.env` has `SCHWAB_CLIENT_ID` and `SCHWAB_CLIENT_SECRET`, then run `python -m schwab_mcp.auth --init`.

**"No newsletter found"** — Database is empty. Drop a PDF into `data/` and run **A > 4** or **B > 1**.
