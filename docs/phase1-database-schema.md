# Phase 1 Database Schema

## Goal

Phase 1 establishes the newsletter intelligence database as the system of record for weekly memory.

This schema is designed to:

- preserve every newsletter issue historically
- preserve the live watchlist exactly as published in the PDF
- preserve the reference rules needed to interpret the watchlist
- store generated intelligence such as briefs and deltas
- support an approval and publication workflow for downstream file-based integration

## Design approach

Phase 1 should extend the existing schema rather than replace it.

Current tables already in active use:

- `newsletters`
- `newsletter_sections`
- `watchlist_entries`
- `watchlist_references`

Phase 1 adds the intelligence and publication layers on top:

- `parser_runs`
- `issue_briefs`
- `issue_deltas`
- `publication_runs`
- `publication_artifacts`

## Naming note

The business concept is a `newsletter_issue`, but the current code and schema already use `newsletters`.

For Phase 1:

- keep the physical table name `newsletters`
- treat it as the canonical issue table
- defer any rename to a later migration only if it becomes necessary

That keeps the implementation incremental and avoids breaking existing MCP tools.

## Phase 1 entity map

### 1. `newsletters`

Purpose:
- one row per newsletter issue version
- canonical weekly source record

Current role:
- already stores source file, file hash, raw text, summary, and issue date

Phase 1 additions recommended:
- `issue_code` text nullable
- `issue_version` text nullable
- `issue_status` text not null default `ingested`
- `page_count` integer nullable
- `source_modified_at` timestamptz nullable
- `approved_at` timestamptz nullable
- `published_at` timestamptz nullable
- `supersedes_newsletter_id` bigint nullable

Key constraints:
- unique `source_file`
- unique `file_hash`
- do not keep `week_ended` globally unique once corrected `A` or `B` issues are supported
- instead, move toward a uniqueness rule such as `(week_ended, coalesce(issue_version, 'base'))`

Important note:
- the current schema makes `week_ended` unique
- Phase 1 should plan a migration to support corrected issues without losing history

Suggested statuses:
- `ingested`
- `validated`
- `approved`
- `published`
- `superseded`
- `failed`

### 2. `newsletter_sections`

Purpose:
- one row per extracted newsletter section
- stores raw text plus summary text for non-watchlist content

Phase 1 additions recommended:
- `section_type` text nullable
- `extraction_confidence` numeric nullable
- `parser_run_id` bigint nullable
- `metadata` jsonb not null default `{}`

Suggested section types:
- `watchlist_page`
- `watchlist_reference`
- `macro_commentary`
- `margin_summary`
- `trade_calendar`
- `strategy`
- `article`
- `other`

Why it matters:
- this table becomes the anchor for future structured extraction of trade calendar, margin, and strategy sections

### 3. `watchlist_entries`

Purpose:
- one row per live watchlist trade
- primary screening, export, and publication layer

Current schema is already strong and should remain the core trade table.

Phase 1 additions recommended:
- `entry_key` text nullable
- `tradeable` boolean nullable
- `blocked_reason` text nullable
- `parser_run_id` bigint nullable
- `publication_state` text nullable
- `metadata` jsonb not null default `{}`

`entry_key` should be a stable normalized identifier derived from:
- week ended
- section name
- commodity name
- spread code
- side

This will help with:
- weekly deltas
- publication manifests
- Phase 2 linkage to daily workflows

Suggested `publication_state` values:
- `candidate`
- `approved`
- `excluded`
- `published`

### 4. `watchlist_references`

Purpose:
- one row per issue for the overview/reference page
- keeps rules separate from live trades

Current schema already fits Phase 1 well.

Phase 1 additions recommended:
- `parser_run_id` bigint nullable
- `reference_version` text nullable
- `metadata` jsonb not null default `{}`

This table will later support:
- report generation
- rules-aware CSV exports
- entry and exit interpretation
- P/L calculation guidance

### 5. `parser_runs`

Purpose:
- one row per ingestion or parsing attempt
- provenance and confidence layer

Recommended columns:
- `id` bigserial primary key
- `newsletter_id` bigint not null references `newsletters(id)` on delete cascade
- `parser_version` text not null
- `run_started_at` timestamptz not null default now
- `run_completed_at` timestamptz nullable
- `status` text not null
- `page_count_detected` integer nullable
- `pages_parsed` integer nullable
- `watchlist_entry_count` integer nullable
- `section_count` integer nullable
- `warning_count` integer not null default 0
- `warnings_json` jsonb not null default `[]`
- `metrics_json` jsonb not null default `{}`

Suggested statuses:
- `running`
- `completed`
- `completed_with_warnings`
- `failed`

Why this table matters:
- makes ingestion auditable
- supports validation reporting
- provides the confidence layer needed before publication

### 6. `issue_briefs`

Purpose:
- one issue-level intelligence brief per newsletter issue

Recommended columns:
- `id` bigserial primary key
- `newsletter_id` bigint not null unique references `newsletters(id)` on delete cascade
- `parser_run_id` bigint nullable references `parser_runs(id)` on delete set null
- `brief_status` text not null default `draft`
- `headline` text nullable
- `executive_summary` text not null
- `key_themes_json` jsonb not null default `[]`
- `notable_risks_json` jsonb not null default `[]`
- `notable_opportunities_json` jsonb not null default `[]`
- `watchlist_summary_json` jsonb not null default `{}`
- `change_summary_json` jsonb not null default `{}`
- `created_at` timestamptz not null default now
- `updated_at` timestamptz not null default now

