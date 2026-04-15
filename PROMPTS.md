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

## Prompting guidance

- Prefer naming the exact issue date.
- Specify `intra_commodity` or `inter_commodity` when export scope matters.
- Ask for reference metadata when downstream interpretation is important.
- Ask for consolidated exports when you want one CSV spanning multiple issues.
