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
