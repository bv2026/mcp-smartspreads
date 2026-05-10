#!/usr/bin/env python3
"""
SmartSpreads CLI - menu-driven access to core MCP functions.

Use this when Claude Code is unavailable (rate limits, outages, etc.).
Run from the SmartSpreads project root:

    python scripts/smartspreads_cli.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.chdir(PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from newsletter_mcp.config import Settings
from newsletter_mcp.database import Database

settings = Settings.from_env()
database = Database(settings.database_url)
database.create_schema()

REPORTS_ROOT = PROJECT_ROOT / "reports"

_server = None
_latest_week_ended: str | None = None


def _get_server():
    global _server
    if _server is None:
        import newsletter_mcp.server as srv
        _server = srv
    return _server


def _get_latest_week_ended() -> str:
    global _latest_week_ended
    if _latest_week_ended is None:
        issues = _get_server().list_issues(limit=1)
        if issues:
            _latest_week_ended = issues[0]["week_ended"]
        else:
            _latest_week_ended = date.today().isoformat()
    return _latest_week_ended


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _format_json(result: Any) -> str:
    if isinstance(result, (dict, list)):
        return json.dumps(result, indent=2, default=str)
    return str(result)


def _md_table(rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    if not rows:
        return "*No data*\n"
    cols = columns or list(rows[0].keys())
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    lines = [header, sep]
    for row in rows:
        vals = []
        for c in cols:
            v = row.get(c, "")
            v = str(v) if v is not None else ""
            if len(v) > 80:
                v = v[:77] + "..."
            v = v.replace("|", "/").replace("\n", " ")
            vals.append(v)
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines) + "\n"


def _md_kv(data: dict[str, Any]) -> str:
    lines = []
    for k, v in data.items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            continue
        if isinstance(v, dict):
            lines.append(f"- **{k}:** *(see details below)*")
        elif isinstance(v, list):
            lines.append(f"- **{k}:** {len(v)} items")
        else:
            lines.append(f"- **{k}:** {v}")
    return "\n".join(lines) + "\n"


def _build_report_md(func_name: str, result: Any) -> str:
    now = datetime.now()
    sections = [
        f"# {func_name.replace('_', ' ').title()}",
        "",
        f"| Field | Value |",
        f"| --- | --- |",
        f"| Function | `{func_name}` |",
        f"| Generated | {now.strftime('%Y-%m-%d %H:%M:%S')} |",
        "",
    ]

    if isinstance(result, list) and result and isinstance(result[0], dict):
        sections.append(f"## Results ({len(result)} rows)\n")
        sections.append(_md_table(result))
    elif isinstance(result, dict):
        nested_lists = {
            k: v for k, v in result.items()
            if isinstance(v, list) and v and isinstance(v[0], dict)
        }
        nested_dicts = {
            k: v for k, v in result.items()
            if isinstance(v, dict)
        }
        scalar_fields = {
            k: v for k, v in result.items()
            if k not in nested_lists and k not in nested_dicts
        }
        if scalar_fields:
            sections.append("## Summary\n")
            sections.append(_md_kv(scalar_fields))
        for key, rows in nested_lists.items():
            sections.append(f"\n## {key.replace('_', ' ').title()} ({len(rows)} rows)\n")
            sections.append(_md_table(rows))
        for key, obj in nested_dicts.items():
            sections.append(f"\n## {key.replace('_', ' ').title()}\n")
            sections.append(_md_kv(obj))
    else:
        sections.append(f"## Output\n\n{result}\n")

    sections.append("\n---\n")
    return "\n".join(sections)


def _save_management_report(func_name: str, result: Any) -> Path:
    report_dir = REPORTS_ROOT / "management"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{func_name}.md"
    path.write_text(_build_report_md(func_name, result), encoding="utf-8")
    return path


def _save_issue_report(week_ended: str, filename: str, content: str) -> Path:
    report_dir = REPORTS_ROOT / week_ended
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


def _run_and_report_mgmt(func_name: str, result: Any) -> None:
    print(_format_json(result))
    path = _save_management_report(func_name, result)
    print(f"\n[saved: {path.relative_to(PROJECT_ROOT)}]")


class _Cancel(Exception):
    pass


def _prompt(msg: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"  {msg}{suffix}: ").strip()
    if val in ("q", "b"):
        raise _Cancel()
    return val or (default or "")


def _prompt_optional(msg: str) -> str | None:
    val = input(f"  {msg} (Enter to skip): ").strip()
    return val or None


def _prompt_week(msg: str = "Week ended date") -> str:
    default = _get_latest_week_ended()
    return _prompt(msg, default)


# ===================================================================
# A - Setup & Management
# ===================================================================

def do_list_issues():
    limit = int(_prompt("How many issues", "10"))
    _run_and_report_mgmt("list_issues", _get_server().list_issues(limit=limit))


def do_verify_newsletter():
    week = _prompt_optional("Week ended date (YYYY-MM-DD)")
    _run_and_report_mgmt("verify_newsletter_ingested",
                         _get_server().verify_newsletter_ingested(week_ended=week))


def do_ingest_newsletter():
    path = _prompt_optional("PDF path (Enter for latest in data/)")
    _run_and_report_mgmt("ingest_newsletter",
                         _get_server().ingest_newsletter(pdf_path=path))


def do_ingest_pending():
    _run_and_report_mgmt("ingest_pending_newsletters",
                         _get_server().ingest_pending_newsletters())


def do_backfill_intelligence():
    _run_and_report_mgmt("backfill_phase1_intelligence",
                         _get_server().backfill_phase1_intelligence())


def do_import_schwab_catalog():
    path = _prompt_optional("CSV path (Enter for default)")
    _run_and_report_mgmt("import_schwab_futures_catalog",
                         _get_server().import_schwab_futures_catalog(csv_path=path))


def do_view_schwab_catalog():
    limit = int(_prompt("Limit", "25"))
    cat = _prompt_optional("Category filter")
    _run_and_report_mgmt("list_schwab_futures_catalog",
                         _get_server().list_schwab_futures_catalog(limit=limit,
                                                                  category=cat))


def do_view_commodity_catalog():
    _run_and_report_mgmt("list_newsletter_commodity_catalog",
                         _get_server().list_newsletter_commodity_catalog())


def do_view_contract_codes():
    _run_and_report_mgmt("list_contract_month_codes",
                         _get_server().list_contract_month_codes())


def do_import_strategy_manual():
    path = _prompt_optional("PDF path (Enter for default)")
    _run_and_report_mgmt("import_strategy_manual",
                         _get_server().import_strategy_manual(pdf_path=path))


def do_view_strategy_principles():
    cat = _prompt_optional("Category filter")
    _run_and_report_mgmt("list_strategy_principles",
                         _get_server().list_strategy_principles(category=cat))


LAYER_A_ITEMS = [
    ("1", "List issues", do_list_issues),
    ("2", "Verify newsletter ingested", do_verify_newsletter),
    ("3", "Ingest single newsletter PDF", do_ingest_newsletter),
    ("4", "Ingest all pending newsletters", do_ingest_pending),
    ("5", "Backfill intelligence (maintenance)", do_backfill_intelligence),
    ("6", "Import Schwab futures catalog", do_import_schwab_catalog),
    ("7", "View Schwab futures catalog", do_view_schwab_catalog),
    ("8", "View commodity catalog", do_view_commodity_catalog),
    ("9", "View contract month codes", do_view_contract_codes),
    ("10", "Import strategy manual", do_import_strategy_manual),
    ("11", "View strategy principles", do_view_strategy_principles),
]


# ===================================================================
# B - Sunday Pipeline
# ===================================================================

def _build_sunday_pipeline_md(week: str, steps: dict[str, Any]) -> str:
    """Build consolidated sunday_pipeline.md from all pipeline step results."""
    now = datetime.now()
    lines = [
        f"# Sunday Pipeline: {week}",
        "",
        f"Generated: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    # Step 1: Ingest
    ingest = steps.get("ingest", {})
    lines.append("## 1. Ingest")
    lines.append("")
    lines.append(f"- **ingested_count:** {ingest.get('ingested_count', 0)}")
    lines.append(f"- **skipped_count:** {ingest.get('skipped_count', 0)}")
    newly = [r for r in ingest.get("results", []) if r.get("status") == "ingested"]
    if newly:
        lines.append(f"\nNewly ingested:")
        for r in newly:
            lines.append(f"- {r.get('week_ended')} -- {r.get('source_file', '')}")
    lines.append("")

    # Step 2: Verify
    verify = steps.get("verify", {})
    lines.append("## 2. Verify")
    lines.append("")
    lines.append(f"- **week_ended:** {verify.get('latest_ingested_week_ended', verify.get('week_ended', ''))}")
    lines.append(f"- **entry_count:** {verify.get('entry_count', 0)}")
    sc = verify.get("section_counts", {})
    lines.append(f"- **intra_commodity:** {sc.get('intra_commodity', 0)}")
    lines.append(f"- **inter_commodity:** {sc.get('inter_commodity', 0)}")
    lines.append(f"- **has_watchlist_reference:** {verify.get('has_watchlist_reference', False)}")
    lines.append(f"- **watchlist_fingerprint:** {verify.get('watchlist_fingerprint', '')}")
    lines.append("")

    # Step 3: Publish
    publish = steps.get("publish", {})
    lines.append("## 3. Publish")
    lines.append("")
    pub_refreshed = publish.get("refreshed", publish)
    pub_published = publish.get("published", publish)
    lines.append(f"- **publication_version:** {pub_published.get('publication_version', publish.get('publication_version', '?'))}")
    lines.append(f"- **publication_run_id:** {pub_published.get('publication_run_id', publish.get('publication_run_id', '?'))}")
    delta = pub_refreshed.get("delta_summary", publish.get("delta_summary", ""))
    if delta:
        lines.append(f"- **delta_summary:** {delta}")
    lines.append("")

    # Step 4: Validated Report
    validated = steps.get("validated", {})
    lines.append("## 4. Validated Watchlist")
    lines.append("")
    lines.append(f"- **is_valid:** {validated.get('is_valid', '?')}")
    lines.append(f"- **message:** {validated.get('message', '')}")
    report_md = validated.get("report_markdown", "")
    if report_md:
        lines.append("")
        lines.append(report_md)
    lines.append("")

    # Step 5: CSV Export (if present)
    csv_info = steps.get("csv_export")
    if csv_info:
        lines.append("## 5. CSV Export")
        lines.append("")
        lines.append(f"- **entry_count:** {csv_info.get('entry_count', 0)}")
        written = csv_info.get("written_files", {})
        if written:
            for label, fpath in written.items():
                lines.append(f"- **{label}:** `{fpath}`")
        lines.append("")

    # Source provenance
    entries = validated.get("entries", [])
    if entries:
        prov_cols = ["section_name", "commodity_name", "spread_expression",
                     "source_page_number", "source_row_hash"]
        lines.append("## Source Provenance")
        lines.append("")
        lines.append(_md_table(entries, prov_cols))

    lines.append("\n---\n")
    return "\n".join(lines)


def _build_issue_analysis_md(week: str, parts: dict[str, Any]) -> str:
    """Build consolidated issue_analysis.md from summary + brief + watchlist + principles."""
    now = datetime.now()
    lines = [
        f"# Issue Analysis: {week}",
        "",
        f"Generated: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    # Issue Brief
    brief = parts.get("brief", {})
    if brief:
        lines.append("## Issue Brief")
        lines.append("")
        if brief.get("headline"):
            lines.append(f"**{brief['headline']}**")
            lines.append("")
        if brief.get("executive_summary"):
            lines.append(brief["executive_summary"])
            lines.append("")
        for field, label in [("key_themes", "Key Themes"),
                             ("notable_risks", "Notable Risks"),
                             ("notable_opportunities", "Notable Opportunities")]:
            items = brief.get(field, [])
            if items:
                lines.append(f"### {label}")
                lines.append("")
                for item in items:
                    lines.append(f"- {item}")
                lines.append("")

        ws = brief.get("watchlist_summary", {})
        if ws:
            lines.append("### Watchlist Summary")
            lines.append("")
            for k, v in ws.items():
                lines.append(f"- **{k}:** {v}")
            lines.append("")

        change = brief.get("change_summary", {})
        if change:
            lines.append("### Change Summary (vs prior issue)")
            lines.append("")
            for k, v in change.items():
                lines.append(f"- **{k}:** {v}")
            lines.append("")

    # Watchlist compact
    entries = parts.get("entries", [])
    if entries:
        intra = [e for e in entries if e.get("section_name") == "intra_commodity"]
        inter = [e for e in entries if e.get("section_name") == "inter_commodity"]
        cols = ["commodity_name", "spread_expression", "side", "enter_date",
                "exit_date", "trade_quality", "volatility_structure", "tradeable"]

        if intra:
            lines.append(f"## Intra-Commodity Watchlist ({len(intra)} rows)")
            lines.append("")
            lines.append(_md_table(intra, cols))

        if inter:
            lines.append(f"## Inter-Commodity Watchlist ({len(inter)} rows)")
            lines.append("")
            lines.append(_md_table(inter, cols))

        # Tradeable summary
        tradeable = [e for e in entries if e.get("tradeable")]
        blocked = [e for e in entries if not e.get("tradeable") and e.get("blocked_reason")]
        lines.append("## Tradeable vs Blocked Summary")
        lines.append("")
        lines.append(f"- **Total entries:** {len(entries)}")
        lines.append(f"- **Tradeable:** {len(tradeable)}")
        lines.append(f"- **Blocked:** {len(blocked)}")
        if entries:
            lines.append(f"- **Selectivity:** {len(tradeable) / len(entries) * 100:.0f}%")
        lines.append("")

        if tradeable:
            lines.append("### Tradeable")
            lines.append("")
            for e in tradeable:
                lines.append(f"- {e.get('commodity_name')} {e.get('spread_expression')} "
                             f"({e.get('trade_quality', '')})")
            lines.append("")

        if blocked:
            lines.append("### Blocked")
            lines.append("")
            for e in blocked:
                reason = (e.get("blocked_reason") or "")[:80]
                lines.append(f"- {e.get('commodity_name')} {e.get('spread_expression')}: {reason}")
            lines.append("")

    # Principle analysis
    if entries and any(e.get("principle_scores") for e in entries):
        lines.append("## Principle Analysis")
        lines.append("")
        for e in entries:
            scores = e.get("principle_scores", {})
            statuses = e.get("principle_status", {})
            if not scores:
                continue
            tradeable_flag = "TRADEABLE" if e.get("tradeable") else "BLOCKED"
            lines.append(f"### {e.get('commodity_name')} {e.get('spread_code', '')} [{tradeable_flag}]")
            lines.append("")
            summary = e.get("decision_summary", "")
            if summary:
                lines.append(f"_{summary}_")
                lines.append("")
            for principle, score in scores.items():
                status = statuses.get(principle, "?")
                marker = "X" if status == "fail" else ("~" if status == "deferred" else "v")
                score_str = f"{score:.2f}" if score is not None else "n/a"
                lines.append(f"- [{marker}] **{principle}:** {score_str} ({status})")
            lines.append("")

    lines.append("\n---\n")
    return "\n".join(lines)


def do_sunday_full_pipeline():
    """Ingest -> verify -> publish -> validated report -> CSV export."""
    srv = _get_server()
    global _latest_week_ended
    _latest_week_ended = None
    steps: dict[str, Any] = {}

    print("\n  Step 1/5: Ingesting pending newsletters...")
    ingest_result = srv.ingest_pending_newsletters()
    steps["ingest"] = ingest_result
    ingested = ingest_result.get("ingested_count", 0)
    skipped = ingest_result.get("skipped_count", 0)
    print(f"  -> Ingested: {ingested}, Skipped: {skipped}")

    print("\n  Step 2/5: Verifying latest newsletter...")
    verify_result = srv.verify_newsletter_ingested(week_ended=None)
    steps["verify"] = verify_result
    week = verify_result.get("latest_ingested_week_ended")
    if not week:
        print("  ERROR: No newsletter found in database.")
        return
    entry_count = verify_result.get("entry_count", 0)
    print(f"  -> Latest issue: {week}, entries: {entry_count}")

    print(f"\n  Step 3/5: Refresh & publish issue {week}...")
    publish_result = srv.refresh_and_publish_issue(week_ended=week)
    steps["publish"] = publish_result
    pub_data = publish_result.get("published", publish_result)
    pub_version = pub_data.get("publication_version", "?")
    print(f"  -> Published: {pub_version}")

    print(f"\n  Step 4/5: Validated watchlist report for {week}...")
    section_counts = verify_result.get("section_counts", {})
    validated = srv.get_validated_watchlist_report(
        week_ended=week,
        expected_entry_count=entry_count,
        expected_intra_commodity_count=section_counts.get("intra_commodity"),
        expected_inter_commodity_count=section_counts.get("inter_commodity"),
        expected_watchlist_fingerprint=verify_result.get("watchlist_fingerprint"),
    )
    steps["validated"] = validated
    is_valid = validated.get("is_valid", False)
    print(f"  -> Valid: {is_valid}")

    print(f"\n  Step 5/5: Exporting watchlist CSV for {week}...")
    csv_dir = REPORTS_ROOT / week
    csv_dir.mkdir(parents=True, exist_ok=True)
    csv_path = str(csv_dir / f"{week}-watchlist.csv")
    csv_result = srv.export_watchlist_csv(
        week_ended=week,
        output_path=csv_path,
    )
    steps["csv_export"] = csv_result
    print(f"  -> CSV exported: {csv_result.get('entry_count', 0)} entries")

    # Save consolidated report
    content = _build_sunday_pipeline_md(week, steps)
    path = _save_issue_report(week, "sunday_pipeline.md", content)

    print(f"\n  Sunday pipeline complete for {week}.")
    print(f"  Reports saved to: {path.parent.relative_to(PROJECT_ROOT)}/")
    print(f"    - sunday_pipeline.md")
    print(f"    - {week}-watchlist.csv")
    if not is_valid:
        print("  WARNING: Validated report has mismatches! Check the report.")


def do_sunday_ingest_and_verify():
    """Ingest pending + verify (steps 1-2 only)."""
    srv = _get_server()
    global _latest_week_ended
    _latest_week_ended = None

    print("\n  Ingesting pending newsletters...")
    ingest_result = srv.ingest_pending_newsletters()
    print(f"  -> Ingested: {ingest_result.get('ingested_count', 0)}, "
          f"Skipped: {ingest_result.get('skipped_count', 0)}")

    print("\n  Verifying latest newsletter...")
    verify_result = srv.verify_newsletter_ingested(week_ended=None)
    week = verify_result.get("latest_ingested_week_ended")
    entry_count = verify_result.get("entry_count", 0)
    sections = verify_result.get("section_counts", {})
    has_ref = verify_result.get("has_watchlist_reference", False)
    print(f"  -> Latest: {week}")
    print(f"  -> Entries: {entry_count}")
    print(f"  -> Sections: {_format_json(sections)}")
    print(f"  -> Watchlist reference: {has_ref}")

    # Save to management since this is a partial run
    _save_management_report("sunday_ingest_verify", {
        "ingest": ingest_result, "verify": verify_result
    })


def do_sunday_publish():
    """Refresh & publish for a specific issue."""
    week = _prompt_week()
    srv = _get_server()
    print(f"\n  Refreshing & publishing {week}...")
    result = srv.refresh_and_publish_issue(week_ended=week)
    print(_format_json(result))
    _save_management_report("refresh_and_publish", result)


def do_sunday_validated_report():
    """Run the full verify -> validated report chain."""
    srv = _get_server()
    print("\n  Verifying latest newsletter...")
    verify = srv.verify_newsletter_ingested(week_ended=None)
    week = verify.get("latest_ingested_week_ended")
    if not week:
        print("  ERROR: No newsletter found.")
        return
    entry_count = verify.get("entry_count", 0)
    sections = verify.get("section_counts", {})
    print(f"  -> Issue: {week}, entries: {entry_count}")

    print(f"\n  Running validated report for {week}...")
    result = srv.get_validated_watchlist_report(
        week_ended=week,
        expected_entry_count=entry_count,
        expected_intra_commodity_count=sections.get("intra_commodity"),
        expected_inter_commodity_count=sections.get("inter_commodity"),
        expected_watchlist_fingerprint=verify.get("watchlist_fingerprint"),
    )
    print(_format_json(result))

    content = _build_sunday_pipeline_md(week, {"verify": verify, "validated": result})
    path = _save_issue_report(week, "sunday_pipeline.md", content)
    print(f"\n[saved: {path.relative_to(PROJECT_ROOT)}]")


def do_sunday_issue_analysis():
    """Build consolidated issue analysis: brief + watchlist + principles."""
    srv = _get_server()
    week = _prompt_week()

    print(f"\n  Building issue analysis for {week}...")

    print("  -> Loading issue summary...")
    summary = srv.get_issue_summary(week_ended=week)
    brief = summary.get("issue_brief", {})

    print("  -> Loading watchlist...")
    watchlist = srv.get_watchlist(week_ended=week)
    entries = watchlist.get("entries", [])
    tradeable = [e for e in entries if e.get("tradeable")]
    blocked = [e for e in entries if not e.get("tradeable") and e.get("blocked_reason")]

    print(f"  -> Entries: {len(entries)}, Tradeable: {len(tradeable)}, Blocked: {len(blocked)}")

    # Display compact watchlist on screen
    intra = [e for e in entries if e.get("section_name") == "intra_commodity"]
    inter = [e for e in entries if e.get("section_name") == "inter_commodity"]

    if intra:
        print(f"\n  Intra-Commodity ({len(intra)} rows):")
        for e in intra:
            t = "Y" if e.get("tradeable") else "N"
            print(f"  {e.get('commodity_name', ''):20s} "
                  f"{e.get('spread_expression', ''):30s} "
                  f"{e.get('side', ''):5s} "
                  f"{e.get('trade_quality', ''):8s} {t}")

    if inter:
        print(f"\n  Inter-Commodity ({len(inter)} rows):")
        for e in inter:
            t = "Y" if e.get("tradeable") else "N"
            print(f"  {e.get('commodity_name', ''):20s} "
                  f"{e.get('spread_expression', ''):30s} "
                  f"{e.get('side', ''):5s} "
                  f"{e.get('trade_quality', ''):8s} {t}")

    content = _build_issue_analysis_md(week, {
        "brief": brief,
        "entries": entries,
    })
    path = _save_issue_report(week, "issue_analysis.md", content)
    print(f"\n[saved: {path.relative_to(PROJECT_ROOT)}]")


def do_sunday_export_csv():
    """Export watchlist CSV for an issue."""
    week = _prompt_week()
    section = _prompt_optional("Section filter (intra_commodity / inter_commodity)")
    csv_dir = REPORTS_ROOT / week
    csv_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"-{section}" if section else ""
    csv_path = str(csv_dir / f"{week}-watchlist{suffix}.csv")
    result = _get_server().export_watchlist_csv(
        week_ended=week,
        section_name=section,
        output_path=csv_path,
    )
    print(f"  Exported {result.get('entry_count', 0)} entries to:")
    print(f"  {csv_path}")


LAYER_B_ITEMS = [
    ("1", "Full Sunday pipeline (ingest->publish->validate->CSV)", do_sunday_full_pipeline),
    ("2", "Ingest & verify only", do_sunday_ingest_and_verify),
    ("3", "Publish issue", do_sunday_publish),
    ("4", "Validated watchlist report", do_sunday_validated_report),
    ("5", "Issue analysis (brief + watchlist + principles)", do_sunday_issue_analysis),
    ("6", "Export watchlist CSV", do_sunday_export_csv),
]


# ===================================================================
# C - Daily Bridge (smartspreads-mcp side only)
# ===================================================================

_daily_issue_date: str | None = None


def _daily_date() -> str:
    assert _daily_issue_date is not None
    return _daily_issue_date


def do_daily_exit_schedule():
    """Resolve exit schedule from manually entered positions."""
    print("  Enter positions as JSON array")
    print('  (e.g. [{"symbol": "/ZCZ26-/ZCH27"}]):')
    raw = input("  > ").strip()
    if not raw:
        print("  No positions entered.")
        return
    positions = json.loads(raw)
    as_of = _prompt("As-of date", date.today().isoformat())
    result = _get_server().resolve_open_position_exit_schedule(
        positions=positions, as_of=as_of)
    print(_format_json(result))


def do_daily_exit_from_schwab():
    """Resolve exit schedule from a Schwab positions JSON file."""
    path = _prompt("Path to Schwab positions JSON file")
    p = Path(path)
    if not p.exists():
        print(f"  File not found: {path}")
        return
    positions_data = json.loads(p.read_text(encoding="utf-8"))
    as_of = _prompt("As-of date", date.today().isoformat())
    result = _get_server().get_daily_exit_schedule(
        schwab_futures_positions=positions_data, as_of=as_of)
    print(_format_json(result))


def do_daily_tradeable_ideas():
    """Show only tradeable watchlist entries for today's action planning."""
    result = _get_server().get_watchlist(week_ended=_daily_date())
    entries = result.get("entries", [])
    tradeable = [e for e in entries if e.get("tradeable")]

    print(f"\n  Tradeable Ideas for {_daily_date()} ({len(tradeable)} of {len(entries)})")
    for e in tradeable:
        summary = (e.get("decision_summary") or "")[:60]
        print(f"  {e.get('commodity_name', ''):20s} "
              f"{e.get('spread_expression', ''):30s} "
              f"{e.get('trade_quality', ''):8s} "
              f"{summary}")


