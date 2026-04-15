# Newsletter MCP Prompt Guide

This file provides suggested prompts for using the newsletter MCP consistently.

## Ingestion prompts

### Ingest all pending newsletters

```text
Ingest all newsletter PDFs currently in the data folder and tell me how many new issues were added.
```

### Ingest one newsletter

```text
Ingest the April 10, 2026 newsletter PDF and return the issue date, number of watchlist rows, and whether a watchlist reference page was captured.
```

## Query prompts

### Get a watchlist

```text
Give me the watchlist for the April 10, 2026 newsletter and include the watchlist reference rules.
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
Export the April 10, 2026 intra-commodity watchlist to CSV.
```

### Export one issue package

```text
Export the March 27, 2026 inter-commodity watchlist as a package with rows.csv and reference.json.
```

### Export a consolidated CSV

```text
Export a consolidated intra-commodity CSV for all newsletters from December 26, 2025 through April 10, 2026.
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
Use newsletter-mcp only. Ingest any pending newsletter PDFs, tell me which issue dates were added, and flag anything suspicious about watchlist counts, missing reference rules, or section classification.
```

### Sunday issue brief

```text
Use newsletter-mcp only. Build the weekly intelligence brief for the April 10, 2026 newsletter. Include:
- issue summary
- intra-commodity summary
- inter-commodity summary
- notable themes
- notable additions/removals versus the prior issue
- important watchlist reference rules that affect interpretation
```

### Sunday publish workflow

```text
Use newsletter-mcp only. Publish the April 10, 2026 issue into the published folder, then confirm the publication version, manifest path, and watchlist row count.
```

### Sunday export workflow

```text
Use newsletter-mcp only. Export the April 10, 2026 issue as:
- intra-commodity CSV
- inter-commodity CSV
- issue package with reference metadata
and tell me where the files were written.
```

### Sunday end-to-end review

```text
Use newsletter-mcp first, then schwab-smartspreads-file. Republish the latest newsletter issue, confirm the published watchlist metadata, then verify the file-based Schwab MCP can see the published week and use that watchlist for live monitoring.
```

## Daily workflow prompts

Use these on trading days after the Sunday publication step is complete.

### Daily morning brief

```text
Use newsletter-mcp and schwab-smartspreads-file. Give me a morning trading brief that combines:
- the current published newsletter week
- today’s live futures/watchlist context
- my current futures positions
- the highest-priority actions for today

Use newsletter-mcp for weekly intelligence and rules. Use schwab-smartspreads-file for live positions, watchlist pricing, and stream status.
```

### Daily action plan

```text
Use newsletter-mcp and schwab-smartspreads-file. Create today’s action plan using the latest published newsletter intelligence plus current Schwab data. Include:
- open positions that need attention
- watchlist ideas that are currently actionable
- exits or dates that are approaching
- conflicts between current positions and the newsletter watchlist
- the top 3 actions I should consider today
```

### Daily watchlist check

```text
Use schwab-smartspreads-file first and newsletter-mcp second. Price the current published watchlist, then explain the results in the context of this week’s newsletter reference rules and section summaries.
```

### Daily position review

```text
Use schwab-smartspreads-file and compare current futures positions against the current published newsletter watchlist. Then use newsletter-mcp to explain whether each position is aligned with this week’s intra/inter ideas and rules.
```

### Daily comparison against live workflow

```text
Use schwab-smartspreads-live and schwab-smartspreads-file. Compare the original live Schwab MCP workflow with the file-based published-watchlist workflow and tell me whether the file-based version is using the expected published issue and watchlist rows.
```

## Prompting guidance

- Prefer naming the exact issue date.
- Specify `intra_commodity` or `inter_commodity` when export scope matters.
- Ask for reference metadata when downstream interpretation is important.
- Ask for consolidated exports when you want one CSV spanning multiple issues.
- For Sunday work, start with `newsletter-mcp` and treat it as the source of truth for ingestion, publication, and weekly intelligence.
- For Daily work, use `schwab-smartspreads-file` for live file-based monitoring and `newsletter-mcp` for interpretation, rules, and week-level context.
- Use `schwab-smartspreads-live` only when you explicitly want to compare the legacy/live workflow against the file-based Phase 1 workflow.
