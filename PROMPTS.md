# SmartSpreads MCP Prompt Guide

This file provides suggested prompts for using the smartspreads-mcp consistently.

## Quiet mode prefix

Use this at the top of any Claude prompt when you want a cleaner final answer without tool chatter:

```text
Use only the needed MCP tools. Do not show tool discovery, function schemas, internal steps, or MCP details. Just use the tools and return the final answer.
```

## Ingestion prompts

### Ingest all pending newsletters

```text
Ingest all newsletter PDFs currently in the data folder and tell me how many new issues were added.
```

### Ingest one newsletter

```text
Ingest the April 24, 2026 newsletter PDF and return the issue date, number of watchlist rows, and whether a watchlist reference page was captured.
```

## Query prompts

### Get a watchlist

```text
Give me the watchlist for the April 24, 2026 newsletter and include the watchlist reference rules.
```

### Get only intra or inter rows

```text
Give me only the intra-commodity watchlist for March 27, 2026.
```

```text
Give me only the inter-commodity watchlist for January 16, 2026.
```

### Get watchlist reference rules

```text
Show me the watchlist reference page details for the February 6, 2026 issue, including column definitions and trading rules.
```

## Export prompts

### Export one issue to CSV

```text
Export the April 24, 2026 intra-commodity watchlist to CSV.
```

### Export one issue package

```text
Export the March 27, 2026 inter-commodity watchlist as a package with rows.csv and reference.json.
```

### Export a consolidated CSV

```text
Export a consolidated intra-commodity CSV for all newsletters from December 26, 2025 through April 24, 2026.
```

### Export a full bundle

```text
Generate the full export bundle for all sample newsletters into the export folder.
```

## Reporting prompts

### Ask for section-specific analysis

```text
Summarize the intra-commodity watchlist trends across the last six issues.
```

### Ask for rules-aware analysis

```text
Use the watchlist reference rules and explain how entry and exit dates should be interpreted in this issue before summarizing the exported trades.
```

### Ask for mixed historical handling

```text
Compare older portfolio/risk-level issues with newer trade-quality issues and explain the schema differences in a report-ready way.
```

## Sunday workflow prompts

Use these after a new weekly PDF has been dropped into `data/`.

### Sunday intake and validation

```text
Use smartspreads-mcp only. Ingest any pending newsletter PDFs, tell me which issue dates were added, and flag anything suspicious about watchlist counts, missing reference rules, or section classification.
```

### Sunday issue brief

```text
Use smartspreads-mcp only. Build the weekly intelligence brief for the April 24, 2026 newsletter. Include:
- issue summary
- intra-commodity summary
- inter-commodity summary
- notable themes
- notable additions/removals versus the prior issue
- important watchlist reference rules that affect interpretation
```

### Sunday publish workflow

```text
Use smartspreads-mcp only. Publish the April 24, 2026 issue into the published folder, then confirm the publication version, manifest path, and watchlist row count.
```

### Sunday export workflow

```text
Use smartspreads-mcp only. Export the April 24, 2026 issue as:
- intra-commodity CSV
- inter-commodity CSV
- issue package with reference metadata
and tell me where the files were written.
```

### Sunday end-to-end review

```text
Use smartspreads-mcp first, then schwab-smartspreads-file. Republish the latest newsletter issue, confirm the published watchlist metadata, then verify the file-based Schwab MCP can see the published week and use that watchlist for live monitoring.
```

### Sunday E2E metrics check

```text
Run the full Sunday SmartSpreads workflow for the newest newsletter issue.

I want:
- ingest
- issue summary review
- watchlist review
- reference-rule review
- publish or refresh-publish
- a short validation summary

Please report:
- total entries
- tradeable count
- blocked count
- deferred count
- selectivity ratio
- top blocking principles
- 3 example entries showing Weekly Intelligence influence
- anything that looks miscalibrated
```

### Sunday trust check

```text
Review the published Sunday result and tell me whether I should trust it operationally.

Please focus on:
- blocked ideas that may be false negatives
- passes that may be too generous
- whether Weekly Intelligence seems meaningfully used
- whether the selectivity looks sane for this issue

Keep the answer short and practical.
```

## Daily workflow prompts

Use these on trading days after the Sunday publication step is complete.

### Daily morning brief

```text
Use only schwab-smartspreads-file and smartspreads-mcp. Do not show tool discovery, function schemas, internal steps, or MCP details. Just use the tools and return the final answer.

Use schwab-smartspreads-file first to get today's futures positions and current watchlist pricing. Then use smartspreads-mcp get_daily_exit_schedule with that futures-positions result. I have already overwritten the canonical TOS statement CSV and canonical TOS screenshot in the Schwab MCP config area, and both timestamps are current. Give me a morning trading brief that combines:
- the current published newsletter week
- today's live futures/watchlist context
- my imported current futures positions
- newsletter-history-backed exit dates for open positions
- the highest-priority actions for today

Use smartspreads-mcp for weekly intelligence, rules, and exit interpretation. Use get_daily_exit_schedule as the preferred exit-resolution path. Use schwab-smartspreads-file for imported positions, live watchlist pricing, live spread pricing, and stream status.
```

### Daily action plan

