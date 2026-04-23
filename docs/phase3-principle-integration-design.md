# Phase 3 Principle Integration Design

## Purpose

Phase 3 adds a principle-evaluation layer between weekly extraction and daily operations.

The goal is not to replace the existing two-workflow architecture.
The goal is to make the weekly watchlist more selective, more explainable, and more reusable during the Daily workflow.

After Phase 3:

- Newsletter MCP still owns weekly intelligence memory
- Schwab MCP still owns live pricing and operational state
- the publication contract stays file-based and human-reviewable
- principle evaluation becomes a first-class business-layer step before publication

## What Phase 3 Changes

Today the Sunday flow is effectively:

1. parse newsletter
2. store normalized records
3. generate summaries
4. publish approved weekly contract

Phase 3 changes that to:

1. parse newsletter
2. store normalized records
3. evaluate watchlist entries against durable strategy principles
4. generate summaries and blocked-trade explanations
5. review principle outcomes
6. publish approved weekly contract with principle context

The Daily flow then consumes:

- live positions and marks from Schwab MCP
- the approved weekly publication
- principle context and tradeability decisions from Newsletter MCP

## Current Implementation Status

Current live status in the repo:

- Sunday principle evaluation is running in `smartspreads-mcp`
- durable Phase 3 records exist in:
  - `evaluation_runs`
  - `principle_evaluations`
  - `watchlist_decisions`
- publication still uses the current metadata-backed bridge so the contract stays stable while durable audit history accumulates
- Weekly Intelligence now feeds Sunday scoring through structured context built from:
  - `issue_briefs`
  - `issue_deltas`
  - `watchlist_references`
- per-entry publication fields now include:
  - `principle_influences`
  - `intelligence_context`
- the Daily dry run now exposes a `Weekly Intelligence Signals Applied` section for validation

What is not yet complete:

- Daily does not yet re-score using the Sunday intelligence context
- overrides are not yet implemented
- publication has not yet shifted to derive directly from `watchlist_decisions`
- threshold calibration remains active work

## Design Goals

- make principle evaluation explicit rather than implicit in prompts
- keep doctrine separate from weekly signal storage
- preserve a reviewable publication artifact
- support concise explanation for blocked or downgraded ideas
- defer portfolio-fit decisions that require current holdings to the Daily workflow
- avoid coupling both MCPs through a shared writable database

## Non-Goals

- no shared multi-owner database across Newsletter MCP and Schwab MCP
- no raw strategy-book text embedded into `watchlist_entries`
- no fully autonomous freeform scoring without stored rationale
- no replacement of Schwab MCP pricing, P/L, or watchlist valuation logic

## Architectural Placement

Phase 3 belongs inside the Newsletter MCP business layer.

Recommended ownership:

- parser layer: extracts weekly facts from the newsletter
- strategy knowledge layer: stores durable doctrine and normalized principles
- principle evaluation layer: scores weekly entries against doctrine
- publication layer: publishes approved principle-aware artifacts
- daily alignment layer: combines approved weekly principle context with live portfolio state

This keeps weekly evaluation close to the database that already owns the memory and audit trail.

## Core Entities

### Existing entities reused

- `newsletters`
- `watchlist_entries`
- `watchlist_references`
- `issue_briefs`
- `issue_deltas`
- `strategy_documents`
- `strategy_sections`
- `strategy_principles`
- `publication_runs`

### New recommended entities

#### `principle_evaluations`

One row per watchlist entry per evaluation run.

Suggested fields:

- `id`
- `newsletter_id`
- `watchlist_entry_id`
- `evaluation_run_id`
- `principle_key`
- `score`
- `status`
  - `pass`
  - `fail`
  - `deferred`
  - `not_applicable`
- `rationale_text`
- `evidence_json`
- `guidance_text`
- `created_at`

This stores the atomic evaluation result for each principle.

#### `evaluation_runs`

One row per principle-evaluation pass for an issue.

Suggested fields:

