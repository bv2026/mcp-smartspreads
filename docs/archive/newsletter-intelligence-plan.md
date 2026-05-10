# Newsletter Intelligence Plan

## Objective

Build newsletter intelligence in two phases:

1. Phase 1 - Newsletter DB + file-based publication
2. Phase 2 - Newsletter DB + Schwab DB integration

The first phase focuses on weekly memory and publication.
The second phase focuses on daily operational learning.

## Chosen storage model

The project will use:

- relational DB for canonical newsletter intelligence history
- published files for downstream integration
- JSON as an artifact/export format where useful

The project will not use:

- file-only storage as the source of truth
- JSON/NoSQL-first storage as the primary intelligence memory layer

Reason:
- newsletter intelligence is historical, comparable, and relational
- downstream integration still benefits from simple published files
- this hybrid model preserves memory without tightly coupling the systems

## Two data domains

The architecture should be understood as two separate data domains:

### Newsletter domain

- owned by `Newsletter MCP`
- DB-first in Phase 1
- holds weekly intelligence history and publication state

### TOS / operational domain

- owned by `Schwab MCP`
- file-based in Phase 1
- uses the canonical TOS account statement CSV, the canonical TOS screenshot, published newsletter contract files, and live market queries

This means the practical Phase 1 model is:

- `Newsletter MCP -> Newsletter DB`
- `Schwab MCP -> file-based operational state`

Only in Phase 2 does the Schwab side need to become a more formal operational DB, if daily persistence and learning require it.

## Phase 1 scope

### Deliverables

- Newsletter intelligence SQLite database
- Published weekly artifact contract
- Sunday workflow implementation around persistent storage
- Issue briefs
- Weekly deltas
- Approved publication process

### Phase 1 database

Core tables:

- `newsletter_issues`
- `watchlist_entries`
- `watchlist_references`
- `issue_briefs`
- `issue_deltas`
- `parser_runs`
- `publication_runs`

### Phase 1 published artifacts

- `published/watchlist.yaml`
- `published/weekly_intelligence.json`
- `published/issue_brief.md`
- `published/publication_manifest.json`

### Phase 1 Sunday workflow

1. Ingest PDF
2. Validate issue structure
3. Extract watchlist + reference + key sections
4. Generate intelligence
5. Compare to prior issue
6. Approve
7. Publish
8. Export

### Phase 1 benefits

- no loss of newsletter history
- stable Schwab MCP integration
- easier debugging and audit
- immediate support for historical learning later

## Phase 2 scope

### Deliverables

- Daily operational persistence
- Weekly-to-daily linkage
- Daily action-plan memory
- Cross-system learning outputs

### Phase 2 data goals

- persist daily snapshots
- persist daily action plans
- link open positions to approved weekly publication
- compare actual positions to newsletter intelligence

### Candidate Phase 2 tables

- `daily_runs`
- `position_snapshots`
- `watchlist_quote_snapshots`
- `daily_portfolio_summaries`
- `daily_action_plans`
- `daily_position_analysis`

### Daily workflow minimum requirements

The Daily workflow should assume:

- the TOS account statement is downloaded during market hours and overwrites the canonical CSV in the Schwab MCP `config/` folder
- the TOS screenshot also overwrites the canonical PNG used for validation/context
- file timestamps are checked to confirm both inputs were updated for the current Daily run
- Schwab MCP tools ingest positions from the TOS statement
- Schwab MCP tools provide live or latest-available market data for each open-position leg
- Schwab MCP tools also provide live or latest-available market data for each published watchlist leg
- Schwab MCP remains the calculation layer for open-position spread values, watchlist spread values, and P/L
- Newsletter MCP provides weekly intelligence, rules, exits, and interpretation
- each open position must be mapped to its newsletter-aligned exit date
- exit-date urgency must be included in the daily action plan
- historical newsletter matches should be used for still-open legacy carryovers when the exact spread is not in the current issue

This is necessary because the Schwab API cannot be relied on to return futures positions for this workflow.

