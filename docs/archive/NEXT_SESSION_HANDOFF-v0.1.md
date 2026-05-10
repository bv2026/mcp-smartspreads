# SmartSpreads Next Session Handoff

Version: v0.1
Date: 2026-05-02
Repo: `C:\work\SmartSpreads`

## 1. What This Project Is

`smartspreads-mcp` is the newsletter-intelligence side of the Smart Spreads system.

Its job is to:

- ingest weekly Smart Spreads PDF newsletters from `data/`
- parse and normalize watchlist rows plus lighter narrative/reference context
- store durable weekly intelligence in the newsletter DB
- evaluate entries against stored strategy principles
- publish an approved weekly contract into `published/`
- support the Schwab-side Daily workflow without taking over live pricing or account-state ownership

The repo is not the live operational engine for positions or streaming prices.
That belongs to the sibling repo: `C:\work\schwab-mcp-file`

## 2. Architecture And Dependency Map

Two connected workflows:

1. Sunday workflow: ingest newsletter, parse/store intelligence, evaluate principles, publish approved weekly contract
2. Daily workflow: Schwab MCP reads live positions/prices, SmartSpreads MCP contributes weekly context, rules, deltas, exit interpretation

Core architectural rule:
- SmartSpreads owns newsletter memory and publication
- Schwab owns operational/live portfolio state
- integration is contract-first through `published/`, not shared writable DB state

### Internal module responsibilities

- `src/newsletter_mcp/parser.py` — PDF text extraction, watchlist row parsing, reference extraction, section summaries
- `src/newsletter_mcp/models.py` — parsed newsletter dataclasses
- `src/newsletter_mcp/database.py` — SQLAlchemy schema, runtime schema creation, newsletter DB
- `src/newsletter_mcp/business.py` — issue brief logic, watchlist summary, Daily continuity
- `src/newsletter_mcp/principle_evaluation.py` — deterministic Sunday principle scoring, historical/intelligence context
- `src/newsletter_mcp/server.py` — MCP tool definitions, newsletter save/refresh/publish, symbol catalog, exit schedule, publication contract

### Contract dependency on Schwab repo

Published artifacts: `watchlist.yaml`, `weekly_intelligence.json`, `issue_brief.md`, `publication_validation.json`, `publication_manifest.json`

## 3. Current Repo State (as of 2026-05-02)

- 31 tests passing
- DB: newsletters=18, watchlist_entries=260, strategy_principles=7, evaluation_runs=10
- Newsletter coverage: 2025-12-26 to 2026-04-24
- Latest published: 2026-04-24 (publication_run_id=43, tradeable=3/13)

## 4. Current Risks

1. Parser remains regex-heavy, narrative summaries noisy/OCR-sensitive
2. Gasoil is unresolved/untradeable for TOS
3. Schema evolution is runtime/additive, not migration-first
4. Daily persistence not yet started
5. Principle calibration active work (volatility_as_constraint can over-block)

## 5. Where We Left Off

Cross-repo hardening sprint complete. Sunday ingest/scoring/publication works. Daily continuity exists. File-based contract handoff works. At observation/calibration stage before adding persistence.

## 6. Next Priorities

1. Parser tests and validation hardening
2. Richer validation reporting
3. First Daily persistence layer (`portfolio_fit_reviews`)
4. Live calibration of principle scoring
5. Schema migrations
