# Claude Prompt Cheat Sheet

This is the short version of the prompt guides.

Use this when you want fast, reliable prompts for:
- Sunday newsletter workflow
- Daily trading workflow
- issue/intelligence checks
- strategy-doctrine queries

---

## Copy This First

### Latest validated watchlist report

```text
Use smartspreads-mcp only. Do not use memory, prior conversation, other MCP servers, or manually reconstructed rows.

Call verify_newsletter_ingested with no date and return the raw JSON.

If is_ingested is false, stop and say the latest newsletter is not ingested.

Use the verifier output as the contract for get_validated_watchlist_report:
- week_ended = verifier.week_ended
- expected_entry_count = verifier.entry_count
- expected_intra_commodity_count = verifier.section_counts.intra_commodity
- expected_inter_commodity_count = verifier.section_counts.inter_commodity
- expected_watchlist_fingerprint = verifier.watchlist_fingerprint

Call get_validated_watchlist_report using that contract.

If is_valid is false, stop and report only the mismatches. Do not create a watchlist report.

If is_valid is true, output report_markdown exactly as returned by the tool. Do not rebuild, reorder, summarize, normalize, supplement, or infer any rows.

Use spread_expression verbatim. Do not split rows into legs. Do not combine intra_commodity and inter_commodity. Do not label rows as calendar/butterfly unless the tool output already does.

The vol_structure column is the newsletter's literal Vol Structure column and must only contain Low, Mid, or High. Never replace it with contango/backwardation labels or inferred structure text.

Inter-Commodity commodity_name values must be literal paired names from the newsletter table, such as Heating Oil, RBOB Gasoline. Never replace them with synthetic bucket names like Grains_Complex, Energy_Complex, or Metals_Complex.

Every report row must be source-backed inside the tool result with source_page_number, source_raw_row, and source_row_hash. If the tool reports a source_provenance mismatch, stop instead of reporting rows.
```

### Ingest latest newsletter

```text
Use smartspreads-mcp only. Ingest any pending newsletter PDFs from the configured newsletter data folder. Then call verify_newsletter_ingested with no date and return the raw JSON.

Report only:
- issue dates newly added
- latest_ingested_week_ended
- latest_source_file
- entry_count
- section_counts
- has_watchlist_reference

If no new issue was added, say so and report the latest ingested issue. Do not assume the uploaded newsletter was ingested unless verify_newsletter_ingested confirms it.
```

### Current positions and exit schedule

```text
Use only smartspreads-mcp and schwab-smartspreads-file. Do not use memory, prior conversation, other MCP servers, or manually reconstructed positions.

Schema gate first:
Call smartspreads-mcp verify_newsletter_ingested with no date and return the raw JSON.

Continue only if the raw JSON contains:
- latest_ingested_week_ended
- latest_source_file
- entry_count
- section_counts
- watchlist_fingerprint
- watchlist_row_signatures

Stop if it contains any stale fields:
- latest_ingested_issue
- watchlist_count
- high_confidence_new
- worthy_of_consideration
- Calendar Spreads
- Butterfly Spreads

Step 1:
Call schwab-smartspreads-file check_schwab_auth.

Auth gate:
If ok is not true or status is SCHWAB_REAUTH_REQUIRED, stop immediately and report SCHWAB_REAUTH_REQUIRED. Do not call positions, exit schedule, or answer from memory/local cached position data.

Step 2:
Call the Schwab current futures positions tool.

Freshness gate:
If any of these are true, stop immediately and report SCHWAB POSITION DATA STALE:
- stale_stream_marks > 0
- warning contains "Do NOT use for trade decisions"
- any leg has mark_source = stream_stale
- position_source = tos_csv_rejected_stale
- error = STALE_TOS_CSV_POSITION_SOURCE

Accept position_source = stream_positions when statement_date is today and stale_stream_marks = 0.
Accept source = stream_positions when all current legs use live_stream marks.
Accept mark_source = tos_csv_fallback only when statement_date is today, warning is absent, and pricing_note says the marks are today's TOS CSV statement marks. This is not stale position data. It is acceptable for current position/exit schedule work, but pricing conclusions are statement-snapshot confidence, not live-stream confidence.

If csv_marks > 0 or pricing_note is present, continue to Step 3 and Step 5. Do not stop. In the final verdict, say POSITION/EXIT SCHEDULE PASS WITH SNAPSHOT PRICING NOTE.

Step 3:
Print every current futures leg exactly as returned:
symbol | side | quantity | mark_source | spread_id | spread_name

Step 4:
Print the Schwab spread summaries exactly as returned:
id | name | type | legs | enter_date | exit_date | marks_live | error

Rules:
- Do not infer closed spreads from memory.
- Do not add any spread that is not present in the current tool output.
- A repeated quantity can intentionally support overlapping spreads. For example, one SHORT quantity of 2 can support two calendar spreads sharing the same short leg.
- Prefer the tool's spread summaries over manual grouping when checking completeness.

Step 5:
Call smartspreads-mcp get_daily_exit_schedule using the exact current futures positions result from Step 2.

Report:
- as_of
- current_issue_week_ended
- position_count
- matched_count
- unmatched/incomplete count
- urgency_counts

Then list every exit schedule row:
position_id | position_name | alignment_status | exit_date | urgency_bucket | spread_error | legs

Final verdict:
PASS if:
- SmartSpreads schema gate passes
- Schwab auth gate passes
- Schwab freshness gate passes
- no VXM/VX legs are present unless they are in the current Schwab tool output
- exit schedule uses current_issue_week_ended from the latest verified SmartSpreads issue
- exit schedule contains only spreads present in the current Schwab result

DATA QUALITY ISSUE if Schwab is fresh but a current spread summary has an error or a null spread_id/spread_name.

POSITION/EXIT SCHEDULE PASS WITH SNAPSHOT PRICING NOTE if the only non-live condition is current-day tos_csv_fallback marks with no stale warning. Continue through the exit schedule and clearly say pricing is statement-snapshot confidence, not live-stream confidence.

FAIL if Claude uses stale schema, fails Schwab auth, uses stale Schwab data, uses stale CSV as current positions, uses memory, or includes any spread not present in current tool output.
```