def do_daily_intelligence_context():
    """Get weekly intelligence context for daily trading decisions."""
    result = _get_server().get_issue_summary(week_ended=_daily_date())
    brief = result.get("issue_brief", {})

    print(f"\n  === Intelligence Context: {_daily_date()} ===")

    for field, label in [("key_themes", "Key Themes"),
                         ("notable_risks", "Risks to Watch"),
                         ("notable_opportunities", "Opportunities")]:
        items = brief.get(field, [])
        if items:
            print(f"\n  {label}:")
            for item in items[:5]:
                print(f"    - {item}")


LAYER_C_ITEMS = [
    ("1", "Exit schedule (enter positions manually)", do_daily_exit_schedule),
    ("2", "Exit schedule (from Schwab positions JSON file)", do_daily_exit_from_schwab),
    ("3", "Tradeable ideas only", do_daily_tradeable_ideas),
    ("4", "Weekly intelligence context", do_daily_intelligence_context),
]


# ===================================================================
# Menu engine
# ===================================================================

def print_top_menu():
    print("\n" + "=" * 60)
    print("  SmartSpreads CLI - Offline MCP Tool Runner")
    print("=" * 60)
    print("    A. Setup & Management")
    print("    B. Sunday Pipeline")
    print("    C. Daily Bridge")
    print("\n    q. Quit    ?. Help")
    print("=" * 60)