### Reuse, do not rebuild

Daily workflow should reuse the existing Schwab MCP operational implementation.

That means:
- do not rebuild TOS statement ingestion in Newsletter MCP
- do not rebuild spread-value and P/L calculations in Newsletter MCP
- do not rebuild live watchlist spread pricing in Newsletter MCP
- do not replace the current Schwab-side daily markdown structure unless there is a strong reason

Instead, Daily workflow design should:
- keep Schwab MCP as the operational engine
- use Newsletter MCP as the weekly intelligence and history layer
- let Claude combine both into the final daily report and action plan

### Seed daily report contract

The current Claude-generated daily markdown should be treated as the seed contract for Daily workflow v1.

Current sections already provide a strong starting point:
- live watchlist values
- open positions from TOS CSV
- spread value calculations
- complete open-position P/L
- changes vs yesterday
- watchlist conflicts
- exit schedule
- portfolio summary
- current portfolio status
- next actions

Exit dates for open positions are required fields in the Daily workflow, and they must feed directly into the generated action plan.

Current implementation status:
- newsletter-history-backed exit matching is now working for current-watchlist and legacy-carryover positions
- broker-normalized symbol matching and quantity-aware butterfly matching are in place
- manual fallback dates for truly unmatched positions are still optional future work, not a blocker for the current Daily flow

## Implementation plan

### Step 1: Foundation

- define newsletter DB schema
- define published file contract
- define issue and publication identifiers

Step 1 schema design is documented in [`phase1-database-schema.md`](./phase1-database-schema.md).

### Step 2: Weekly intelligence

- improve issue parsing
- add issue briefs
- add issue deltas
- add reference extraction cleanup

### Step 3: Publication flow

- generate `watchlist.yaml` from DB
- generate `weekly_intelligence.json`
- generate `issue_brief.md`
- generate publication manifest

The publication contract is documented in [`publication-contract.md`](./publication-contract.md).

### Step 4: Workflow integration

- update Sunday workflow around DB + publication
- keep daily workflow consuming published files

### Step 5: Phase 2 preparation

- define daily schema
- define linking keys between weekly and daily records
- define sync/import boundary with Schwab MCP

## Risks and design guardrails

### Avoid

- one shared writable SQLite DB for both MCPs
- making `watchlist.yaml` the source of truth
- direct daily dependence on raw PDF parsing

### Prefer

- single ownership of each DB
- explicit publication contracts
- versioned artifacts
- approval before publication

## Success criteria

### Phase 1 success

- weekly newsletters are fully stored historically
- weekly intelligence is queryable later
- published outputs are generated from DB
- Schwab MCP can continue using approved weekly files
- one-shot refresh and republish is available for issue maintenance

### Phase 1 current status

Phase 1 is complete.

Implemented in Phase 1:
- persistent newsletter intelligence DB
- business-layer issue briefs and deltas
- published contract files
- file-based Schwab MCP handoff
- local testing harnesses
- end-to-end handoff validation

Phase 1 is complete enough to move into Daily workflow and Phase 2 design work.

### Phase 2 success

Phase 2 is complete for the currently intended Daily-operational scope.

Implemented in Phase 2:
- canonical Daily input model using one TOS CSV and one TOS screenshot
- reuse of Schwab MCP for positions, live/latest pricing, spread values, and P/L
- newsletter-history-backed exit schedule resolution for open positions
- broker-root-aware symbol matching and quantity-aware butterfly matching
- higher-level `get_daily_exit_schedule(...)` Daily tool
- strategy/doctrine ingestion from the Smart Spreads strategy manual
- updated Daily prompts and usage guidance for Claude

Deferred to Phase 3:
- validated YTD portfolio rollups
- snapshot-based "vs yesterday" state
- persisted Daily reports, action plans, and learning memory
- deeper strategy-aware commentary inside weekly and Daily generated outputs

- daily decisions can be linked back to weekly intelligence
- daily operational memory is preserved
- the system can learn from both newsletters and portfolio actions
