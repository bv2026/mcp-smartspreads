# Business Layer Design

## Purpose

The business layer sits above parsing and storage.

Its job is to turn extracted newsletter data into reusable intelligence for:
- Sunday approval and publication
- Daily operational interpretation
- future reporting and learning

The business layer should not replace the parser or the database.
It should consume normalized DB records and produce higher-level intelligence objects.

## Inputs

The business layer will read from the newsletter DB:

- `newsletters`
- `newsletter_sections`
- `watchlist_entries`
- `watchlist_references`
- `issue_briefs`
- `issue_deltas`
- `parser_runs`
- `publication_runs`

It may also read published artifacts when validating the publication contract, but the DB remains the source of truth.

## Outputs

The business layer should produce:

- issue brief
- section briefs
- watchlist summaries
- change summaries versus prior issue
- action candidates
- publication validation signals
- later, daily alignment summaries against live Schwab data

## Design principles

### 1. DB-first

The business layer should compute from normalized DB records, not directly from raw PDFs.

### 2. Derived, not destructive

Business intelligence should be stored as derived outputs and should not overwrite raw extracted fields.

### 3. Comparable across weeks

All business outputs should support issue-over-issue comparisons.

### 4. Rules-aware

Interpretation should use `watchlist_references` where relevant.

### 5. Publication-aware

The business layer should understand which issue/version has been approved and published.

## Core business entities

### IssueBrief

Purpose:
- executive summary for one issue

Contents:
- issue summary
- intra summary
- inter summary
- key themes
- key risks
- notable additions/removals
- publication status context

### WatchlistSummary

Purpose:
- summarize the live weekly watchlist in business terms

Contents:
- counts by section
- counts by category
- counts by trade quality / risk level
- blocked vs tradeable counts
- notable high-conviction ideas

### IssueDeltaSummary

Purpose:
- describe how the current issue changed versus the prior one

Contents:
- added ideas
- removed ideas
- changed side
- changed dates
- changed quality/risk metadata
- changed blocked/tradeable status

### ThemeSignal

Purpose:
- capture recurring market themes at the issue level

Examples:
- energy bias
- grains concentration
- volatility-sensitive setups
- seasonal concentration

This can begin as a lightweight derived object before it becomes its own table.

### ActionCandidate

Purpose:
- create a business-layer bridge between weekly intelligence and later daily operations

Examples:
- new trade to review
- blocked idea to ignore
- high-conviction idea with near-term date relevance
- issue requiring manual validation

## Business services

Recommended service boundaries:

### `IssueBriefService`

Builds the issue-level brief from:
- newsletter summary
- section summaries
- watchlist summaries
- issue delta

### `WatchlistSummaryService`

Builds structured watchlist summaries from:
- section
- category
- quality / risk
- tradeability / blocked rules

### `IssueDeltaService`

Builds business-friendly change summaries from raw issue deltas.

### `PublicationService`

Validates and publishes the approved issue:
- current issue metadata
- publication version
- output contract
- reference integrity

### `DailyAlignmentService` later

Compares:
- current published issue
- live positions
- live watchlist pricing

This belongs after the weekly business layer is stable.

## Recommended implementation order

### Step 1

Formalize `IssueBriefService`.

This is the highest-value first business object because it helps both Sunday review and later Daily interpretation.

### Step 2

Add `WatchlistSummaryService`.

This gives structured counts and signal summaries without needing live market integration.

### Step 3

Add `IssueDeltaSummary`.

This makes weekly change intelligence easier to consume operationally.

### Step 4

Add `ActionCandidate` generation.

This creates the first bridge toward the Daily workflow.

### Step 5

Design `DailyAlignmentService`.

This should happen only after the weekly business layer is trusted.

## Immediate next recommendation

Build Business Layer v1 around:

1. `IssueBriefService`
2. `WatchlistSummaryService`
3. `IssueDeltaSummary`

That gives a useful business layer without yet depending on live Schwab integration.
