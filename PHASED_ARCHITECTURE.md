# Phased Architecture

## Overview

SmartSpreads should be designed as two connected workflows built on persistent memory:

- Sunday workflow
- Daily workflow

The key architectural decision is to avoid a single shared multi-owner SQLite database across both MCP servers.

Instead:

- Newsletter MCP owns newsletter intelligence history
- Schwab MCP owns live market and operational history
- integration happens through a published contract first, then controlled cross-system integration later

## Two workflows

### Sunday workflow

Purpose:
- ingest the new newsletter PDF
- validate and extract the weekly signal set
- generate intelligence
- publish approved outputs for the coming week

Sunday output is the new weekly context for the rest of the week.

### Daily workflow

Purpose:
- pull live positions and prices from Schwab MCP
- join them to the approved weekly intelligence
- produce the daily report, P/L view, and action plan

Daily output is operational guidance, not source extraction.

## Recommended system boundaries

### Newsletter MCP

Owns:
- PDF parsing
- weekly watchlist extraction
- watchlist reference extraction
- issue briefs
- issue deltas
- export bundle generation
- publication of approved weekly files
- newsletter intelligence database

### Schwab MCP

Owns:
- live quotes
- futures positions
- trade log
- account dashboard
- daily checks
- daily operational reporting
- operational database

## Phase 1

### Model

Newsletter DB + file-based publication

### Goal

Preserve all newsletter history while keeping the existing Schwab MCP workflow stable.

### Database ownership

Newsletter MCP becomes the system of record for:
- newsletter issues
- watchlist entries
- watchlist references
- issue briefs
- issue deltas
- parser runs
- publication runs

### Publication boundary

Newsletter MCP publishes approved weekly artifacts into a `published/` folder.

Recommended outputs:
- `published/watchlist.yaml`
- `published/weekly_intelligence.json`
- `published/issue_brief.md`
- `published/publication_manifest.json`

### Storage decision

Phase 1 is intentionally:
- DB-first internally
- file-published externally

This means:
- the relational newsletter DB is the source of truth
- published files are the approved handoff contract
- JSON is used as an export/publication format, not as the main historical store

The architecture is explicitly not:
- file-only as the system of record
- JSON-first / NoSQL-first as the primary intelligence memory layer

### Why this is the right first step

- preserves weekly memory
- avoids coupling the two MCPs too early
- keeps Sunday workflow human-reviewable
- lets Schwab MCP continue to operate with simple published inputs
- creates a clean audit trail

### Phase 1 completion status

Phase 1 is now functionally complete.

Completed outcomes:
- newsletter issues, watchlists, references, briefs, deltas, parser runs, and publication history are persisted in the newsletter DB
- business-layer issue summaries are stored and queryable
- approved weekly artifacts are published into the `published/` contract
- the file-based Schwab MCP consumes the published watchlist contract successfully
- one-shot refresh and republish is available through `refresh_and_publish_issue(...)`
- unit, integration, publication, and handoff E2E tests are in place and passing

What remains after Phase 1 is mainly polish:
- response ergonomics in the UI
- additional business-layer depth for daily workflow intelligence
- later cross-system learning in Phase 2

## Phase 2

### Model

Newsletter DB + Schwab DB integration

### Goal

Connect weekly intelligence history with daily portfolio operations and learning.

### Recommendation

Still keep two DBs, but allow controlled integration through:
- shared identifiers
- synced publication records
- selective import/sync jobs
- optional read-only cross-system access

Do not collapse both systems into one shared multi-owner SQLite database.

### Phase 2 value

- link daily actions to weekly intelligence
- persist daily action plans
- compare actual held positions with newsletter recommendations
- build learning loops across weeks and days

## Database philosophy

The newsletter database must be the memory layer.

Without that memory, the current workflow becomes:
- extract
- publish
- forget

With the database, the workflow becomes:
- extract
- normalize
- store
- compare
- learn
- publish

## Newsletter MCP as publisher

The publication artifact is not the source of truth.

`watchlist.yaml` should be treated as:
- an approved weekly publication artifact
- an integration payload for Schwab MCP

It should not be treated as the canonical historical store.

## Shared contract

The two MCPs should share a contract, not a writable DB.

### Minimum shared contract

- watchlist payload
- issue metadata
- issue brief
- publication version
- validity window

### Contract properties

- explicit
- versioned
- auditable
- easy to validate manually

## Sunday workflow target design

1. Drop PDF into `data/`
2. Ingest and parse into DB
3. Validate counts and extraction quality
4. Generate issue brief and weekly deltas
5. Review and approve
6. Publish weekly artifacts into `published/`
7. Export bundles and downstream files

## Daily workflow target design

1. Pull positions and prices from Schwab MCP
2. Read current approved weekly publication
3. Combine live data with weekly intelligence
4. Calculate daily P/L and operational changes
5. Produce daily report and action plan
6. In Phase 2, persist daily operational memory

## Architectural conclusions

### Phase 1

Build the weekly memory layer.

### Phase 2

Build the daily learning layer.

That ordering minimizes risk and gives immediate value.
