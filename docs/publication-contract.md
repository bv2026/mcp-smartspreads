# Publication Contract

## Goal

Phase 1 publication turns the newsletter database into a weekly file-based handoff for downstream consumers such as the Schwab MCP server.

The database remains the system of record.
Everything in `published/` is a derived artifact.

## Output folder

Default output root:

- `published/`

Primary files:

- `published/watchlist.yaml`
- `published/weekly_intelligence.json`
- `published/issue_brief.md`
- `published/publication_validation.json`
- `published/publication_manifest.json`

## `watchlist.yaml`

Purpose:
- weekly machine-readable payload for downstream live-pricing workflows
- intended to be compatible with YAML consumers

Implementation note:
- the current publisher writes YAML-compatible JSON into the `.yaml` file
- this keeps the payload valid for standard YAML parsers while avoiding an extra dependency

Top-level fields:

- `schema_version`
- `publication_version`
- `published_at`
- `week_ended`
- `newsletter_id`
- `title`
- `principle_context`
- `source_file`
- `watchlist`

Each watchlist entry includes:

- `id`
- `entry_key`
- `name`
- `commodity_name`
- `spread_code`
- `symbol`
- `legs`
- `leg_details`
- `type`
- `spread_type`
- `spread_formula`
- `spread_expression`
- `spread_terms`
- `reporting_rule`
- `side`
- `section`
- `category`
- `enter_date`
- `exit_date`
- `valid_until`
- `win_pct`
- `avg_value`
- `avg_profit`
- `tier`
- `volatility_structure`
- `portfolio`
- `risk_level`
- `trade_quality`
- `ridx`
- `five_year_corr`
- `page_number`
- `action`
- `tradeable`
- `blocked_reason`
- `blocked_guidance`
- `decision_summary`
- `principle_scores`
- `principle_status`
- `principle_influences`
- `intelligence_context`
- `deferred_principles`
- `principle_evaluation_ts`
- `evaluation_version`

Key contract rules:

- `watchlist` only contains live watchlist entries
- `tradeable` and `blocked_reason` expose policy and platform constraints
- `principle_context` is the issue-level Phase 3 screening rollup
- per-entry principle fields expose publication-safe summaries, not raw internal reasoning
- `principle_influences` exposes which Weekly Intelligence or issue-change signals affected scoring
- `intelligence_context` exposes the compact issue-level context snapshot used during Sunday evaluation
- `entry_key` is stable across weeks so downstream systems can compare recurring ideas
- `section` / `section_name` is authoritative; downstream reports must not mix `intra_commodity` and `inter_commodity`
- `spread_expression` is the canonical report-ready expression for the whole row, e.g. `BUY (CZ26 - 2*CN27 + CZ27)`
- `side` applies to the complete `spread_formula`; reports should not split a row into independent directional leg trades

### `principle_context`

Current Phase 3 fields:

- `total_entries`
- `evaluated_entries`
- `tradeable_entries`
- `blocked_by_principles`
- `deferred_for_daily_review`
- `selectivity_ratio`
- `top_violations`

### Current implementation note

The current Phase 3 publisher is still metadata-backed at the publication edge, even though durable evaluation records now also exist in:

- `evaluation_runs`
- `principle_evaluations`
- `watchlist_decisions`

This is intentional for now.
The publication contract remains stable while the durable tables accumulate audit history beside it.

## `weekly_intelligence.json`

Purpose:
- structured issue-level intelligence payload
- richer context than the watchlist file

Top-level fields:

- `schema_version`
- `week_ended`
- `newsletter_id`
- `title`
- `issue_status`
- `source_file`
- `published_context`
- `issue_brief`
- `issue_delta`
- `watchlist_reference`

This file is intended for:

- daily workflow context
- issue comparison
- later rules-aware reporting

Phase 3 note:

- `weekly_intelligence.json` now carries the published principle rollup under `published_context.principle_context`
- richer per-entry principle detail continues to live in `watchlist.yaml`
- Weekly Intelligence now materially affects Sunday scoring and is reflected back into the watchlist contract through `principle_influences` and `intelligence_context`

## `issue_brief.md`

Purpose:
- human-readable issue brief for quick review

Contains:

- issue metadata
- executive summary
- watchlist counts
- change summary vs prior issue
- top reference rules

## `publication_manifest.json`

Purpose:
- auditable record of what was written in one publication run

Fields:

- `schema_version`
- `publication_run_id`
- `publication_version`
- `week_ended`
- `newsletter_id`
- `title`
- `published_at`
- `output_root`
- `files`
- `watchlist_count`

## `publication_validation.json`

Purpose:
- fast operator-facing validation artifact for the weekly handoff
- compact summary of whether the published contract looks usable before Daily review

Fields currently include:

- `schema_version`
- `publication_version`
- `published_at`
- `week_ended`
- `watchlist_count`
- `tradeable_count`
- `blocked_count`
- `entries_missing_symbols`
- `empty_legs_entries`
- `section_counts`
- `type_counts`
- `intermarket_entry_count`
- `manual_support_review_count`
- `manual_support_review_entries`
- `blocked_entries`
- `checks`

Current usage:

- review this file after publication before treating the handoff as trusted
- use it to catch missing legs, unresolved symbols, blocked entries, and support-limited entries quickly
- the weekly pipeline script also relies on this artifact during the cross-repo handoff check

## Database linkage

Each publish action creates:

- one `publication_runs` row
- one `publication_artifacts` row per written file

This allows:

- repeat publication without losing history
- artifact hash tracking
- traceability between DB state and generated files

## Current assumptions

- default publication target is the current issue-level `published/` folder
- re-publishing overwrites the current files on disk but still records a new DB publication run
- publication currently uses the existing draft brief and delta records generated during ingestion

## Next likely improvements

- archived per-issue publication folders
- stronger Schwab-specific watchlist shaping
- explicit approval step before publish
- publication diff reporting between versions
- Phase 3 threshold and recurrence calibration based on live dry-run feedback
- gradual shift from metadata-derived publication fields toward `watchlist_decisions` as the source of truth
