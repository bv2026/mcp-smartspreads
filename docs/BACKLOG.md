# Backlog

## Milestone 1: Stabilize Parsing And Ingestion

### Must Have

- [ ] Add parser tests for all supported newsletter layouts
- [ ] Add tests for mixed-page `intra_commodity` / `inter_commodity` classification
- [ ] Add tests for watchlist reference extraction
- [ ] Add ingestion validation reports after each import
- [ ] Add suspicious-parse warnings for partial or drifted layouts
- [ ] Improve OCR/reference cleanup for older overview pages
- [ ] Validate section coverage so key newsletter sections are not silently missed
- [ ] Add parser confidence signals per extracted section/table

### Outcome

This milestone makes the current parser reliable enough for repeatable use.

## Milestone 2: Production-Ready Data Layer

### Must Have

- [ ] Add schema migrations
- [ ] Add migration/version tracking documentation
- [ ] Add Supabase-first production bootstrap guidance
- [ ] Add production-safe database initialization path
- [ ] Add issue re-ingestion/versioning strategy for corrected PDFs and suffix variants like `A` / `B`

### Should Have

- [ ] Add indexes tuned for historical watchlist queries
- [ ] Add environment validation for production startup
- [ ] Add parser audit/provenance fields for source file version, page coverage, and extraction warnings

### Outcome

This milestone makes schema evolution and deployment safer.

## Milestone 3: Operational Workflow

### Must Have

- [ ] Add automated “new PDF dropped into `data`” workflow
- [x] Add one command that runs ingest -> validate -> export bundle
- [ ] Add clear success/failure output for operational runs
- [ ] Add duplicate-detection and corrected-issue handling rules during ingestion

### Should Have

- [x] Add issue-level validation summary files
- [ ] Add health-check / smoke-test MCP tool
- [ ] Add operational logs for each ingest/export run

### Outcome

This milestone turns the project into an operational pipeline instead of a manual toolset.

## Milestone 4: Export And Integration Improvements

### Should Have

- [ ] Add JSON export format
- [ ] Add JSONL export format
- [ ] Add export naming/versioning controls
- [ ] Add common query/export helpers for latest issue and latest section
- [ ] Add stable schema metadata for downstream export consumers
- [ ] Add exportable newsletter brief outputs in Markdown and JSON
- [ ] Add export package manifests so downstream jobs know what was generated

### Outcome

This milestone makes the data easier to integrate into downstream systems.

## Milestone 5: Reporting And Analysis

### Must Have

- [ ] Add issue-level newsletter brief generation
- [ ] Add section-level summary generation for article, macro, strategy, and other key narrative sections
- [ ] Add comparative weekly brief generation to explain what changed from the previous issue

### Should Have

- [ ] Add rules-aware report generation using watchlist rows plus reference rules
- [x] Add strategy/doctrine knowledge layer from the Smart Spreads strategy manual
- [ ] Integrate strategy principles into weekly issue briefs and Daily action-plan explanations
- [ ] Add historical comparison helpers across old and new scoring systems
- [ ] Add notebook/dashboard workflow for exploration
- [ ] Add watchlist change summaries such as added, removed, and upgraded/downgraded ideas across weeks
- [ ] Add theme extraction from newsletter narratives for search and reporting

### Nice To Have

- [ ] Add P/L interpretation workflows derived from reference rules
- [ ] Add anomaly detection for parsing drift across weeks
- [ ] Add semantic search / retrieval across newsletter narratives and reference rules

### Outcome

This milestone turns the stored data into decision support and analysis outputs.

## Milestone 6: Structured Non-Watchlist Data

### Must Have

- [ ] Extract structured trade calendar data instead of summary-only capture
- [ ] Extract structured margin summary data instead of summary-only capture

### Should Have

- [ ] Extract strategy-for-next-week blocks as structured records
- [ ] Track spread chart metadata and page references for later retrieval
- [ ] Extract market outlook subsections such as seasonality, technicals, and fundamentals when reliably detectable

### Outcome

This milestone expands the system from a watchlist-focused database into a fuller newsletter intelligence model.

## Milestone 7: Project Quality

### Should Have

- [ ] Add GitHub Actions validation workflow
- [ ] Add release/version tagging
- [ ] Add contribution/setup conventions

### Nice To Have

- [ ] Add changelog process
- [ ] Add release notes template

### Outcome

This milestone improves maintainability and team workflow.

## Priority Order

### Immediate next priorities

1. Parser tests
2. Richer ingestion and parser validation reporting
3. Daily persistence (`portfolio_fit_reviews`)
4. Live run of the weekly pipeline on the next newsletter cycle
5. Schema migrations

### After that

1. OCR/reference cleanup improvements
2. Structured trade calendar and margin extraction
3. Supabase production bootstrap
4. JSON/JSONL exports
5. Rules-aware reporting

## Notes

- Use `watchlist_entries` as the live trade/export layer.
- Use `watchlist_references` as the interpretation and rules layer.
- Use `strategy_documents`, `strategy_sections`, and `strategy_principles` as the durable doctrine layer behind newsletter and Daily interpretation.
- Keep `intra_commodity` and `inter_commodity` exports explicit in every workflow.
- The newsletters contain additional high-value sections beyond the watchlist, especially trade calendar, margin summary, macro commentary, and strategy notes.
- Brief generation should combine structured rows plus narrative sections instead of summarizing only raw text.
