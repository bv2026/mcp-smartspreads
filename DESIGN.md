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
