# Roadmap

## Near term

- Harden PDF parsing for additional newsletter layout changes
- Improve watchlist reference extraction for older OCR-heavy pages
- Add explicit tests for intra/inter section classification on mixed-layout issues
- Add a lightweight health-check or smoke-test MCP tool

## Export improvements

- Add configurable filename patterns for bundle exports
- Add optional JSONL export for downstream pipelines
- Add CSV schema version metadata for long-term compatibility

## Database improvements

- Add migrations for schema evolution instead of relying only on create-all behavior
- Add optional Supabase-first bootstrap and connection helpers
- Add indexes tuned for historical watchlist analysis queries

## Workflow improvements

- Add an automated “new PDF dropped into data” ingest/export script
- Add scheduled local or hosted export jobs
- Add issue-level validation reports after ingestion

## Product direction

- Build report-generation workflows that combine live watchlist rows with reference rules
- Add comparative analysis across old `portfolio/risk_level` and newer `trade_quality` issues
- Add a dashboard or notebook workflow for historical watchlist exploration
