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

Key contract rules:

- `watchlist` only contains live watchlist entries
- `tradeable` and `blocked_reason` expose policy and platform constraints
- `entry_key` is stable across weeks so downstream systems can compare recurring ideas

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