def print_layer_menu(key: str, name: str, items: list,
                     context: str | None = None):
    label = f"[{key}] {name}"
    if context:
        label += f"  (issue: {context})"
    print(f"\n  {label}")
    print("  " + "-" * len(label))
    for num, desc, _ in items:
        print(f"    {num:>2}. {desc}")
    print(f"\n     b. Back    q. Quit")


def run_layer(key: str, name: str, items: list,
              context: str | None = None):
    while True:
        print_layer_menu(key, name, items, context=context)
        choice = input(f"\n  {key}> ").strip().lower()
        if choice in ("b", "back"):
            return
        if choice in ("q", "quit", "exit"):
            raise SystemExit(0)
        handler = None
        for num, desc, fn in items:
            if choice == num:
                handler = (desc, fn)
                break
        if handler is None:
            print(f"  Unknown option '{choice}'.")
            continue
        desc, fn = handler
        print(f"\n  -- {desc} --")
        try:
            fn()
        except (KeyboardInterrupt, _Cancel):
            print("\n  [cancelled]")
        except Exception as e:
            print(f"\n  ERROR: {e}")


def enter_daily():
    global _daily_issue_date
    default = _get_latest_week_ended()
    try:
        _daily_issue_date = _prompt("Published issue date", default)
    except _Cancel:
        _daily_issue_date = None
        return
    print(f"  Daily bridge using issue: {_daily_issue_date}")
    run_layer("C", "Daily Bridge", LAYER_C_ITEMS,
              context=_daily_issue_date)
    _daily_issue_date = None


def main():
    print_top_menu()
    while True:
        choice = input("\nSelect> ").strip().upper()
        if choice in ("Q", "QUIT", "EXIT"):
            print("Bye.")
            break
        if choice == "?":
            print_top_menu()
            continue
        if choice == "A":
            try:
                run_layer("A", "Setup & Management", LAYER_A_ITEMS)
            except SystemExit:
                print("Bye.")
                break
        elif choice == "B":
            try:
                run_layer("B", "Sunday Pipeline", LAYER_B_ITEMS)
            except SystemExit:
                print("Bye.")
                break
        elif choice == "C":
            try:
                enter_daily()
            except SystemExit:
                print("Bye.")
                break
        else:
            print(f"  Unknown option '{choice}'. Type ? for menu.")
            continue
        print_top_menu()


if __name__ == "__main__":
    main()
