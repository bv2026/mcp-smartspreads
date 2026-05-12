# Newsletter Intelligence Test Prompts

This file is a practical testing guide for the Phase 1 intelligence workflow.

Use these prompts during development and validation when you want reliable,
compact answers from the stored business-layer outputs and published artifacts.

## Best practices

- Prefer `get_issue_summary` when testing business-layer outputs.
- Name the exact issue date.
- Ask Claude to use the tool once and summarize in plain English.
- Ask for compact answers to reduce repeated JSON/source attachment blocks.
- Use published artifact checks only when validating handoff or publication parity.

## Reliable prompts

### Stored issue brief

```text
Use get_issue_summary for 2026-04-10 once. Read issue_brief from that result and give me a concise plain-English summary of the stored issue brief.
```

Expected result:
- headline
- top themes
- main risks
- main opportunities
- watchlist composition summary

### Top themes

```text
Use get_issue_summary for 2026-04-10 once. Read issue_brief only and give me the top 3 stored themes in 3 short bullets. Do not restate raw JSON.
```

Expected result:
- grain concentration theme
- intra/inter mix theme
- dominant classification or volatility theme

### Risks and opportunities

```text
Use get_issue_summary for 2026-04-10 once. Read issue_brief only and give me 3 notable risks and 3 notable opportunities in concise bullets. Do not restate raw JSON.
```

Expected result:
- blocked-trade risk
- low-RIDX risk
- interpretation/rules risk
- top tradeable opportunities

### Watchlist composition

```text
Use get_issue_summary for 2026-04-10 once. Read issue_brief.watchlist_summary only and summarize the watchlist by section, category, classification, volatility, and blocked trades in one compact answer.
```

Expected result:
- section split
- dominant category
- dominant classification
- dominant volatility
- tradeable vs blocked count
- one or two blocked examples

### Change summary

```text
Use get_issue_summary for 2026-04-10 once. Read issue_delta and issue_brief.change_summary only and compare April 10 to the prior issue in one short paragraph.
```

Expected result:
- added count
- removed count
- changed count
- short interpretation of what changed

### Stored vs published parity

```text
Check whether the stored issue brief and published weekly_intelligence for 2026-04-10 agree on themes, risks, opportunities, watchlist summary, and change summary. Respond with only mismatches or say they match.
```

Expected result:
- `They match.` or a short list of mismatches

### Publication summary

```text
Summarize the current published April 10 issue from the stored business-layer data and published contract in one compact answer.
```

Expected result:
- publication version
- row count
- compact business summary

## Daily-oriented prompts

### Daily intelligence context

```text
Use get_issue_summary for 2026-04-10 once and give me the weekly context a trader should know before the open: top themes, key risks, best opportunities, and blocked trades.
```

### Daily risk focus

```text
Use get_issue_summary for 2026-04-10 once. List only the blocked trades, blocked reasons, and any rule-based caveats that matter operationally.
```

## Prompts to avoid

These are not always wrong, but they have been less reliable during testing.

### Too vague

```text
Use only stored business-layer fields for 2026-04-10 and give me 3 notable risks and 3 notable opportunities.
```

Problem:
- Claude may choose the wrong source path or over-literalize the request.

Better:

```text
Use get_issue_summary for 2026-04-10 once. Read issue_brief only and give me 3 notable risks and 3 notable opportunities in concise bullets.
```

### Artifact-only phrasing

```text
Using only persisted business-layer outputs, what are the top 3 themes for the April 10, 2026 issue?
```

Problem:
- Claude may read an older artifact snapshot instead of the current DB-backed issue summary.

Better:

```text
Use get_issue_summary for 2026-04-10 once. Read issue_brief only and give me the top 3 stored themes in 3 short bullets.
```

### Source-heavy phrasing

```text
Compare April 10, 2026 to the prior issue using only the stored issue brief and issue delta records.
```

Problem:
- Sometimes leads to repeated source attachment blocks after each line.

Better:

```text
Use get_issue_summary for 2026-04-10 once. Read issue_brief.change_summary and issue_delta only and compare April 10 to the prior issue in one short paragraph. Do not restate raw JSON.
```

## Good response patterns

Good answers should:
- be concise
- avoid repeating the same JSON source card after every sentence
- summarize rather than quote
- clearly separate stored brief facts from interpretation

Good compact format:

```text
April 10 is a grain-led issue with 10 trades split 7 intra / 3 inter. The main stored themes are grain concentration, Tier 1 emphasis, and a high-volatility bias. The biggest stored risks are 4 blocked setups, 4 low-RIDX setups, and the need to interpret trades using the issue’s hypothetical-entry rules. The top stored opportunities are Live Cattle/Lean Hogs, S&P 500 VIX, and Corn.
```

## Recommended reusable template

```text
Use get_issue_summary for <date> once. Read <field path> from that result and answer concisely in plain English. Do not restate raw JSON.
```

## Saved Markdown artifact prompts

Use these when you want the output in a reusable Markdown file that can be saved/downloaded directly.

### Newsletter report with save path

```text
Use smartspreads-mcp only. First call verify_newsletter_ingested with no date and confirm the target week is ingested. If it is not ingested, stop and report the latest ingested week.

Then generate one complete Markdown newsletter report for that verified week.

Save the same Markdown to:
- reports/<week_ended>/newsletter_report_<week_ended>.md
- where <week_ended> is the verified issue date in YYYY-MM-DD format.

End by printing the saved file path.
```

### Validated watchlist report with save path

```text
Use smartspreads-mcp only. Do not use memory.

Step 1:
Call verify_newsletter_ingested with no date and return raw JSON.

Step 2:
Use verifier.entry_count, verifier.section_counts, and verifier.watchlist_fingerprint as the expected contract.

Step 3:
Call get_validated_watchlist_report for verifier.week_ended with those expected values.

If is_valid is false, stop and report the mismatch.
If is_valid is true, output report_markdown exactly as returned.

Save the same Markdown to:
- reports/<week_ended>/validated_watchlist_report_<week_ended>.md
- where <week_ended> is verifier.week_ended in YYYY-MM-DD format.

End by printing the saved file path.
```
