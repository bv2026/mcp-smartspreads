# Symbol Catalog Design

## Purpose

The current hardcoded root-symbol mapping in `newsletter_mcp` is too brittle for long-term use.

We need a data-driven normalization layer that answers three separate questions:

1. What contract roots and products does the newsletter use?
2. What futures products does Schwab actually offer?
3. How should newsletter roots map to Schwab/TOS roots, including policy blocks and confidence?

This design proposes two catalog tables stored in the Newsletter DB.

## Why this is needed

Today, publication logic relies on a hardcoded `ROOT_SYMBOL_MAP` in code.

That causes problems such as:
- symbol mapping bugs like `MW -> /MWE`
- inability to distinguish:
  - not offered by Schwab
  - offered by Schwab but unsupported in streaming
  - offered by Schwab but blocked by policy
- difficulty auditing symbol decisions
- difficulty updating mappings when newsletter conventions or Schwab offerings change

The correct place for this logic is the database, not a fixed dictionary in code.

## Table 1: `schwab_futures_catalog`

Purpose:
- authoritative catalog of Schwab/TOS futures products available to the workflow
- imported from the Schwab futures symbol CSV

Example source:
- `futures-tradelog - Sheet13.csv`

### Suggested columns

- `id` bigserial primary key
- `symbol_root` text not null unique
  - examples: `/GC`, `/VX`, `/VXM`, `/ZW`
- `display_name` text not null
- `exchange` text nullable
- `category` text nullable
- `multiplier` numeric nullable
- `minimum_tick` text nullable
- `settlement_type` text nullable
- `trading_hours` text nullable
- `options_tradable` boolean nullable
- `is_micro` boolean not null default false
- `streaming_supported` boolean nullable
- `contract_notes` text nullable
- `source_file` text nullable
- `source_updated_at` timestamptz nullable
- `is_active` boolean not null default true
- `metadata` jsonb not null default `{}`

### Why this table matters

This table becomes the source of truth for:
- what Schwab claims to offer
- which TOS root is valid
- multiplier and product metadata
- eventual streaming support overrides

## Table 2: `newsletter_commodity_catalog`

Purpose:
- authoritative catalog of the symbols and commodity roots used by the newsletter
- imported from the newsletter's Commodity Details page

### Suggested columns

- `id` bigserial primary key
- `newsletter_root` text not null unique
  - examples: `MW`, `KW`, `VX`, `FC`
- `commodity_name` text not null
- `exchange` text nullable
- `category` text nullable
- `contract_notes` text nullable
- `default_side_notes` text nullable
- `preferred_schwab_root` text nullable
  - example: `/ZW`
- `alternate_schwab_roots_json` jsonb not null default `[]`
- `is_tradeable_by_policy` boolean nullable
- `policy_block_reason` text nullable
- `mapping_confidence` text nullable
  - examples: `high`, `medium`, `low`
- `mapping_notes` text nullable
- `source_issue_week` date nullable
- `source_page_number` integer nullable
- `is_active` boolean not null default true
- `metadata` jsonb not null default `{}`

### Why this table matters

This table becomes the source of truth for:
- what the newsletter means by each commodity root
- which Schwab/TOS root we intend to use
- whether the symbol is blocked by policy
- how confident we are in the mapping

## Crosswalk behavior

The two-table design keeps the crosswalk inside `newsletter_commodity_catalog` for now.

That means:
- `newsletter_root` identifies the newsletter contract family
- `preferred_schwab_root` points to the intended Schwab/TOS root
- `alternate_schwab_roots_json` captures fallback or variant roots

This is sufficient for the current phase.

If needed later, a third table can be introduced:
- `newsletter_schwab_symbol_map`

But that is not necessary yet.

## Publication workflow with catalogs

When publishing a weekly watchlist:

1. Parse each contract code into:
   - newsletter root
   - month code
   - year code
2. Look up the newsletter root in `newsletter_commodity_catalog`
3. Read:
   - `preferred_schwab_root`
   - `policy_block_reason`
   - `mapping_confidence`
4. Validate that `preferred_schwab_root` exists in `schwab_futures_catalog`
5. Build the final contract symbol
6. Publish:
   - `tos_symbol`
   - `tradeable`
   - `blocked_reason`
   - `mapping_confidence`
   - optional mapping metadata

## Benefits

This design fixes or improves:
- Spring Wheat / `MW` mapping
- policy blocking
- tradeability validation
- auditability of mapping decisions
- long-term maintenance of symbol coverage
- future classification of:
  - offered by Schwab
  - blocked by policy
  - not supported by streaming

## How this replaces `ROOT_SYMBOL_MAP`

Today:
- `ROOT_SYMBOL_MAP` in code decides the Schwab root

After this change:
- `newsletter_commodity_catalog` becomes the first lookup
- `schwab_futures_catalog` validates the Schwab root and supplies product metadata

So the code path becomes:

1. `newsletter_root`
2. `newsletter_commodity_catalog.preferred_schwab_root`
3. validate against `schwab_futures_catalog.symbol_root`
4. publish final `tos_symbol`

The code should only keep minimal fallback behavior, not the full mapping table.

## Recommended implementation order

1. Add both tables to the schema
2. Create importers for:
   - Schwab symbol CSV
   - newsletter Commodity Details page
3. Backfill initial catalog records
4. Change publication logic to use the DB-backed mapping
5. Retire the hardcoded root map once the catalogs are trusted
