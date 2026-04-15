# Backlog

## Milestone 1: Stabilize Parsing And Ingestion

### Must Have

- [ ] Add parser tests for all supported newsletter layouts
- [ ] Add tests for mixed-page `intra_commodity` / `inter_commodity` classification
- [ ] Add tests for watchlist reference extraction
- [ ] Add ingestion validation reports after each import
- [ ] Add suspicious-parse warnings for partial or drifted layouts
- [ ] Improve OCR/reference cleanup for older overview pages

### Outcome

This milestone makes the current parser reliable enough for repeatable use.

## Milestone 2: Production-Ready Data Layer

### Must Have

- [ ] Add schema migrations
- [ ] Add migration/version tracking documentation
- [ ] Add Supabase-first production bootstrap guidance
- [ ] Add production-safe database initialization path

### Should Have

- [ ] Add indexes tuned for historical watchlist queries
- [ ] Add environment validation for production startup

### Outcome

This milestone makes schema evolution and deployment safer.

## Milestone 3: Operational Workflow

### Must Have

- [ ] Add automated “new PDF dropped into `data`” workflow
- [ ] Add one command that runs ingest -> validate -> export bundle
- [ ] Add clear success/failure output for operational runs

### Should Have

- [ ] Add issue-level validation summary files
- [ ] Add health-check / smoke-test MCP tool

### Outcome

This milestone turns the project into an operational pipeline instead of a manual toolset.

## Milestone 4: Export And Integration Improvements

### Should Have

- [ ] Add JSON export format
- [ ] Add JSONL export format
- [ ] Add export naming/versioning controls
- [ ] Add common query/export helpers for latest issue and latest section
- [ ] Add stable schema metadata for downstream export consumers

### Outcome

This milestone makes the data easier to integrate into downstream systems.

## Milestone 5: Reporting And Analysis

### Should Have

- [ ] Add rules-aware report generation using watchlist rows plus reference rules
- [ ] Add historical comparison helpers across old and new scoring systems
- [ ] Add notebook/dashboard workflow for exploration

### Nice To Have

- [ ] Add P/L interpretation workflows derived from reference rules
- [ ] Add anomaly detection for parsing drift across weeks

### Outcome

This milestone turns the stored data into decision support and analysis outputs.

## Milestone 6: Project Quality

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
2. Ingestion validation report
3. Automated ingest/export workflow
4. Schema migrations

### After that

1. OCR/reference cleanup improvements
2. Supabase production bootstrap
3. JSON/JSONL exports
4. Rules-aware reporting

## Notes

- Use `watchlist_entries` as the live trade/export layer.
- Use `watchlist_references` as the interpretation and rules layer.
- Keep `intra_commodity` and `inter_commodity` exports explicit in every workflow.
