# Newsletter MCP Server

This project ingests Smart Spreads weekly newsletter PDFs from the `data` folder, stores complete watchlist rows in a database, stores lighter summaries for the rest of the issue, and exposes that data through an MCP server.

Current milestone: Phase 1 and Phase 2 are complete for the currently intended scope, and Phase 3 is now live in its first integrated form. The project now has persistent newsletter intelligence, published file-based handoff to the file-based Schwab MCP, an operational Daily workflow, newsletter-history-backed exit scheduling, a strategy/doctrine knowledge layer, and Weekly-Intelligence-informed Sunday principle scoring.

## Latest Integration Update

The current cross-repo hardening sprint is now implemented:

- SmartSpreads publication now writes `publication_validation.json` beside the normal published artifacts.
- `scripts/run_weekly_pipeline.ps1` now gives one operator path for ingest -> refresh/publish -> Schwab contract load validation.
- the sibling `schwab-mcp-file` repo now prefers the published SmartSpreads contract when present, preserves `intermarket` entries, and warns when the watchlist source is stale or fallback-only.

What still remains after this sprint:

- run the new weekly pipeline on the live current issue and review the produced validation output
- decide whether the Schwab side should warn or fail hard when it is using a stale/fallback watchlist
- add the first Daily persistence layer, currently still expected to be `portfolio_fit_reviews`
- continue parser drift protection, ingestion validation summaries, migration tooling, and Phase 3 calibration

## Project Docs

All documentation lives in [`docs/`](./docs/):

- [DESIGN.md](./docs/DESIGN.md) — architecture and schema decisions
- [USAGE.md](./docs/USAGE.md) — setup, MCP queries, and export workflows
- [PHASED_ARCHITECTURE.md](./docs/PHASED_ARCHITECTURE.md) — two-workflow, two-phase system design
- [PROMPTS.md](./docs/PROMPTS.md) — reusable prompt patterns
- [CLAUDE_CHEAT_SHEET.md](./docs/CLAUDE_CHEAT_SHEET.md) — copy-paste guide for Claude workflows
- [CLAUDE_PROJECT_INSTRUCTIONS.md](./docs/CLAUDE_PROJECT_INSTRUCTIONS.md) — recommended Claude Project Instructions
- [TEST_PROMPTS.md](./docs/TEST_PROMPTS.md) — intelligence-testing prompts
- [DEPLOY_LOCAL.md](./docs/DEPLOY_LOCAL.md) — local deployment guide
- [CLIENT_CONFIG.md](./docs/CLIENT_CONFIG.md) — client configuration
- [BACKLOG.md](./docs/BACKLOG.md) / [ROADMAP.md](./docs/ROADMAP.md) — project planning
- Design docs: `phase1-database-schema`, `publication-contract`, `business-layer-design`, `daily-workflow-design`, `symbol-catalog-design`, `strategy-knowledge-design`, `phase3-principle-integration-design`, `claude-project-instructions-reference`, `newsletter-intelligence-plan`

## Offline CLI

When Claude Code is unavailable (rate limits exhausted, outages), use the menu-driven CLI:

```bash
python scripts/smartspreads_cli.py
```

Provides direct access to all 25 MCP tool functions: newsletter ingestion, watchlist queries, exports, publication, catalog management, and strategy doctrine.

## Recommendation

Use `Supabase Postgres` for production and `SQLite` for local development:

- Supabase is the best fit when you want managed Postgres, SQL access, backups, auth, and room to add APIs or dashboards later.
- SQLite is ideal as a zero-friction local fallback while we iterate on parsing and schema changes.

For this use case, I recommend:

1. Keep the MCP server stateless.
2. Store PDFs on disk in `data/`.
3. Store parsed issue metadata, summaries, and watchlist rows in Supabase Postgres.
4. Use a scheduled job or manual MCP tool call each week to ingest newly delivered PDFs.

## Data Model

### `newsletters`

- One row per weekly PDF
- Stores issue date, source file, full extracted text, a compact summary, and metadata

### `newsletter_sections`

- One row per extracted page-level section summary
- Lets clients retrieve lightweight summaries without loading the entire PDF text

### `watchlist_entries`

- One row per watchlist trade
- This is the normalized table you can query for screening, dashboards, exports, and historical analysis

### `watchlist_references`

- One row per issue for the watchlist overview/reference page
- Stores the column definitions plus trading and classification rules used to interpret the watchlist

### `issue_briefs`

- One row per issue-level intelligence brief
- Stores the executive summary plus structured watchlist and change summaries

### `issue_deltas`

- One row per issue comparison
- Stores added, removed, and changed watchlist entries relative to the prior issue

### `parser_runs` and `publication_runs`

- Track ingestion provenance and publication lifecycle state
- Make weekly processing auditable instead of file-only

### `evaluation_runs`, `principle_evaluations`, and `watchlist_decisions`

- Durable Phase 3 audit tables owned by `smartspreads-mcp`
- Store Sunday evaluation runs, per-principle outcomes, and per-entry decision snapshots
- Preserve the current publication bridge while building toward richer decision history

## What Gets Imported

### Fully imported

- Watchlist rows
- Dates
- Spread code
- Side
- Legs
- Category
- Win percentage
- Profit and drawdown fields
- Legacy `portfolio` and `risk_level` fields when present in older issues
- `trade_quality` when present in newer issues
- `volatility_structure` when present in mid-2026 and newer issues

