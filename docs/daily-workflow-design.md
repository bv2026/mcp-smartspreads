# Daily Workflow Design

## Purpose

The Daily workflow is the operational layer that runs during market hours.

It should:
- reuse `schwab-smartspreads-file` for imported futures positions, live pricing, spread values, and current P/L
- reuse `newsletter-mcp` for weekly intelligence, rules, issue context, and exit interpretation
- let Claude combine both into a daily markdown report and action plan

The Daily workflow should not rebuild the existing Schwab MCP operational calculations.

## Design goals

1. Reuse the existing Schwab MCP toolchain rather than replacing it.
2. Use Newsletter MCP as the weekly intelligence and history layer.
3. Keep the operator workflow simple:
   - one canonical TOS CSV
   - one canonical TOS screenshot PNG
   - freshness checked by file timestamp
4. Produce one consistent markdown report contract.
5. Make action recommendations explicit, especially around exit dates and watchlist conflicts.
6. Leave optional daily persistence for Phase 2, rather than forcing a second DB immediately.

## Inputs

### 1. Schwab operational inputs

Owned by `schwab-smartspreads-file`.

- canonical TOS account statement CSV in the Schwab MCP `config/` folder
- canonical TOS screenshot PNG in the Schwab MCP `config/` folder
- live or latest-available market data for:
  - open-position legs
  - published watchlist legs
- current published watchlist contract consumed from Newsletter MCP output

### 2. Newsletter intelligence inputs

Owned by `newsletter-mcp`.

- current published issue metadata
- issue brief
- watchlist entries
- watchlist reference rules
- issue delta versus prior issue
- newsletter-aligned exit dates
- business-layer themes, risks, and opportunities

## Canonical daily file convention

To keep the workflow simple, Daily operations should use one current CSV and one current PNG.

Recommended convention:

- `config/tos-statement.csv`
- `config/tos-screenshot.png`

The system should treat these as the current daily inputs and use file last-modified timestamps to confirm they were updated before the Daily run.

This design intentionally avoids:
- dated file trees
- accumulating raw operational screenshots/CSVs in folders
- asking the operator to manage multiple file variants for one trading day

## Ownership model

### Schwab MCP owns

- TOS statement ingestion
- screenshot-supported operational validation context
- imported current futures positions
- live leg pricing
- open-position spread values
- open-position P/L
- live published watchlist pricing
- operational watchlist/position comparisons
- stream health and market-data status
- seed daily markdown structure

### Newsletter MCP owns

- weekly intelligence memory
- issue brief
- watchlist reference rules
- issue delta
- weekly themes, risks, and opportunities
- published weekly contract
- exit-date interpretation and newsletter context

### Claude owns

- orchestration across both MCPs
- synthesis into the final daily report
- action-plan prioritization
- narrative interpretation of conflicts, exits, and opportunities

## Daily workflow sequence

### Step 1. Freshness check

Before doing any analysis:

- confirm `tos-statement.csv` exists
- confirm `tos-screenshot.png` exists
- confirm both files were updated recently enough for the current Daily run

If freshness fails, the Daily workflow should stop and ask for updated inputs.

### Step 2. Import open positions from Schwab MCP

Use `schwab-smartspreads-file` to:
- read the imported TOS positions
- normalize futures positions
- identify open positions only

This is the operational source of truth for futures positions.

### Step 3. Price the open positions

Use Schwab MCP to:
- fetch live or latest-available prices for each leg
- calculate current spread values
- calculate current position P/L

This should remain fully on the Schwab side.

### Step 4. Price the published watchlist

Use Schwab MCP to:
- load the current published watchlist contract
- fetch live or latest-available prices for each watchlist leg
- calculate current watchlist spread values

This supports:
- live monitoring of current candidate trades
- conflict analysis
- actionability analysis

### Step 5. Pull weekly intelligence from Newsletter MCP

Use `newsletter-mcp` to retrieve:
- current published issue summary
- issue brief
- watchlist reference rules
- issue delta
- exit-date interpretation
- current week themes, risks, and opportunities