---

## General rules

- Before any "latest", "this week", or weekly newsletter report, verify the issue with `smartspreads-mcp.verify_newsletter_ingested`.
- If the requested or expected issue is not ingested, stop and report that fact; never answer from the prior issue.
- If `verify_newsletter_ingested` returns old fields like `status: verified`, `Calendar Spreads`, or `Butterfly Spreads`, stop: Claude is using a stale MCP tool/cache. Restart Claude and use the current `smartspreads-mcp` server.
- For watchlist rows, use `spread_expression` exactly as returned. Do not split rows into leg-level trades or reclassify intra/inter sections.
- For Sunday work, start with `smartspreads-mcp`.
- For Daily work, start with `schwab-smartspreads-file`, then use `smartspreads-mcp`.
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
Use smartspreads-mcp only. Ingest any pending newsletter PDFs from the configured newsletter data folder. Then call verify_newsletter_ingested with no date and return the raw JSON. Report the newly added issue dates, latest_ingested_week_ended, latest_source_file, entry_count, section_counts, and has_watchlist_reference.
```

### 2. Weekly intelligence brief

```text
Use smartspreads-mcp only. First verify the April 10, 2026 newsletter is ingested with verify_newsletter_ingested. If it is not ingested, stop and say the latest ingested issue. If it is ingested, build the weekly intelligence brief for the April 10, 2026 newsletter. Include:
- issue summary
- intra-commodity summary
- inter-commodity summary
- notable themes
- notable additions/removals versus the prior issue
- important watchlist reference rules that affect interpretation
```

### 2a. Latest ingested check

```text
Use smartspreads-mcp only. Verify the latest ingested newsletter issue first and report its week_ended and source_file. If that is not the issue I expect for this week, stop and say the newsletter is not ingested. Do not report from an older issue.
```

### 2b. Intra-only list without spread reinterpretation

```text
Use smartspreads-mcp only. First verify the requested issue is ingested. Then get the watchlist and return only rows where section_name is exactly intra_commodity. For each row, print commodity_name, spread_expression, enter_date, exit_date, trade_quality, and volatility_structure. Use spread_expression verbatim. Do not split rows into legs, do not create calendar/butterfly sub-bullets, and do not include inter_commodity rows.
```

### 2c. Latest validated watchlist report

```text
Use smartspreads-mcp only. Do not use memory or prior conversation.

First call verify_newsletter_ingested with no date and return the raw JSON. Then use that verifier output as the contract for get_validated_watchlist_report:
- expected_entry_count = verifier.entry_count
- expected_intra_commodity_count = verifier.section_counts.intra_commodity
- expected_inter_commodity_count = verifier.section_counts.inter_commodity
- expected_watchlist_fingerprint = verifier.watchlist_fingerprint

Call get_validated_watchlist_report for verifier.week_ended using those expected counts and expected_watchlist_fingerprint.

If is_valid is false, stop and report the mismatch. Do not create a report.
If is_valid is true, output report_markdown exactly as returned by the tool. Do not rebuild the table yourself.

Use spread_expression verbatim. Do not split rows into legs. Do not combine intra_commodity and inter_commodity. Do not use rows from memory, prior conversation, other tools, or manually reconstructed tables.

The `vol_structure` column is the newsletter's literal `Vol Structure` column and must only contain Low, Mid, or High. Never replace it with contango/backwardation labels or inferred structure text.

Inter-Commodity `commodity_name` values must be the literal paired names from the newsletter table, such as `Heating Oil, RBOB Gasoline`. Never replace them with synthetic bucket names like `Grains_Complex`, `Energy_Complex`, or `Metals_Complex`.