### Summarized

- Narrative article pages
- Margin summary pages
- Macro commentary and other supporting sections

### Stored as reference metadata

- Watch list overview page
- Column definitions
- Entry/exit date handling notes
- Spread leg interpretation rules
- Tier / volatility / portfolio interpretation notes

## Setup

1. Create a virtual environment.
2. Install dependencies with `python -m pip install -e .`
3. Copy `.env.example` to `.env`
4. Set `DATABASE_URL`
5. Run the server with `smartspreads-mcp`

## Testing

Run the current unit and integration tests with:

`python -m unittest discover -s tests`

Phase 3 integration coverage includes:

- Weekly Intelligence influence recording during Sunday scoring
- publication contract validation for principle-aware fields
- dry-run compatibility with the published principle context

## Weekly Pipeline

The current operator-facing weekly path is:

`powershell -ExecutionPolicy Bypass -File .\scripts\run_weekly_pipeline.ps1`

Optional explicit week:

`powershell -ExecutionPolicy Bypass -File .\scripts\run_weekly_pipeline.ps1 -WeekEnded 2026-04-17`

What it does:

- ingests any pending newsletters
- refreshes and republishes the target issue into `published/`
- writes `watchlist.yaml`, `weekly_intelligence.json`, `issue_brief.md`, `publication_validation.json`, and `publication_manifest.json`
- validates that the sibling `C:\work\schwab-mcp-file` repo can load the current published watchlist contract

Note:

- the script writes a real publication run into the configured local DB
- review `published/publication_validation.json` after each run before treating the handoff as trusted for Daily operations

## Supabase Setup

1. Create a Supabase project.
2. Open the SQL editor.
3. Run [`supabase/schema.sql`](./supabase/schema.sql).
4. Set `DATABASE_URL` to your Supabase Postgres connection string.

For local-only testing, keep the default SQLite URL from `.env.example`.

## MCP Tools

- `ingest_newsletter(pdf_path=None)` parses one PDF and stores it
- `ingest_pending_newsletters()` ingests every PDF in `data/` that is not already stored
- `backfill_phase1_intelligence()` seeds parser, brief, delta, and publication records for issues already in the database
- `publish_issue(week_ended, output_dir=None, publication_version=None, published_by=None)` writes the current issue into the `published/` contract files and records a publication run
- `refresh_and_publish_issue(week_ended, output_dir=None, publication_version=None, published_by=None)` rebuilds issue intelligence, reruns current scoring logic, and republishes the approved issue
- `list_issues(limit=10)` returns recently imported issues
- `get_issue_summary(week_ended)` returns the issue summary and section summaries
- `get_watchlist(week_ended, min_trade_quality=None, include_reference=True)` returns structured watchlist rows and can include the issue's watchlist reference block for export/report workflows
- `export_watchlist_csv(week_ended, section_name=None, min_trade_quality=None, include_reference=True, output_path=None, reference_output_path=None)` returns CSV-ready watchlist rows, can filter to `intra_commodity` or `inter_commodity`, and can write the CSV/reference files directly
- `export_watchlist_package(week_ended, section_name=None, min_trade_quality=None, output_dir=None)` returns paired `rows.csv` and `reference.json` content for one issue and can write both to a target directory
- `export_all_watchlists_csv(date_from, date_to, section_name=None, min_trade_quality=None, include_reference=True, output_path=None, reference_output_path=None)` exports one combined CSV across a date range and can also write a reference JSON bundle
- `export_watchlist_bundle(date_from, date_to, output_dir, include_issue_packages=True, include_consolidated=True, include_reference_bundle=True)` writes a folder tree with per-issue intra/inter packages plus consolidated intra/inter CSVs
- `get_watchlist_reference(week_ended)` returns overview rules and column definitions for that issue

## Notes On Parsing

- The current parser is designed around the newsletter structure already present in `data/`.
- Watchlist rows are captured with regex-based extraction from the watchlist pages.
- The parser handles three historical watchlist layouts across the sample PDFs:
  - older `portfolio + risk level`
  - transitional `type + volatility structure`
  - newer `trade quality + volatility structure`
- If Darren changes the PDF layout materially, we will likely want a second parser path or a PDF table extraction upgrade.

## Current Phase 3 Notes

- Sunday scoring is now influenced by stored Weekly Intelligence context derived from the issue brief, issue delta, and watchlist reference.
- The current published contract includes `principle_influences` and `intelligence_context` per entry so downstream review can validate why a setup passed, blocked, or deferred.
- Schwab MCP remains contract-based only in v1. Daily logic should read the published context, not write into Newsletter tables.
- Daily continuity is now started in the Newsletter business layer so the dry run can detect where current portfolio fit weakens a Sunday-approved idea.
- Threshold calibration is still active work. Before trusting a new week operationally, review the Sunday screening counts and blocked examples after publication.

## Current Pause Point

The repo is now at a good observation checkpoint:

- Sunday and Daily Phase 3 flows are working end to end
- the next recommended step is to run the next newsletter cycle, collect metrics, and then add the first Daily persistence layer
- the current leading persistence candidate is `portfolio_fit_reviews`