- `id`
- `newsletter_id`
- `strategy_document_id`
- `evaluation_version`
- `status`
  - `draft`
  - `reviewed`
  - `approved`
- `summary_json`
- `created_at`
- `approved_at`

This gives a stable audit boundary between draft scoring and approved publication.

#### `watchlist_decisions`

One row per watchlist entry capturing the aggregated business outcome.

Suggested fields:

- `id`
- `watchlist_entry_id`
- `evaluation_run_id`
- `tradeable`
- `decision_band`
  - `green`
  - `yellow`
  - `red`
  - `blocked`
- `blocked_reason`
- `decision_summary`
- `review_notes`
- `created_at`

This is the business-layer result the publication service can export.

## Principle Taxonomy

Recommended v1 principle set:

- `structure_before_conviction`
- `selectivity_not_participation`
- `trade_selection_dominates_management`
- `volatility_as_constraint`
- `margin_as_survivability`
- `portfolio_fit_over_isolated_trade_appeal`
- `intercommodity_requires_extra_confirmation`

Notes:

- `portfolio_fit_over_isolated_trade_appeal` should usually be deferred at Sunday publication time because it depends on current holdings
- `intercommodity_requires_extra_confirmation` should be `not_applicable` for intra-commodity structures

## Evaluation Model

Each principle should produce both a score and a state.

Recommended rules:

- score range: `0.0` to `1.0`
- state is authoritative; score supports ranking and explanation
- `fail` means the principle actively blocked the idea
- `deferred` means the principle cannot be resolved without live portfolio context
- `not_applicable` means the principle is irrelevant for this structure

Recommended aggregation:

- hard-fail principles can block publication as tradeable
- soft-fail principles can downgrade the decision band without blocking
- deferred principles must be carried into the publication contract for Daily resolution

Example hard-fail principles:

- `structure_before_conviction`
- `margin_as_survivability`

Example deferred principle:

- `portfolio_fit_over_isolated_trade_appeal`

## Sunday Workflow Design

### Step 1: Parse and normalize

No change from current architecture.

### Step 2: Build candidate set

Select all current issue `watchlist_entries` and attach:

- newsletter facts
- reference/rule context
- normalized spread metadata
- strategy principle metadata

### Step 3: Run principle evaluation

For each watchlist entry:

1. evaluate all applicable principles
2. store one `principle_evaluations` row per principle
3. aggregate to one `watchlist_decisions` row

### Step 4: Generate review summaries

Produce business outputs such as:

- count of tradeable vs blocked ideas
- counts by blocking principle
- top high-conviction entries
- entries deferred for Daily portfolio-fit review

### Step 5: Human review

Operator reviews:

- blocked ideas
- surprising passes
- deferred portfolio-fit flags
- publication summary metrics

### Step 6: Publish approved contract

Publication must export the final approved decision, not raw intermediate reasoning.

## Publication Contract Extension

The current `watchlist.yaml` remains the bridge.
Phase 3 extends it rather than replacing it.

Recommended top-level additions:

```yaml
publication_version: "1.0"
principle_context:
  total_entries: 56
  tradeable_entries: 38
  blocked_by_principles: 18
  deferred_for_daily_review: 6
  selectivity_ratio: 0.68
  top_violations:
    structure_before_conviction: 12
    portfolio_fit_over_isolated_trade_appeal: 5
```

Recommended per-entry additions:

```yaml
tradeable: true
decision_band: "green"
blocked_reason: null
deferred_principles:
  - portfolio_fit_over_isolated_trade_appeal
principle_scores:
  structure_before_conviction: 0.92
  selectivity_not_participation: 0.88
  trade_selection_dominates_management: 0.95
  volatility_as_constraint: 0.78
  margin_as_survivability: 0.85
principle_status:
  portfolio_fit_over_isolated_trade_appeal: deferred
  intercommodity_requires_extra_confirmation: not_applicable
principle_influences:
  structure_before_conviction:
    - issue_delta.new_this_week
  volatility_as_constraint:
    - weekly_intelligence.volatility_emphasis
intelligence_context:
  highlighted_commodities:
    - soybeans
  risk_commodities:
    - soybean oil
decision_summary: "High-conviction structure with no pre-publication principle failure."
blocked_guidance: null
principle_evaluation_ts: "2026-04-16T10:30:00Z"
evaluation_version: "phase3-v1"
```