### Step 6. Map open positions to newsletter context

For each open position:
- map it to the current newsletter watchlist when possible
- determine whether it aligns with current intra/inter ideas
- determine the newsletter-derived exit date
- flag if the position is:
  - aligned
  - unaligned
  - legacy carryover
  - missing from current weekly watchlist

### Step 7. Generate action priorities

Action priority should consider:
- exits due today
- exits due soon
- positions with the highest operational risk
- watchlist conflicts
- high-conviction current opportunities
- blocked ideas that should be ignored
- stale or weak data-quality conditions

### Step 8. Render the daily markdown report

Claude should generate the final report from the structured outputs of the previous steps.

## Daily report contract

The current Claude-generated markdown should be treated as the seed contract and formalized into these sections.

### Required sections

1. `Run status`
   - current published issue
   - TOS CSV freshness
   - screenshot freshness
   - stream/market-data health

2. `Live watchlist values`
   - current live pricing for the published watchlist
   - section-aware if useful (`intra_commodity`, `inter_commodity`)

3. `Imported open positions`
   - positions sourced from the TOS statement
   - normalized contract/spread presentation

4. `Open-position spread values and P/L`
   - spread value
   - current P/L
   - supporting leg context when needed

5. `Exit schedule`
   - open positions mapped to newsletter-derived exit dates
   - due today
   - due soon
   - overdue or unmatched where applicable

6. `Watchlist alignment and conflicts`
   - positions aligned with the current watchlist
   - positions not aligned
   - conflicting exposures
   - blocked ideas that should not be acted on

7. `Weekly intelligence context`
   - current week themes
   - major risks
   - notable opportunities
   - important interpretation rules

8. `Portfolio summary`
   - high-level operational picture
   - concentration, urgency, notable changes, and key exposures

9. `Action plan`
   - top 3 actions for today
   - exit-driven actions
   - monitoring actions
   - ignore/hold actions where relevant

## Action-plan contract

The action plan should always include:

- `why now`
  the reason the action matters today

- `what to review`
  the specific position, watchlist idea, or conflict

- `timing`
  especially exit-date urgency

- `supporting context`
  brief reference to the weekly intelligence or live pricing condition

### Priority order

Recommended priority order:

1. exits due today
2. exits due soon
3. high-risk open positions
4. watchlist conflicts
5. strongest current watchlist opportunities
6. lower-priority monitoring items

## Failure handling

The Daily workflow should explicitly handle:

- stale TOS CSV
- stale TOS screenshot
- missing positions from TOS import
- partial or missing live market data
- unmatched positions that cannot be linked to newsletter entries
- blocked watchlist ideas that should not be surfaced as candidates

If data quality is weak, the report should say so clearly and downgrade confidence.

## What not to build

Daily design should not:

- rebuild TOS ingestion inside Newsletter MCP
- rebuild live spread/P&L calculations inside Newsletter MCP
- move newsletter intelligence into Schwab MCP
- require a second operational DB in Phase 1
- require dated screenshot/CSV archives as part of the normal workflow

## Phase 1 vs Phase 2

### Phase 1

- file-based operational state on the Schwab side
- Newsletter DB as the weekly intelligence system of record
- Claude-generated daily markdown as the main daily artifact

### Phase 2

Optional persistence may include:
- `daily_runs`
- `position_snapshots`
- `watchlist_quote_snapshots`
- `daily_portfolio_summaries`
- `daily_action_plans`
- `daily_reports`

Phase 2 should add memory, not change the core division of responsibilities.

## Minimal implementation plan

### Step 1

Formalize this report contract and prompt contract.

### Step 2

Identify the exact Schwab MCP tools needed for:
- imported positions
- watchlist pricing
- spread pricing
- current P/L
- stream status

### Step 3

Design a reusable Daily prompt that:
- checks input freshness
- gathers Schwab operational facts
- gathers Newsletter intelligence
- produces the markdown report and action plan

### Step 4

Only after the workflow is trusted, decide what daily artifacts should be persisted in Phase 2.