```text
Use only schwab-smartspreads-file and smartspreads-mcp. Do not show tool discovery, function schemas, internal steps, or MCP details. Just use the tools and return the final answer.

Use schwab-smartspreads-file first to get today's futures positions and current watchlist pricing. Then use smartspreads-mcp get_daily_exit_schedule with that futures-positions result. I have already overwritten the canonical TOS statement CSV and canonical TOS screenshot in the Schwab MCP config area, and both timestamps are current. Create today's action plan using the latest published newsletter intelligence plus current Schwab data. Include:
- open positions that need attention
- watchlist ideas that are currently actionable
- exits due soon or due today
- conflicts between current positions and the newsletter watchlist
- legacy-carryover positions whose exit dates come from older newsletters
- the top 3 actions I should consider today
```

### Daily watchlist check

```text
Use schwab-smartspreads-file first and smartspreads-mcp second. Price the current published watchlist legs and spreads, then explain the results in the context of this week's newsletter reference rules, section summaries, and entry/exit interpretation.
```

### Daily position review

```text
Use schwab-smartspreads-file and compare imported current futures positions against the current published newsletter watchlist. Then use smartspreads-mcp to explain whether each position is aligned with this week's intra/inter ideas, rules, and exit dates. If a position is not in the current issue, search newsletter history for a legacy-carryover match before marking its exit as unknown.
```

### Daily exit schedule check

```text
Use only schwab-smartspreads-file and smartspreads-mcp. Do not show tool discovery, function schemas, internal steps, or MCP details. Just use the tools and return the final answer.

Use schwab-smartspreads-file first to get today's futures positions. Then use smartspreads-mcp get_daily_exit_schedule with that result. I have already overwritten the canonical TOS statement CSV and canonical TOS screenshot in the Schwab MCP config area, and both timestamps are current. Build today's exit schedule from newsletter history, including:
- current-week exact matches
- legacy-carryover matches from older newsletters
- quantity-aware butterfly matches
- urgency buckets

Call out any positions that still have no newsletter-history match. Also note any valid symbols that are manual-leg-only or known no-tick cases.
```

### Daily exit schedule via higher-level tool

```text
Use only schwab-smartspreads-file and smartspreads-mcp. Do not show tool discovery, function schemas, internal steps, or MCP details. Just use the tools and return the final answer.

Use schwab-smartspreads-file first to get today's futures positions, then use smartspreads-mcp get_daily_exit_schedule with that result. Do not search past conversations. Respond only with:
- matched positions and exit dates
- unmatched positions
- manual-leg-only symbols
- no-tick symbols
Keep it concise.
```

### Daily comparison against live workflow

```text
Use schwab-smartspreads-live and schwab-smartspreads-file. Compare the original live Schwab MCP workflow with the file-based published-watchlist workflow and tell me whether the file-based version is using the expected published issue and watchlist rows.
```

### Daily E2E run

```text
Run the Daily SmartSpreads workflow using the current published week and current Schwab/TOS inputs.

I want:
- run status
- watchlist conflicts
- Daily continuity from Sunday
- Sunday passes that now need Daily override
- top 3 actions for today

Please explicitly call out:
- any Sunday-approved ideas degraded by portfolio overlap
- any still-ready Sunday-approved ideas
- any blocked ideas I should ignore
```

### Daily metrics check

```text
Give me simple Daily metrics from the current run.

Please report:
- Sunday passes still ready
- Sunday passes degraded by Daily review
- Sunday blocked ideas still blocked
- overlap-driven overrides
- manual-leg limitations
- no-tick limitations

Then give a 1-paragraph assessment of whether the Daily bridge looks useful.
```

### Calibration check

```text
Based on the current Sunday and Daily outputs, what looks most miscalibrated?

Please identify:
- the principle most likely over-blocking
- the principle most likely under-informing Daily review
- 2 concrete adjustments you would test next

Do not redesign the system. Just focus on calibration.
```

### Persistence readiness

```text
Based on the Sunday and Daily runs we just observed, what should we persist first?

Please choose between:
- Daily continuity runs
- operator overrides
- published decision snapshots
- portfolio-fit review records

Then explain why in a few sentences.
```

## Weekend runbook

Use these in order for the cleanest Phase 3 testing loop:

1. run the Sunday E2E metrics check
2. run the Sunday trust check
3. run the Daily E2E run
4. run the Daily metrics check
5. run the calibration check
6. run the persistence readiness check

## Prompting guidance

- Prefer naming the exact issue date.
- Specify `intra_commodity` or `inter_commodity` when export scope matters.
- Ask for reference metadata when downstream interpretation is important.
- Ask for consolidated exports when you want one CSV spanning multiple issues.
- For Sunday work, start with `smartspreads-mcp` and treat it as the source of truth for ingestion, publication, and weekly intelligence.
- For Daily work, use `schwab-smartspreads-file` for live file-based monitoring and `smartspreads-mcp` for interpretation, rules, week-level context, and newsletter-history-backed exit matching.
- Prefer `smartspreads-mcp.get_daily_exit_schedule` over manually composing butterfly quantities or flat leg rows.
- If Claude starts dumping tool chatter, add: `Do not show tool discovery, function schemas, internal steps, or MCP details. Just use the tools and return the final answer.`
- Use `schwab-smartspreads-live` only when you explicitly want to compare the legacy/live workflow against the file-based Phase 1 workflow.
- When Daily output includes VIX-family or other no-tick/manual-leg symbols, ask Claude to distinguish between:
  - valid symbol but manual-leg-only workflow
  - valid symbol but no-tick stream condition
  - actually blocked / not tradeable symbols
