# Newsletter Intelligence Plan

## Objective

Build newsletter intelligence in two phases:

1. Phase 1 - Newsletter DB + file-based publication
2. Phase 2 - Newsletter DB + Schwab DB integration

The first phase focuses on weekly memory and publication.
The second phase focuses on daily operational learning.

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

### Phase 2 success

- daily decisions can be linked back to weekly intelligence
- daily operational memory is preserved
- the system can learn from both newsletters and portfolio actions
