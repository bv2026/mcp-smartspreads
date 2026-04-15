# Newsletter MCP Server

This project ingests Smart Spreads weekly newsletter PDFs from the `data` folder, stores complete watchlist rows in a database, stores lighter summaries for the rest of the issue, and exposes that data through an MCP server.

## Project Docs

- [`DESIGN.md`](./DESIGN.md) for architecture and schema decisions
- [`USAGE.md`](./USAGE.md) for setup, MCP queries, and export workflows
- [`PROMPTS.md`](./PROMPTS.md) for reusable prompt patterns
- [`PHASED_ARCHITECTURE.md`](./PHASED_ARCHITECTURE.md) for the two-workflow, two-phase system design
- [`docs/newsletter-intelligence-plan.md`](./docs/newsletter-intelligence-plan.md) for the implementation sequence of newsletter intelligence
- [`docs/phase1-database-schema.md`](./docs/phase1-database-schema.md) for the concrete Phase 1 schema design

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
5. Run the server with `newsletter-mcp`

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
