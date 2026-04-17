# Newsletter MCP Usage

## Setup

1. Install the package:

```powershell
python -m pip install -e .
```

2. Configure `.env` if needed:

```env
NEWSLETTER_DATA_DIR=C:\work\SmartSpreads\data
DATABASE_URL=sqlite:///C:/work/SmartSpreads/newsletters.db
```

3. Start the MCP server:

```powershell
newsletter-mcp
```

## Typical workflow

### 1. Ingest newsletters

Ingest all PDFs currently in `data/`:

```python
ingest_pending_newsletters()
```

Or ingest a single PDF:

```python
ingest_newsletter("Smart-Spreads-Weekly-Newsletter-Week-End-April-10-2026.pdf")
```

### 2. Query issues

List recent imported issues:

```python
list_issues(limit=10)
```

Get a single issue summary:

```python
get_issue_summary("2026-04-10")
```

### 3. Query watchlists

Get the watchlist with reference metadata:

```python
get_watchlist("2026-04-10")
```

Get only stronger tiers in newer issues:

```python
get_watchlist("2026-04-10", min_trade_quality="Tier 2")
```

Get the separate reference block:

```python
get_watchlist_reference("2026-04-10")
```

## Export workflows

### Single issue CSV

```python
export_watchlist_csv(
    week_ended="2026-04-10",
    section_name="intra_commodity",
    output_path=r"C:\work\SmartSpreads\export\apr10_intra.csv",
)
```

### Single issue package

Writes:
- `rows.csv`
- `reference.json`

```python
export_watchlist_package(
    week_ended="2026-04-10",
    section_name="inter_commodity",
    output_dir=r"C:\work\SmartSpreads\export\issues\2026-04-10\inter_commodity",
)
```

### Consolidated CSV across dates

```python
export_all_watchlists_csv(
    date_from="2025-12-26",
    date_to="2026-04-10",
    section_name="intra_commodity",
    output_path=r"C:\work\SmartSpreads\export\consolidated\intra_commodity.csv",
)
```

### Full bundle export

Writes:
- per-issue intra/inter packages
- consolidated intra/inter CSVs
- consolidated references JSON files

```python
export_watchlist_bundle(
    date_from="2025-12-26",
    date_to="2026-04-10",
    output_dir=r"C:\work\SmartSpreads\export",
)
```

## Output locations

Current canonical export root:

- `C:\work\SmartSpreads\export`

Key outputs:

- `C:\work\SmartSpreads\export\consolidated\intra_commodity.csv`
- `C:\work\SmartSpreads\export\consolidated\inter_commodity.csv`
- `C:\work\SmartSpreads\export\issues\<week-ended>\intra_commodity\rows.csv`
- `C:\work\SmartSpreads\export\issues\<week-ended>\inter_commodity\rows.csv`

## Best practice notes

- Treat `watchlist_entries` as the live trading/export layer.
- Treat `watchlist_references` as interpretation metadata, not live trades.
- Use `section_name` to separate intra/inter exports.
- For older issues, expect `portfolio` and `risk_level` instead of `trade_quality`.

## Sunday workflow

Recommended Sunday sequence:

1. `newsletter-mcp`
   Ingest the new PDF and validate the issue.
2. `newsletter-mcp`
   Review `get_issue_summary(...)`, `get_watchlist(...)`, and `get_watchlist_reference(...)`.
3. `newsletter-mcp`
   Run `publish_issue(...)` for the approved week.
   Phase 3 note:
   the published contract now includes `principle_context` at the top level and per-entry principle fields such as `principle_scores`, `principle_status`, `decision_summary`, and `deferred_principles`.
4. `newsletter-mcp`
   Generate any CSV/package exports needed for review.
5. `schwab-smartspreads-file`
   Verify the file-based Schwab workflow is reading the published watchlist.

Suggested Sunday ask:

```text
Use newsletter-mcp first, then schwab-smartspreads-file. Ingest the latest newsletter, validate the watchlist and reference rules, publish the approved issue, and confirm the file-based Schwab MCP is reading the published watchlist correctly.
```

## Daily workflow

Recommended Daily sequence:

1. Overwrite the canonical TOS statement CSV in the Schwab MCP `config/` folder.
2. Overwrite the canonical TOS screenshot PNG used for validation/context.
3. Confirm both file timestamps show they were updated for the current Daily run.
4. `schwab-smartspreads-file`
   Check stream health, import current futures positions from the TOS statement, and price:
   - open-position legs/spreads
   - current published watchlist legs/spreads
5. `newsletter-mcp`
   Pull the current week's intelligence, watchlist reference rules, issue summary, and newsletter-aligned exit dates.
   Prefer `get_daily_exit_schedule(...)` when you already have the `get_futures_positions` result from Schwab MCP.
   This now includes:
    - current-issue matches where the open spread is still in the latest watchlist
    - legacy-carryover matches from older newsletters when the spread is no longer in the current issue
    - quantity-aware matching for butterfly structures
    - Phase 3 publication context showing which weekly ideas were screened, blocked, or deferred for Daily review
6. Claude combines both sources into:
   - morning brief
   - action plan
   - alignment check between current positions and weekly watchlist
   - exit-date urgency for open positions

Known Daily limitations:

- Some valid symbols may still have no ticks from Schwab streaming in this workflow.
- VIX-family contracts are valid but are treated as manual-leg workflow items, not native spread entries.
- `/MWE` currently remains a known no-tick / unsupported operational case.
- If a position truly has no newsletter-history match, its exit date will remain `Unknown` until a manual fallback is introduced.
- Phase 3 principle thresholds are now live in the weekly publication, but they still need ongoing calibration against real historical recurrence and operator judgment.

Suggested Daily ask:

```text
Use schwab-smartspreads-file first to get today's futures positions and watchlist pricing, then use newsletter-mcp get_daily_exit_schedule on that positions result. I have already overwritten the canonical TOS statement CSV and TOS screenshot in the Schwab MCP config area, and both timestamps are current. Give me a morning brief using the current published newsletter week, my imported futures positions, current watchlist pricing, newsletter-history-backed exit dates, and the rules that matter for interpreting today's setups. Treat valid-but-manual-leg symbols separately from normal native spread entries.
```

## Testing

Run the full local test suite with:

```powershell
python -m unittest discover -s tests
```

Phase 3 coverage now includes:

- `tests/test_principle_evaluation.py`
- `tests/test_publication_contract.py`