Contract rules:

- keep fields concise and operator-readable
- avoid publishing full chapter-level doctrine text
- publish decision summaries, not chain-of-thought
- preserve versioning so Daily consumers know how to interpret the schema
- publish influence tags and compact context snapshots, not raw reasoning transcripts

## Daily Workflow Integration

Schwab MCP remains the operational engine.
Newsletter MCP contributes decision context.

Daily flow impact:

1. Schwab MCP loads live positions, marks, and watchlist pricing
2. Daily workflow reads approved `watchlist.yaml`
3. open positions are aligned to weekly entries where possible
4. deferred principles are resolved using current portfolio state
5. Daily brief includes principle-aware action guidance

Examples of Daily use:

- suppress attention on entries already blocked at publication time
- highlight tradeable ideas that now fail `portfolio_fit`
- explain why an open position conflicts with current weekly doctrine
- prioritize exits when a position is both near exit date and misaligned with principle context

## Explanation Strategy

Phase 3 should improve explanation quality without becoming verbose.

Recommended explanation outputs:

- `decision_summary`: one sentence for the publication contract
- `blocked_guidance`: one sentence naming the failed principle and the corrective lens
- `daily_alignment_note`: one sentence added at Daily runtime when live portfolio state changes the interpretation

Good explanation style:

- specific
- framework-based
- short enough to survive repeated use in reports

Bad explanation style:

- book-length doctrine dumps
- generic "low quality" statements with no reason
- unstable freeform rationale that cannot be audited

## Service Boundaries

Recommended new services inside Newsletter MCP:

### `PrincipleEvaluationService`

Responsibilities:

- map entries to applicable principles
- score and status each principle
- persist `principle_evaluations`
- aggregate decisions

### `WatchlistDecisionService`

Responsibilities:

- derive `tradeable`
- assign `decision_band`
- generate concise decision summaries
- count violations for issue-level rollups

### `PrinciplePublicationAdapter`

Responsibilities:

- convert approved decision data into contract-safe YAML/JSON fields
- hide internal-only evaluation details
- enforce publication schema versioning

## Schema Ownership And MCP Boundary

Phase 3 schema ownership belongs to Newsletter MCP.

Recommended decision:

- `smartspreads-mcp` owns the schema, migrations, repository methods, and write path for:
  - `evaluation_runs`
  - `principle_evaluations`
  - `watchlist_decisions`
- `schwab-mcp` consumes approved publication artifacts only
- `schwab-mcp` does not write directly into Newsletter MCP tables in v1

Why this boundary matters:

- it preserves the current two-MCP architecture
- it avoids turning the Newsletter database into a shared writable store
- it keeps Sunday doctrine evaluation auditable in one system of record
- it lets Daily logic evolve independently without hidden cross-system coupling

Recommended interaction model:

- Sunday:
  - `smartspreads-mcp` evaluates principles and stores durable records
  - `smartspreads-mcp` publishes approved decision summaries to `watchlist.yaml` and `weekly_intelligence.json`
- Daily:
  - `schwab-mcp` reads the publication contract plus live account state
  - `schwab-mcp` resolves live-only principles such as portfolio fit and margin pressure in its own workflow
  - `schwab-mcp` reports Daily conclusions without writing back into Newsletter MCP tables

If Daily persistence becomes necessary later, add it as a separate Daily-side store or an explicit import/sync step.
Do not introduce direct shared DB writes across MCPs unless the architecture is intentionally revised.

## Review and Audit Model

Every publication should make it possible to answer:

- which principles were applied
- which ones failed
- which ones were deferred
- which evaluation version produced the result
- when the issue was approved

