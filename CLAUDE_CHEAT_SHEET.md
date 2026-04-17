# Claude Prompt Cheat Sheet

This is the short version of the prompt guides.

Use this when you want fast, reliable prompts for:
- Sunday newsletter workflow
- Daily trading workflow
- issue/intelligence checks
- strategy-doctrine queries

---

## General rules

- Name the exact issue date when possible.
- For Sunday work, start with `newsletter-mcp`.
- For Daily work, start with `schwab-smartspreads-file`, then use `newsletter-mcp`.
- Prefer `get_daily_exit_schedule(...)` over asking Claude to manually infer exits.
- If stream marks are stale, ask Claude to downgrade confidence in pricing-based conclusions.
- Use the strategy layer when you want "why this matters" instead of just "what the newsletter says."
- When Claude gets noisy, add: `Do not show tool discovery, function schemas, internal steps, or MCP details. Just use the tools and return the final answer.`

### Quiet mode prefix

Paste this at the top of any Claude prompt when you want a cleaner answer:

```text
Use only the needed MCP tools. Do not show tool discovery, function schemas, internal steps, or MCP details. Just use the tools and return the final answer.
```

---

## Sunday workflow

### 1. Ingest new newsletter(s)

```text
Use newsletter-mcp only. Ingest any pending newsletter PDFs, tell me which issue dates were added, and flag anything suspicious about watchlist counts, missing reference rules, or section classification.
```

### 2. Weekly intelligence brief

```text
Use newsletter-mcp only. Build the weekly intelligence brief for the April 10, 2026 newsletter. Include:
- issue summary
- intra-commodity summary
- inter-commodity summary
- notable themes
- notable additions/removals versus the prior issue
- important watchlist reference rules that affect interpretation
```

### 3. Publish the approved week

```text
Use newsletter-mcp only. Publish the April 10, 2026 issue into the published folder, then confirm the publication version, manifest path, and watchlist row count.
```

### 4. End-to-end weekly handoff

```text
Use newsletter-mcp first, then schwab-smartspreads-file. Republish the latest newsletter issue, confirm the published watchlist metadata, then verify the file-based Schwab MCP can see the published week and use that watchlist for live monitoring.
```

---

## Daily workflow

Use these after:
- `tos-statement.csv` is overwritten in the Schwab MCP `config/` folder
- `tos-screenshot.png` is overwritten in the Schwab MCP `config/` folder

### 1. Best Daily morning brief

```text
Use only schwab-smartspreads-file and newsletter-mcp. Do not show tool discovery, function schemas, internal steps, or MCP details. Just use the tools and return the final answer.

Use schwab-smartspreads-file first to get stream status, futures positions, and watchlist pricing. Then use newsletter-mcp get_daily_exit_schedule with the futures-positions result, and use get_issue_summary for weekly context. Give me a concise morning brief with:
- stream/data quality status
- open positions ordered by nearest exit
- current watchlist opportunities
- conflicts or overlaps
- top 3 actions for today

If marks are stale, clearly downgrade confidence in pricing-based conclusions, but keep newsletter-derived exit dates as valid.
```

### 2. Daily action plan

```text
Use only schwab-smartspreads-file and newsletter-mcp. Do not show tool discovery, function schemas, internal steps, or MCP details. Just use the tools and return the final answer.

Use schwab-smartspreads-file first to get today's futures positions and current watchlist pricing. Then use newsletter-mcp get_daily_exit_schedule with that futures-positions result. Create today's action plan using the latest published newsletter intelligence plus current Schwab data. Include:
- open positions that need attention
- watchlist ideas that are currently actionable
- exits due soon or due today
- conflicts between current positions and the newsletter watchlist
- legacy-carryover positions whose exit dates come from older newsletters
- the top 3 actions I should consider today
```

### 3. Exit schedule only