The validated report is source-backed. Every report row must have `source_page_number`, `source_raw_row`, and `source_row_hash` inside the tool result. If the tool reports a `source_provenance` mismatch, stop instead of reporting rows.
```

### 3. Publish the approved week

```text
Use smartspreads-mcp only. Publish the April 10, 2026 issue into the published folder, then confirm the publication version, manifest path, and watchlist row count.
```

### 4. End-to-end weekly handoff

```text
Use smartspreads-mcp first, then schwab-smartspreads-file. Republish the latest newsletter issue, confirm the published watchlist metadata, then verify the file-based Schwab MCP can see the published week and use that watchlist for live monitoring.
```

---

## Daily workflow

Use these after:
- `tos-statement.csv` is overwritten in the Schwab MCP `config/` folder
- `tos-screenshot.png` is overwritten in the Schwab MCP `config/` folder

### 1. Best Daily morning brief

```text
Use only schwab-smartspreads-file and smartspreads-mcp. Do not show tool discovery, function schemas, internal steps, or MCP details. Just use the tools and return the final answer.

Use schwab-smartspreads-file first to get stream status, futures positions, and watchlist pricing. Then use smartspreads-mcp get_daily_exit_schedule with the futures-positions result, and use get_issue_summary for weekly context. Give me a concise morning brief with:
- stream/data quality status
- open positions ordered by nearest exit
- current watchlist opportunities
- conflicts or overlaps
- top 3 actions for today

If marks are stale, clearly downgrade confidence in pricing-based conclusions, but keep newsletter-derived exit dates as valid.
```

### 2. Daily action plan

```text
Use only schwab-smartspreads-file and smartspreads-mcp. Do not show tool discovery, function schemas, internal steps, or MCP details. Just use the tools and return the final answer.

Use schwab-smartspreads-file first to get today's futures positions and current watchlist pricing. Then use smartspreads-mcp get_daily_exit_schedule with that futures-positions result. Create today's action plan using the latest published newsletter intelligence plus current Schwab data. Include:
- open positions that need attention
- watchlist ideas that are currently actionable
- exits due soon or due today
- conflicts between current positions and the newsletter watchlist
- legacy-carryover positions whose exit dates come from older newsletters
- the top 3 actions I should consider today
```

### 3. Exit schedule only

```text
Use only schwab-smartspreads-file and smartspreads-mcp. Do not show tool discovery, function schemas, internal steps, or MCP details. Just use the tools and return the final answer.

Use schwab-smartspreads-file first to get today's futures positions, then use smartspreads-mcp get_daily_exit_schedule with that result. Do not search past conversations. Respond only with:
- matched positions and exit dates
- unmatched positions
- manual-leg-only symbols
- no-tick symbols
Keep it concise.
```

### 4. Position alignment review

```text
Use schwab-smartspreads-file first, then smartspreads-mcp. Compare my imported current futures positions against the current published newsletter watchlist. Explain whether each position is aligned with this week's intra/inter ideas, rules, and exit dates. If a position is not in the current issue, use newsletter history for a legacy-carryover match before marking its exit as unknown.
```

### 5. Watchlist pricing check

```text
Use schwab-smartspreads-file first and smartspreads-mcp second. Price the current published watchlist legs and spreads, then explain the results in the context of this week's newsletter reference rules, section summaries, and entry/exit interpretation.
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
Use smartspreads-mcp import_strategy_manual, then tell me how many chapters and strategy principles were loaded.
```

### List top strategy principles

```text
Use smartspreads-mcp list_strategy_principles and summarize the top strategy principles that should influence the weekly intelligence brief.
```

### Strategy-aware interpretation

```text
Use smartspreads-mcp list_strategy_principles and get_issue_summary for 2026-04-10. Explain this week's issue in the framework of the strategy doctrine, especially:
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
- Say `Use smartspreads-mcp only` when you want historical/intelligence answers without Daily operational data.

---

## Avoid these patterns

- `Use only stored business-layer fields...`
  - Too vague; Claude may choose the wrong source path.

- `Figure out the exits manually...`
  - Use `get_daily_exit_schedule(...)` instead.

- `Use the latest issue` without verification
  - Always force `verify_newsletter_ingested` first; otherwise Claude may report from the latest stored issue even when this week's PDF has not been ingested.

---

## Recommended default Daily prompt

If you use only one prompt most days, use this:

```text
Use only schwab-smartspreads-file and smartspreads-mcp. Do not show tool discovery, function schemas, internal steps, or MCP details. Just use the tools and return the final answer.

Use schwab-smartspreads-file first to get stream status, futures positions, and watchlist pricing. Then use smartspreads-mcp get_daily_exit_schedule with the futures-positions result, and use get_issue_summary for weekly context. Give me a concise morning brief with:
- stream/data quality status
- open positions ordered by nearest exit
- current watchlist opportunities
- conflicts or overlaps
- top 3 actions for today

If marks are stale, clearly downgrade confidence in pricing-based conclusions, but keep newsletter-derived exit dates as valid.
```
