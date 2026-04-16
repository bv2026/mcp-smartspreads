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
6. Claude combines both sources into:
   - morning brief
   - action plan
   - alignment check between current positions and weekly watchlist
   - exit-date urgency for open positions

Suggested Daily ask:

```text
Use newsletter-mcp and schwab-smartspreads-file. I have already overwritten the canonical TOS statement CSV and TOS screenshot in the Schwab MCP config area, and both timestamps are current. Give me a morning brief using the current published newsletter week, my imported futures positions, current watchlist pricing, newsletter-aligned exit dates, and the rules that matter for interpreting today's setups.
```

