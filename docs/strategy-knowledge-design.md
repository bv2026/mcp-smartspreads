# Strategy Knowledge Design

## Purpose

The strategy PDF should become a separate doctrine layer above the weekly newsletter layer.

It should answer:
- why the framework prefers certain spread structures
- how trade quality should be interpreted
- how volatility, margin, and portfolio fit should be understood
- how weekly newsletter ideas should be explained in framework terms

It should not replace weekly newsletter parsing.

The design goal is:
- weekly newsletters = current signals
- strategy manual = durable principles

## Source document

Current source:
- `C:\work\SmartSpreads\reference\strategy\The Smart Spreads Strategy S.pdf`

Observed document structure:
- title page and front matter
- contents page with clean chapter layout
- Part I: foundations of commodity spread behavior
- Part II: trade quality and philosophy
- Part III: trade selection
- Part IV/V: execution, margin, stops, profit-taking
- Part VI: framework, hierarchy, inter-commodity constraints
- appendices and glossary

This is a strong structure for section-level extraction and principle normalization.

## Design principles

### 1. Separate doctrine from weekly signals

Do not mix raw strategy text into `watchlist_entries` or weekly issue tables.

Instead:
- newsletter tables hold weekly facts
- strategy tables hold durable framework knowledge

### 2. DB-first, not PDF-at-runtime

The strategy PDF should be ingested once into structured records.

Runtime queries should use:
- normalized sections
- normalized principles
- derived summaries

Not repeated raw PDF parsing.

### 3. Explain, do not duplicate

The strategy layer should improve:
- issue brief explanations
- blocked-trade explanations
- daily action-plan reasoning

It should not duplicate every paragraph of the book in weekly outputs.

### 4. Principle-based retrieval

The main retrieval target should be strategy principles, not raw chapter dumps.

Example principle objects:
- `structure_before_conviction`
- `selectivity_not_participation`
- `margin_as_survivability_constraint`
- `volatility_as_constraint`
- `portfolio_fit`
- `trade_quality_hierarchy`
- `intercommodity_conditional_edge`

### 5. Quote sparingly, summarize heavily

The strategy layer should support:
- concise summaries
- references back to chapter/section/page ranges
- low-friction explanation in Sunday and Daily workflows

## Recommended schema

### `strategy_documents`

One row per strategy source document.

Suggested fields:
- `id`
- `title`
- `source_file`
- `file_hash`
- `document_type`
  - example: `strategy_manual`
- `author`
- `version_label`
- `published_year`
- `page_count`
- `raw_text`
- `summary_text`
- `metadata_json`
- `created_at`
- `updated_at`

### `strategy_sections`

One row per structural section or chapter.

Suggested fields:
- `id`
- `strategy_document_id`
- `part_number`
- `part_title`
- `chapter_number`
- `chapter_title`
- `section_label`
- `page_start`
- `page_end`
- `heading_path`
- `body_text`
- `summary_text`
- `keywords_json`
- `metadata_json`
- `created_at`
- `updated_at`

Notes:
- `heading_path` should store normalized hierarchy like:
  - `Part II > Chapter 8 > Smart Spreads Philosophy`
- `keywords_json` can hold extracted anchors like:
  - `trade_quality`
  - `volatility`
  - `portfolio_fit`

### `strategy_principles`

One row per normalized principle.

Suggested fields:
- `id`
- `strategy_document_id`
- `strategy_section_id`
- `principle_key`
- `principle_title`
- `category`
- `priority`
- `summary_text`
- `guidance_text`
- `applies_to_json`
- `examples_json`
- `anti_patterns_json`
- `metadata_json`
- `created_at`
- `updated_at`

Suggested categories:
- `philosophy`
- `trade_selection`
- `trade_quality`
- `volatility`
- `margin`
- `execution`
- `profit_taking`
- `stop_management`
- `portfolio_construction`
- `intercommodity`
- `failure_modes`

