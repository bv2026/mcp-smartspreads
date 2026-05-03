Use only smartspreads-mcp and schwab-smartspreads-file. Do not search past conversations. Do not use memory. Do not show tool discovery, function schemas, internal steps, or MCP details. Just use the tools and return the final answer.

Step 1: Verify newsletter ingestion
Call smartspreads-mcp.verify_newsletter_ingested with no date.
Report the raw verifier JSON first.
If latest_ingested_week_ended is not 2026-05-01, stop and say the May 1 newsletter is not the latest ingested issue.
If the verifier response contains old fields like status: verified, Calendar Spreads, Butterfly Spreads, or source_file without latest_source_file, stop and say Claude is using a stale MCP tool/cache.

Step 2: Weekly watchlist integrity
Using week_ended 2026-05-01, get the watchlist.
Report:
- total row count
- count where section_name is intra_commodity
- count where section_name is inter_commodity

Then print two separate sections:
1. Intra-Commodity Rows
2. Inter-Commodity Rows

For each row, print only:
commodity_name | spread_expression | enter_date | exit_date | trade_quality | volatility_structure

Rules:
- Use spread_expression verbatim.
- Treat each watchlist row as one spread.
- Do not split rows into legs.
- Do not create calendar/butterfly sub-bullets.
- Do not move rows between intra_commodity and inter_commodity.
- Do not add analysis in this section.

Step 3: Schwab/TOS position ingestion
Use schwab-smartspreads-file to get the current futures positions from the imported TOS CSV.
Report:
- statement_date
- source
- futures leg count
- whether marks are live or from tos_csv/stale/manual/no_tick
- any warnings returned by the tool

Step 4: Daily exit schedule
Pass the schwab futures positions result into smartspreads-mcp.get_daily_exit_schedule.
Report:
- as_of
- current_issue_week_ended
- position_count
- matched count
- unmatched/incomplete count
- urgency counts

Then list each matched position:
spread_id | spread_name | matched_week_ended | alignment_status | exit_date | days_to_exit | urgency_bucket

Then list each unmatched or incomplete position:
spread_id or symbol | legs | alignment_status | spread_error if present

Rules:
- Use smartspreads-mcp for newsletter rules, watchlists, and exit schedule.
- Use schwab-smartspreads-file for imported positions/pricing only.
- Prefer get_daily_exit_schedule over manually inferring exits.
- If marks are stale or from tos_csv, clearly say pricing conclusions are low confidence, but newsletter-derived exit dates remain valid.
- Do not invent missing exits.
- Do not reinterpret spread formulas.
- Do not combine intra and inter lists.
