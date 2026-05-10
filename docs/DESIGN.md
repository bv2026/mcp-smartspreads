# Newsletter MCP Design

## Goal

This MCP server ingests Smart Spreads weekly newsletter PDFs from `data/`, extracts the live watchlist plus the watchlist reference/overview rules, stores both in a database, and exposes query/export tools for downstream analysis.

## Core Design

### Ingestion model

Each newsletter issue is parsed into three data layers:

1. `newsletters`
   Stores issue-level metadata, raw extracted text, and a compact overall summary.

2. `watchlist_entries`
   Stores the live rows from the actual weekly watchlist.
   These rows are normalized and tagged with:
   - `section_name`
   - `portfolio` / `risk_level` for older issues
   - `trade_quality` / `volatility_structure` for newer issues

3. `watchlist_references`
   Stores the watchlist overview/reference page separately from live trades.
   This includes:
   - column definitions
   - trading rules
   - classification rules
   - raw reference page text

The key design choice is that overview/example pages are not treated as live trades.

## Section handling

The newsletters contain two real watchlist sections:

- `intra_commodity`
- `inter_commodity`

Some PDFs place both sections on the same page. In those cases, the parser uses both page structure and row shape to classify rows correctly.

Example:
- rows with comma-separated commodity names are typically `inter_commodity`
- single-market names are typically `intra_commodity`

## Historical format support

The parser currently supports three watchlist layouts found in the sample PDFs:

1. Older layout
   - `portfolio`
   - `risk_level`

2. Transitional layout
   - `portfolio`
   - `volatility_structure`

3. Newer layout
   - `trade_quality`
   - `volatility_structure`

This allows one database schema to hold a continuous history even though the newsletter format changed over time.

## Export model

Exports are built from the live query layer and can optionally include reference metadata.

Supported export styles:

- single-issue CSV
- single-issue package with `rows.csv` and `reference.json`
- consolidated CSV across a date range
- full folder bundle with:
  - per-issue intra/inter packages
  - consolidated intra/inter CSVs
  - consolidated reference bundles

## Database recommendation

Recommended production target:
- `Supabase Postgres`

Why:
- managed Postgres
- easy schema evolution
- backups
- SQL-friendly for analysis
- good fit for MCP + export workflows

Recommended local/dev target:
- `SQLite`

Why:
- simple local testing
- fast parser iteration
- zero setup

## Storage recommendation

The recommended architecture is:

- relational DB as the system of record
- published files as the integration boundary
- JSON as an artifact format, not the primary source of truth

### Why not file-only

File-only storage is fine for exports and handoff, but it is weak as the historical memory layer.

With file-only storage, cross-week intelligence becomes harder to:
- query
- compare
- audit
- evolve safely

That is exactly the weakness in the pre-database workflow:
- extract
- publish
- forget

### Why not JSON-first / NoSQL-first

JSON documents are useful for nested payloads and publication outputs, but they should not be the canonical store for this project.

This dataset is naturally relational:
- issues
- watchlist rows
- reference rules
- briefs
- deltas
- publication runs

Those entities benefit from:
- stable identifiers
- joins and comparisons
- explicit schema evolution
- structured historical queries

### Recommended hybrid

The best practical model is:

1. relational DB for normalized intelligence history
2. files for downstream consumption
3. optional JSON payloads inside the DB or in exports for richer nested details

This gives:
- persistent memory
- operational simplicity
- easy downstream integration
- room for future analytics and reporting

## Symbol normalization

The next important normalization layer should move symbol/root mapping out of hardcoded code tables and into the database.

Recommended model:

- `schwab_futures_catalog`
  authoritative catalog of Schwab/TOS futures roots and product metadata

- `newsletter_commodity_catalog`
  authoritative catalog of newsletter commodity roots plus preferred Schwab/TOS mappings and policy blocks

This layer is needed because the newsletter and Schwab are separate naming systems, and publication logic needs a data-driven crosswalk rather than a fixed dictionary in code.

## Strategy knowledge layer

The next major knowledge layer should incorporate the Smart Spreads strategy manual as durable doctrine, separate from weekly newsletters.

Recommended model:

- `strategy_documents`
  stores strategy source-document metadata and extracted raw text

- `strategy_sections`
  stores chapter/section-level extracted text and summaries

- `strategy_principles`
  stores normalized framework principles such as trade quality, portfolio fit, survivability, volatility, and execution discipline

This layer should improve:
- issue brief explanations
- blocked-trade explanations
- daily action-plan reasoning

It should not:
- replace weekly newsletter parsing
- inject raw strategy text directly into watchlist tables
- require raw PDF parsing at runtime for normal use

## Main tradeoffs

### Strengths

- works with the actual newsletter samples already in `data/`
- preserves both live trades and interpretation metadata
- supports historical newsletter changes
- exports are ready for CSV/report workflows

### Limitations

- parsing is still PDF-text based, not native table extraction
- if the PDF layout changes materially, parser rules will need updates
- older OCR-style text can still require occasional cleanup heuristics

## Current output structure

Canonical generated export bundle:

- `C:\work\SmartSpreads\export`

Important subfolders:

- `C:\work\SmartSpreads\export\issues`
- `C:\work\SmartSpreads\export\consolidated`