Suggested `brief_status` values:
- `draft`
- `reviewed`
- `approved`

This is the core table for newsletter intelligence output in Phase 1.

### 7. `issue_deltas`

Purpose:
- store structured changes between one issue and the prior comparable issue

Recommended columns:
- `id` bigserial primary key
- `newsletter_id` bigint not null unique references `newsletters(id)` on delete cascade
- `previous_newsletter_id` bigint nullable references `newsletters(id)` on delete set null
- `delta_status` text not null default `generated`
- `added_entries_json` jsonb not null default `[]`
- `removed_entries_json` jsonb not null default `[]`
- `changed_entries_json` jsonb not null default `[]`
- `summary_text` text nullable
- `created_at` timestamptz not null default now

What belongs here:
- additions
- removals
- side changes
- date window changes
- quality or risk changes
- volatility structure changes

### 8. `publication_runs`

Purpose:
- one row per approval or publish attempt for downstream artifacts

Recommended columns:
- `id` bigserial primary key
- `newsletter_id` bigint not null references `newsletters(id)` on delete cascade
- `publication_version` text not null
- `status` text not null
- `published_by` text nullable
- `published_at` timestamptz nullable
- `output_root` text nullable
- `manifest_json` jsonb not null default `{}`
- `notes` text nullable
- `created_at` timestamptz not null default now

Suggested statuses:
- `draft`
- `approved`
- `published`
- `failed`
- `superseded`

Why this table matters:
- separates parsing from approval
- makes publication explicit and auditable
- supports regeneration without losing history

### 9. `publication_artifacts`

Purpose:
- track the exact files written for a publication run

Recommended columns:
- `id` bigserial primary key
- `publication_run_id` bigint not null references `publication_runs(id)` on delete cascade
- `artifact_type` text not null
- `file_path` text not null
- `file_hash` text nullable
- `row_count` integer nullable
- `metadata` jsonb not null default `{}`

Suggested artifact types:
- `watchlist_yaml`
- `weekly_intelligence_json`
- `issue_brief_md`
- `publication_manifest_json`
- `rows_csv`
- `reference_json`

This table is optional for the very first implementation pass, but it is highly recommended because it turns publication into something traceable.

## Relationship model

Core relationships:

- `newsletters` 1 -> many `newsletter_sections`
- `newsletters` 1 -> many `watchlist_entries`
- `newsletters` 1 -> 1 `watchlist_references`
- `newsletters` 1 -> many `parser_runs`
- `newsletters` 1 -> 1 `issue_briefs`
- `newsletters` 1 -> 1 `issue_deltas`
- `newsletters` 1 -> many `publication_runs`
- `publication_runs` 1 -> many `publication_artifacts`

## Phase 1 minimal implementation set

If we want the smallest useful Phase 1 slice, implement these first:

1. extend `newsletters`
2. add `parser_runs`
3. add `issue_briefs`
4. add `issue_deltas`
5. add `publication_runs`

`publication_artifacts` can follow immediately after if we want full publication traceability.

## Suggested indexes

### `newsletters`

- index on `(week_ended desc)`
- index on `(issue_status, week_ended desc)`
- unique index on `(week_ended, coalesce(issue_version, 'base'))` after migration

### `newsletter_sections`

- index on `(newsletter_id, section_type)`
- index on `(parser_run_id)`

### `watchlist_entries`

- index on `(newsletter_id, section_name)`
- index on `(section_name, enter_date, exit_date)`
- index on `(trade_quality)`
- index on `(category)`
- index on `(entry_key)`
- index on `(publication_state)`

### `watchlist_references`

- unique index on `(newsletter_id)`
- index on `(parser_run_id)`

### `parser_runs`

- index on `(newsletter_id, run_started_at desc)`
- index on `(status)`

### `issue_briefs`

- unique index on `(newsletter_id)`

### `issue_deltas`

- unique index on `(newsletter_id)`
- index on `(previous_newsletter_id)`

### `publication_runs`

- index on `(newsletter_id, created_at desc)`
- index on `(status, published_at desc)`

### `publication_artifacts`

- index on `(publication_run_id)`
- index on `(artifact_type)`

## Migration strategy

Phase 1 should be implemented through additive migrations where possible.

Recommended order:

1. add new nullable columns to `newsletters`
2. add new nullable metadata fields to existing tables
3. create new Phase 1 intelligence tables
4. backfill `issue_status` and parser provenance for existing issues
5. later relax `week_ended` uniqueness once corrected issue versioning is implemented

Important:
- do not break existing `get_watchlist` and export tooling while introducing Phase 1 tables
- keep the current MCP behavior stable during migration

## Canonical source-of-truth boundary

In Phase 1:

- the database is the system of record
- `watchlist.yaml` is a publication artifact
- publication files are derived outputs, not primary storage

That boundary is essential because the purpose of Phase 1 is to stop losing weekly memory.

## Recommendation

Implement Phase 1 schema in two passes:

### Pass 1

- additive intelligence tables
- approval and publication tracking
- no breaking changes to current watchlist ingestion

### Pass 2

- corrected issue version support
- richer section typing and confidence fields
- publication artifact tracking

This keeps the design strong while minimizing migration risk.