Suggested `applies_to_json` values:
- `issue_brief`
- `daily_brief`
- `blocked_trade_explanation`
- `action_plan`
- `portfolio_fit`

### `strategy_examples` later

Optional later table if we want explicit worked examples.

Suggested fields:
- `id`
- `strategy_principle_id`
- `strategy_section_id`
- `example_title`
- `example_text`
- `example_type`
- `metadata_json`

This is useful later, but not required for v1.

## Recommended ingestion flow

### Step 1: Register the document

Create a `strategy_documents` row with:
- metadata
- file hash
- page count
- raw extracted text

### Step 2: Parse structure

Use the contents page and chapter headings to segment the document into:
- parts
- chapters
- appendices

Create `strategy_sections` rows for each chapter.

### Step 3: Summarize sections

Generate concise section summaries, for example:
- 3-6 bullet themes per chapter
- 1 short paragraph summary

### Step 4: Normalize principles

Create a curated set of strategy principles from the extracted sections.

This should be a deliberate normalization step, not fully automatic freeform extraction.

Recommended v1 target:
- 15 to 25 principles

Examples:
- structure before conviction
- selectivity over participation
- trade selection dominates trade management
- volatility is a structural design variable
- margin is a survivability constraint
- inter-commodity spreads require extra structural caution
- blocked trades should be interpreted through survivability and framework integrity

### Step 5: Add retrieval paths

Expose MCP tools such as:
- `list_strategy_sections()`
- `get_strategy_section(chapter_number=...)`
- `list_strategy_principles(category=...)`
- `get_strategy_principle(principle_key=...)`

These can come after the schema and ingestion are stable.

## How the strategy layer should be used

### Sunday workflow

Use strategy principles to improve issue interpretation.

Examples:
- explain why Tier 1 matters in framework terms
- explain why blocked trades are blocked beyond raw RIDX thresholds
- explain why a volatility structure matters

### Daily workflow

Use strategy principles to improve operational explanations.

Examples:
- why overlapping grains exposure should be treated carefully
- why a manual-leg VIX workflow is operationally different from a native spread
- why margin should be treated as survivability, not opportunity

### Publication

The strategy layer should not be injected directly into `watchlist.yaml`.

Instead, it should enrich:
- `weekly_intelligence.json`
- issue brief generation
- daily markdown explanations

## First v1 principle set

Recommended first extraction set:
- `structure_before_conviction`
- `selectivity_not_participation`
- `spreads_are_primary_not_secondary`
- `seasonality_is_structural_not_predictive`
- `trade_selection_dominates_trade_management`
- `volatility_as_constraint`
- `margin_as_survivability_constraint`
- `portfolio_fit_over_isolated_trade_appeal`
- `intercommodity_conditional_edge`
- `structural_vs_cyclical_breakdown`
- `execution_discipline_preserves_edge`
- `profit_taking_without_abandoning_structure`
- `stops_contain_structural_failure`
- `trade_quality_hierarchy`
- `system_integrity_over_frequency`

## Recommended implementation order

### Step 1

Add schema for:
- `strategy_documents`
- `strategy_sections`
- `strategy_principles`

### Step 2

Ingest the strategy PDF into:
- document metadata
- section/chapter rows

### Step 3

Create a curated v1 principle set.

### Step 4

Use the principle set in:
- issue brief generation
- blocked-trade explanation
- daily action-plan explanation

### Step 5

Add MCP query tools for strategy retrieval.

## What to defer

Do not build these yet:
- full semantic search
- vector retrieval
- example-heavy quote browsing
- automatic principle extraction without human review
- direct coupling between strategy doctrine and Schwab-side operational data

Those can come later if needed.

## Recommendation

The strategy PDF should be incorporated as a doctrine layer now, but only in a structured, sectioned, principle-based way.

The right v1 approach is:
- ingest once
- section cleanly
- normalize principles
- use those principles to enrich Sunday and Daily explanations

That gives SmartSpreads:
- weekly intelligence
- daily operations
- and now, durable strategy doctrine

without collapsing those three layers into one.