This is important because principle tuning will likely evolve.

If the scoring model changes, we should be able to compare:

- issue outcomes by evaluation version
- principle hit rates over time
- operator overrides versus raw evaluation

## Rollout Plan

### Phase 3A: Persistence and scoring

Build:

- `evaluation_runs`
- `principle_evaluations`
- `watchlist_decisions`
- `PrincipleEvaluationService`

Output can stay internal at first.

### Phase 3B: Publication contract

Extend:

- `watchlist.yaml`
- `weekly_intelligence.json`

Add principle-aware summaries and per-entry decision fields.

### Phase 3C: Daily resolution

Add Daily logic for:

- deferred portfolio-fit resolution
- principle-aware action notes
- blocked-idea suppression in operational views
- reuse of Sunday `principle_influences` and `intelligence_context` as Daily review context without breaking the MCP boundary

### Phase 3D: Learning loop

Later, compare:

- principle decisions
- actual held positions
- realized outcomes from trade log and snapshots

This belongs after the first publication contract is stable.

## Open Questions

- should operator overrides be stored separately from raw evaluation output
- should `portfolio_fit` stay fully deferred, or should Sunday publication include a lightweight placeholder score
- should decision bands be issue-relative or based on fixed thresholds
- should `weekly_intelligence.json` carry richer rationale than `watchlist.yaml`, or should both stay equally concise

## Recommended Next Implementation Order

1. add the new Phase 3 tables and repository methods
2. implement `PrincipleEvaluationService` with deterministic status rules
3. generate issue-level principle rollups for review
4. extend `watchlist.yaml` publication schema
5. update Daily report generation to consume deferred principle context

This sequence preserves the current system while making Phase 3 incremental and testable.

## Operator Notes For The Next Newsletter Cycle

For the next weekly issue, especially the April 24, 2026 newsletter:

1. treat the Sunday publish as both an operational step and a calibration checkpoint
2. review `principle_context` counts before trusting the watchlist downstream
3. spot-check a few entries for non-empty `principle_influences` so you know Weekly Intelligence was actually used
4. compare blocked ideas against your own judgment rather than assuming the current thresholds are final
5. rerun the dry run after publication and confirm the report mirrors the published counts and influence tags

If the new issue suddenly collapses to a very low tradeable count, that is a signal to review thresholds and intelligence adjustments before treating the output as final doctrine.

## Pause Point And Next Plan

This is the current recommended stopping point before the next implementation wave.

What is working now:

- Sunday ingest, scoring, publication, and Schwab-side contract reading are working end to end
- Weekly Intelligence is materially affecting Sunday scoring
- Daily continuity is working in the business layer and dry run
- Sunday-to-Daily drift is now visible for portfolio-fit conflicts
- the current system is ready for live observation on the next Sunday and Daily runs

What we should do before adding more persistence:

1. run the full Sunday workflow on the next newsletter issue
2. run multiple Daily sessions against that published issue
3. collect calibration metrics from real use
4. confirm which gaps are operationally painful versus merely architecturally incomplete

Recommended first persistence target after observation:

- `portfolio_fit_reviews`

Why this is first:

- it answers why a Sunday-blocked idea appears in the portfolio anyway
- it answers why a Sunday-approved idea was skipped or downgraded in Daily review
- it captures operator intent without requiring full Daily run persistence yet

Recommended next implementation order after Apr 22:

1. design and add `portfolio_fit_reviews`
2. wire Daily continuity output into that table
3. support operator decision updates such as `skip`, `enter_anyway`, and `already_entered`
4. only then decide whether broader Daily persistence is still necessary

Current pending TODOs:

- calibrate `volatility_as_constraint`, which currently appears too aggressive
- formalize Daily `portfolio_fit_over_isolated_trade_appeal` as a clearer gate beyond dry-run reporting
- investigate Sunday-blocked ideas that still appear in live positions, especially Gold
- shift publication gradually toward `watchlist_decisions` as the source of truth
- add override support once the first Daily persistence layer exists