```text
Use only schwab-smartspreads-file and newsletter-mcp. Do not show tool discovery, function schemas, internal steps, or MCP details. Just use the tools and return the final answer.

Use schwab-smartspreads-file first to get today's futures positions, then use newsletter-mcp get_daily_exit_schedule with that result. Do not search past conversations. Respond only with:
- matched positions and exit dates
- unmatched positions
- manual-leg-only symbols
- no-tick symbols
Keep it concise.
```

### 4. Position alignment review

```text
Use schwab-smartspreads-file first, then newsletter-mcp. Compare my imported current futures positions against the current published newsletter watchlist. Explain whether each position is aligned with this week's intra/inter ideas, rules, and exit dates. If a position is not in the current issue, use newsletter history for a legacy-carryover match before marking its exit as unknown.
```

### 5. Watchlist pricing check

```text
Use schwab-smartspreads-file first and newsletter-mcp second. Price the current published watchlist legs and spreads, then explain the results in the context of this week's newsletter reference rules, section summaries, and entry/exit interpretation.
```

---

## Intelligence checks

### Stored issue brief

```text
Use get_issue_summary for 2026-04-10 once. Read issue_brief from that result and give me a concise plain-English summary of the stored issue brief.
```

### Top themes

```text
Use get_issue_summary for 2026-04-10 once. Read issue_brief only and give me the top 3 stored themes in 3 short bullets. Do not restate raw JSON.
```

### Risks and opportunities

```text
Use get_issue_summary for 2026-04-10 once. Read issue_brief only and give me 3 notable risks and 3 notable opportunities in concise bullets. Do not restate raw JSON.
```

### Stored vs published parity

```text
Check whether the stored issue brief and published weekly_intelligence for 2026-04-10 agree on themes, risks, opportunities, watchlist summary, and change summary. Respond with only mismatches or say they match.
```

---

## Strategy layer

### Import strategy manual

```text
Use newsletter-mcp import_strategy_manual, then tell me how many chapters and strategy principles were loaded.
```

### List top strategy principles

```text
Use newsletter-mcp list_strategy_principles and summarize the top strategy principles that should influence the weekly intelligence brief.
```

### Strategy-aware interpretation

```text
Use newsletter-mcp list_strategy_principles and get_issue_summary for 2026-04-10. Explain this week's issue in the framework of the strategy doctrine, especially:
- structure before conviction
- selectivity not participation
- volatility as constraint
- portfolio fit
```

---

## Good prompt habits

- Say `Do not restate raw JSON` when you want cleaner prose.
- Say `Keep it concise` when you want a compact answer.
- Say `Do not search past conversations` when the DB/history should be the source of truth.
- Say `Do not show tool discovery, function schemas, internal steps, or MCP details` when Claude starts dumping tool chatter.
- Use the quiet mode prefix when you want to suppress tool chatter across any workflow.
- Say `Use schwab-smartspreads-file first` when the Daily workflow depends on current positions/pricing.
- Say `Use newsletter-mcp only` when you want historical/intelligence answers without Daily operational data.

---

## Avoid these patterns

- `Use only stored business-layer fields...`
  - Too vague; Claude may choose the wrong source path.

- `Figure out the exits manually...`
  - Use `get_daily_exit_schedule(...)` instead.

- `Use the latest issue` without a date
  - Fine for casual use, but less reliable than naming the exact issue date.

---

## Recommended default Daily prompt

If you use only one prompt most days, use this:

```text
Use only schwab-smartspreads-file and newsletter-mcp. Do not show tool discovery, function schemas, internal steps, or MCP details. Just use the tools and return the final answer.

Use schwab-smartspreads-file first to get stream status, futures positions, and watchlist pricing. Then use newsletter-mcp get_daily_exit_schedule with the futures-positions result, and use get_issue_summary for weekly context. Give me a concise morning brief with:
- stream/data quality status
- open positions ordered by nearest exit
- current watchlist opportunities
- conflicts or overlaps
- top 3 actions for today

If marks are stale, clearly downgrade confidence in pricing-based conclusions, but keep newsletter-derived exit dates as valid.
```
