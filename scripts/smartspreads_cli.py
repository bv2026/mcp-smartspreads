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


def _save_report(func_name: str, result: Any,
                 issue_date: str | None = None) -> Path:
    if issue_date:
        report_dir = REPORTS_ROOT / issue_date
        filename = f"{issue_date}-{func_name}.md"
    else:
        report_dir = REPORTS_ROOT
        filename = f"{func_name}.md"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / filename
    path.write_text(_build_report_md(func_name, result), encoding="utf-8")
    return path


def _run_and_report(func_name: str, result: Any,
                    issue_date: str | None = None) -> None:
    print(_format_json(result))
    path = _save_report(func_name, result, issue_date=issue_date)
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
    _run_and_report("list_issues", _get_server().list_issues(limit=limit))


def do_verify_newsletter():
    week = _prompt_optional("Week ended date (YYYY-MM-DD)")
    _run_and_report("verify_newsletter_ingested",
                    _get_server().verify_newsletter_ingested(week_ended=week))


def do_ingest_newsletter():
    path = _prompt_optional("PDF path (Enter for latest in data/)")
    _run_and_report("ingest_newsletter",
                    _get_server().ingest_newsletter(pdf_path=path))


def do_ingest_pending():
    _run_and_report("ingest_pending_newsletters",
                    _get_server().ingest_pending_newsletters())


def do_backfill_intelligence():
    _run_and_report("backfill_phase1_intelligence",
                    _get_server().backfill_phase1_intelligence())


def do_import_schwab_catalog():
    path = _prompt_optional("CSV path (Enter for default)")
    _run_and_report("import_schwab_futures_catalog",
                    _get_server().import_schwab_futures_catalog(csv_path=path))


def do_view_schwab_catalog():
    limit = int(_prompt("Limit", "25"))
    cat = _prompt_optional("Category filter")
    _run_and_report("list_schwab_futures_catalog",
                    _get_server().list_schwab_futures_catalog(limit=limit,
                                                             category=cat))


def do_view_commodity_catalog():
    _run_and_report("list_newsletter_commodity_catalog",
                    _get_server().list_newsletter_commodity_catalog())


def do_view_contract_codes():
    _run_and_report("list_contract_month_codes",
                    _get_server().list_contract_month_codes())


def do_import_strategy_manual():
    path = _prompt_optional("PDF path (Enter for default)")
    _run_and_report("import_strategy_manual",
                    _get_server().import_strategy_manual(pdf_path=path))


def do_view_strategy_principles():
    cat = _prompt_optional("Category filter")
    _run_and_report("list_strategy_principles",
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

def do_sunday_full_pipeline():
    """Ingest pending -> verify -> refresh & publish -> validated report."""
    srv = _get_server()
    global _latest_week_ended
    _latest_week_ended = None

    print("\n  Step 1/4: Ingesting pending newsletters...")
    ingest_result = srv.ingest_pending_newsletters()
    ingested = ingest_result.get("ingested_count", 0)
    skipped = ingest_result.get("skipped_count", 0)
    print(f"  -> Ingested: {ingested}, Skipped: {skipped}")
    _save_report("sunday_1_ingest", ingest_result)

    print("\n  Step 2/4: Verifying latest newsletter...")
    verify_result = srv.verify_newsletter_ingested(week_ended=None)
    week = verify_result.get("latest_ingested_week_ended")
    if not week:
        print("  ERROR: No newsletter found in database.")
        return
    entry_count = verify_result.get("entry_count", 0)
    print(f"  -> Latest issue: {week}, entries: {entry_count}")
    _save_report("sunday_2_verify", verify_result)

    print(f"\n  Step 3/4: Refresh & publish issue {week}...")
    publish_result = srv.refresh_and_publish_issue(week_ended=week)
    pub_version = publish_result.get("publication_version", "?")
    print(f"  -> Published: {pub_version}")
    _save_report("sunday_3_publish", publish_result, issue_date=week)

    print(f"\n  Step 4/4: Validated watchlist report for {week}...")
    section_counts = verify_result.get("section_counts", {})
    validated = srv.get_validated_watchlist_report(
        week_ended=week,
        expected_entry_count=entry_count,
        expected_intra_commodity_count=section_counts.get("intra_commodity"),
        expected_inter_commodity_count=section_counts.get("inter_commodity"),
        expected_watchlist_fingerprint=verify_result.get("watchlist_fingerprint"),
    )
    is_valid = validated.get("is_valid", False)
    tradeable = validated.get("tradeable_count", "?")
    blocked = validated.get("blocked_count", "?")
    print(f"  -> Valid: {is_valid}, Tradeable: {tradeable}, Blocked: {blocked}")
    _save_report("sunday_4_validated_report", validated, issue_date=week)

    print(f"\n  Sunday pipeline complete for {week}.")
    print(f"  Reports saved to: reports/{week}/")
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
    _save_report("sunday_ingest_verify", {
        "ingest": ingest_result, "verify": verify_result
    })


def do_sunday_publish():
    """Refresh & publish for a specific issue."""
    week = _prompt_week()
    srv = _get_server()
    print(f"\n  Refreshing & publishing {week}...")
    result = srv.refresh_and_publish_issue(week_ended=week)
    _run_and_report("refresh_and_publish_issue", result, issue_date=week)


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
    _run_and_report("validated_watchlist_report", result, issue_date=week)


def do_sunday_e2e_metrics():
    """Sunday E2E metrics: ingest -> summary -> watchlist -> publish -> validate."""
    srv = _get_server()
    global _latest_week_ended
    _latest_week_ended = None

    print("\n  Step 1: Ingesting pending newsletters...")
    ingest = srv.ingest_pending_newsletters()
    print(f"  -> Ingested: {ingest.get('ingested_count', 0)}")

    print("\n  Step 2: Verifying...")
    verify = srv.verify_newsletter_ingested(week_ended=None)
    week = verify.get("latest_ingested_week_ended")
    if not week:
        print("  ERROR: No newsletter found.")
        return
    print(f"  -> Issue: {week}")

    print(f"\n  Step 3: Issue summary for {week}...")
    summary = srv.get_issue_summary(week_ended=week)
    _save_report("sunday_e2e_summary", summary, issue_date=week)

    print(f"\n  Step 4: Watchlist for {week}...")
    watchlist = srv.get_watchlist(week_ended=week)
    entries = watchlist.get("entries", [])
    tradeable = [e for e in entries if e.get("tradeable")]
    blocked = [e for e in entries if not e.get("tradeable") and e.get("blocked_reason")]
    deferred = [e for e in entries
                if e.get("tradeable") and e.get("principle_status", {})
                and any(v == "deferred" for v in e.get("principle_status", {}).values())]
    print(f"  -> Total: {len(entries)}, Tradeable: {len(tradeable)}, "
          f"Blocked: {len(blocked)}, Deferred: {len(deferred)}")
    _save_report("sunday_e2e_watchlist", watchlist, issue_date=week)

    print(f"\n  Step 5: Refresh & publish {week}...")
    publish = srv.refresh_and_publish_issue(week_ended=week)
    print(f"  -> Published: {publish.get('publication_version', '?')}")
    _save_report("sunday_e2e_publish", publish, issue_date=week)

    print(f"\n  Step 6: Validated report for {week}...")
    section_counts = verify.get("section_counts", {})
    validated = srv.get_validated_watchlist_report(
        week_ended=week,
        expected_entry_count=verify.get("entry_count"),
        expected_intra_commodity_count=section_counts.get("intra_commodity"),
        expected_inter_commodity_count=section_counts.get("inter_commodity"),
        expected_watchlist_fingerprint=verify.get("watchlist_fingerprint"),
    )
    _save_report("sunday_e2e_validated", validated, issue_date=week)

    selectivity = (len(tradeable) / len(entries) * 100) if entries else 0
    top_blocks = {}
    for e in blocked:
        reason = (e.get("blocked_reason") or "unknown").split(".")[0].strip()
        top_blocks[reason] = top_blocks.get(reason, 0) + 1

    print(f"\n  === Sunday E2E Metrics for {week} ===")
    print(f"  Total entries:       {len(entries)}")
    print(f"  Tradeable:           {len(tradeable)}")
    print(f"  Blocked:             {len(blocked)}")
    print(f"  Deferred for daily:  {len(deferred)}")
    print(f"  Selectivity:         {selectivity:.0f}%")
    print(f"  Valid:               {validated.get('is_valid', '?')}")
    if top_blocks:
        print(f"  Top blocking reasons:")
        for reason, count in sorted(top_blocks.items(), key=lambda x: -x[1]):
            print(f"    - {reason}: {count}")
    print(f"\n  Reports saved to: reports/{week}/")


LAYER_B_ITEMS = [
    ("1", "Full Sunday pipeline (ingest->publish->validate)", do_sunday_full_pipeline),
    ("2", "Ingest & verify only", do_sunday_ingest_and_verify),
    ("3", "Publish issue", do_sunday_publish),
    ("4", "Validated watchlist report (with verify chain)", do_sunday_validated_report),
    ("5", "Sunday E2E metrics check", do_sunday_e2e_metrics),
]


# ===================================================================
# C - Newsletter Analysis (issue date set once at entry)
# ===================================================================

_active_issue_date: str | None = None


def _issue_date() -> str:
    assert _active_issue_date is not None
    return _active_issue_date


def do_issue_summary():
    _run_and_report("get_issue_summary",
                    _get_server().get_issue_summary(week_ended=_issue_date()),
                    issue_date=_issue_date())


def do_issue_brief():
    """Extract and display the issue brief in readable form."""
    result = _get_server().get_issue_summary(week_ended=_issue_date())
    brief = result.get("issue_brief", {})
    if not brief:
        print("  No issue brief found for this issue.")
        return

    print(f"\n  === Issue Brief: {_issue_date()} ===")
    print(f"\n  Headline: {brief.get('headline', 'N/A')}")

    exec_summary = brief.get("executive_summary", "")
    if exec_summary:
        print(f"\n  Executive Summary:\n  {exec_summary[:500]}")

    themes = brief.get("key_themes", [])
    if themes:
        print(f"\n  Key Themes:")
        for t in themes:
            print(f"    - {t}")

    risks = brief.get("notable_risks", [])
    if risks:
        print(f"\n  Notable Risks:")
        for r in risks:
            print(f"    - {r}")

    opps = brief.get("notable_opportunities", [])
    if opps:
        print(f"\n  Notable Opportunities:")
        for o in opps:
            print(f"    - {o}")

    ws = brief.get("watchlist_summary", {})
    if ws:
        print(f"\n  Watchlist Summary:")
        for k, v in ws.items():
            print(f"    - {k}: {v}")

    change = brief.get("change_summary", {})
    if change:
        print(f"\n  Change Summary (vs prior issue):")
        for k, v in change.items():
            print(f"    - {k}: {v}")

    _save_report("issue_brief", brief, issue_date=_issue_date())
    print(f"\n  [saved: reports/{_issue_date()}/{_issue_date()}-issue_brief.md]")


def do_watchlist():
    quality = _prompt_optional("Min trade quality (e.g. 'Tier 2')")
    _run_and_report("get_watchlist",
                    _get_server().get_watchlist(week_ended=_issue_date(),
                                               min_trade_quality=quality),
                    issue_date=_issue_date())


def do_watchlist_compact():
    """Compact watchlist: key fields only, split by section."""
    result = _get_server().get_watchlist(week_ended=_issue_date())
    entries = result.get("entries", [])

    intra = [e for e in entries if e.get("section_name") == "intra_commodity"]
    inter = [e for e in entries if e.get("section_name") == "inter_commodity"]
    cols = ["commodity_name", "spread_expression", "side", "enter_date",
            "exit_date", "trade_quality", "volatility_structure", "tradeable"]

    report_lines = [f"# Compact Watchlist: {_issue_date()}\n"]

    if intra:
        print(f"\n  Intra-Commodity ({len(intra)} rows):")
        report_lines.append(f"\n## Intra-Commodity ({len(intra)} rows)\n")
        for e in intra:
            line = (f"  {e.get('commodity_name', ''):20s} "
                    f"{e.get('spread_expression', ''):30s} "
                    f"{e.get('side', ''):5s} "
                    f"{e.get('enter_date', ''):12s} "
                    f"{e.get('exit_date', ''):12s} "
                    f"{e.get('trade_quality', ''):8s} "
                    f"{e.get('volatility_structure', ''):5s} "
                    f"{'Y' if e.get('tradeable') else 'N'}")
            print(line)
        report_lines.append(_md_table(intra, cols))

    if inter:
        print(f"\n  Inter-Commodity ({len(inter)} rows):")
        report_lines.append(f"\n## Inter-Commodity ({len(inter)} rows)\n")
        for e in inter:
            line = (f"  {e.get('commodity_name', ''):20s} "
                    f"{e.get('spread_expression', ''):30s} "
                    f"{e.get('side', ''):5s} "
                    f"{e.get('enter_date', ''):12s} "
                    f"{e.get('exit_date', ''):12s} "
                    f"{e.get('trade_quality', ''):8s} "
                    f"{e.get('volatility_structure', ''):5s} "
                    f"{'Y' if e.get('tradeable') else 'N'}")
            print(line)
        report_lines.append(_md_table(inter, cols))

    report_dir = REPORTS_ROOT / _issue_date()
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{_issue_date()}-watchlist_compact.md"
    path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"\n  [saved: {path.relative_to(PROJECT_ROOT)}]")


def do_watchlist_reference():
    _run_and_report("get_watchlist_reference",
                    _get_server().get_watchlist_reference(
                        week_ended=_issue_date()),
                    issue_date=_issue_date())


def do_principle_analysis():
    """Show principle scoring breakdown for all entries."""
    result = _get_server().get_watchlist(week_ended=_issue_date())
    entries = result.get("entries", [])

    print(f"\n  Principle Analysis for {_issue_date()} ({len(entries)} entries)")
    print(f"  {'Commodity':20s} {'Spread':25s} {'Tradeable':10s} {'Decision':50s}")
    print("  " + "-" * 105)

    for e in entries:
        tradeable = "YES" if e.get("tradeable") else "NO"
        summary = (e.get("decision_summary") or "")[:50]
        print(f"  {e.get('commodity_name', ''):20s} "
              f"{e.get('spread_code', ''):25s} "
              f"{tradeable:10s} "
              f"{summary}")

        scores = e.get("principle_scores", {})
        statuses = e.get("principle_status", {})
        if scores:
            for principle, score in scores.items():
                status = statuses.get(principle, "?")
                marker = "X" if status == "fail" else ("~" if status == "deferred" else " ")
                print(f"    [{marker}] {principle}: {score:.2f} ({status})")

    _save_report("principle_analysis", {
        "week_ended": _issue_date(),
        "entry_count": len(entries),
        "entries": [{
            "commodity_name": e.get("commodity_name"),
            "spread_code": e.get("spread_code"),
            "tradeable": e.get("tradeable"),
            "decision_summary": e.get("decision_summary"),
            "principle_scores": e.get("principle_scores"),
            "principle_status": e.get("principle_status"),
            "blocked_reason": e.get("blocked_reason"),
        } for e in entries]
    }, issue_date=_issue_date())


def do_export_csv():
    section = _prompt_optional("Section name filter (intra_commodity / inter_commodity)")
    quality = _prompt_optional("Min trade quality")
    out_path = _prompt_optional("Output CSV path")
    _run_and_report("export_watchlist_csv",
                    _get_server().export_watchlist_csv(
                        week_ended=_issue_date(), section_name=section,
                        min_trade_quality=quality, output_path=out_path),
                    issue_date=_issue_date())


def do_export_bundle():
    date_from = _prompt("Date from (YYYY-MM-DD)")
    date_to = _prompt("Date to", _issue_date())
    out = _prompt_optional("Output directory")
    _run_and_report("export_watchlist_bundle",
                    _get_server().export_watchlist_bundle(
                        date_from=date_from, date_to=date_to, output_dir=out),
                    issue_date=_issue_date())


def do_publish():
    out = _prompt_optional("Output directory")
    _run_and_report("publish_issue",
                    _get_server().publish_issue(
                        week_ended=_issue_date(), output_dir=out),
                    issue_date=_issue_date())


LAYER_C_ITEMS = [
    ("1", "Issue summary (full JSON)", do_issue_summary),
    ("2", "Issue brief (readable)", do_issue_brief),
    ("3", "Watchlist (full)", do_watchlist),
    ("4", "Watchlist (compact, by section)", do_watchlist_compact),
    ("5", "Watchlist reference rules", do_watchlist_reference),
    ("6", "Principle analysis (scoring breakdown)", do_principle_analysis),
    ("7", "Export watchlist CSV", do_export_csv),
    ("8", "Export watchlist bundle (date range)", do_export_bundle),
    ("9", "Publish issue", do_publish),
]


# ===================================================================
# D - Daily Bridge (smartspreads-mcp side only)
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
    _run_and_report("resolve_open_position_exit_schedule",
                    _get_server().resolve_open_position_exit_schedule(
                        positions=positions, as_of=as_of),
                    issue_date=_daily_date())


def do_daily_exit_from_schwab():
    """Resolve exit schedule from a Schwab positions JSON file."""
    path = _prompt("Path to Schwab positions JSON file")
    p = Path(path)
    if not p.exists():
        print(f"  File not found: {path}")
        return
    positions_data = json.loads(p.read_text(encoding="utf-8"))
    as_of = _prompt("As-of date", date.today().isoformat())
    _run_and_report("get_daily_exit_schedule",
                    _get_server().get_daily_exit_schedule(
                        schwab_futures_positions=positions_data, as_of=as_of),
                    issue_date=_daily_date())


def do_daily_issue_context():
    """Get weekly intelligence context for daily trading decisions."""
    result = _get_server().get_issue_summary(week_ended=_daily_date())
    brief = result.get("issue_brief", {})

    print(f"\n  === Daily Intelligence Context: {_daily_date()} ===")

    themes = brief.get("key_themes", [])
    if themes:
        print(f"\n  Key Themes:")
        for t in themes[:5]:
            print(f"    - {t}")

    risks = brief.get("notable_risks", [])
    if risks:
        print(f"\n  Risks to Watch:")
        for r in risks[:5]:
            print(f"    - {r}")

    opps = brief.get("notable_opportunities", [])
    if opps:
        print(f"\n  Opportunities:")
        for o in opps[:5]:
            print(f"    - {o}")

    blocked = []
    watchlist = _get_server().get_watchlist(week_ended=_daily_date())
    for e in watchlist.get("entries", []):
        if not e.get("tradeable") and e.get("blocked_reason"):
            blocked.append(e)
    if blocked:
        print(f"\n  Blocked Trades ({len(blocked)}):")
        for e in blocked:
            print(f"    - {e.get('commodity_name')} {e.get('spread_code')}: "
                  f"{e.get('blocked_reason', '')[:60]}")

    _save_report("daily_intelligence_context", {
        "week_ended": _daily_date(),
        "themes": themes,
        "risks": risks,
        "opportunities": opps,
        "blocked_trades": [{
            "commodity_name": e.get("commodity_name"),
            "spread_code": e.get("spread_code"),
            "blocked_reason": e.get("blocked_reason"),
        } for e in blocked],
    }, issue_date=_daily_date())


def do_daily_watchlist_reference():
    """Show watchlist reference rules for daily interpretation."""
    _run_and_report("get_watchlist_reference",
                    _get_server().get_watchlist_reference(
                        week_ended=_daily_date()),
                    issue_date=_daily_date())


def do_daily_tradeable_ideas():
    """Show only tradeable watchlist entries for today's action planning."""
    result = _get_server().get_watchlist(week_ended=_daily_date())
    entries = result.get("entries", [])
    tradeable = [e for e in entries if e.get("tradeable")]

    cols = ["commodity_name", "spread_expression", "side", "enter_date",
            "exit_date", "trade_quality", "volatility_structure", "decision_summary"]

    print(f"\n  Tradeable Ideas for {_daily_date()} ({len(tradeable)} of {len(entries)})")
    for e in tradeable:
        summary = (e.get("decision_summary") or "")[:60]
        print(f"  {e.get('commodity_name', ''):20s} "
              f"{e.get('spread_expression', ''):30s} "
              f"{e.get('trade_quality', ''):8s} "
              f"{summary}")

    _save_report("daily_tradeable_ideas", {
        "week_ended": _daily_date(),
        "total_entries": len(entries),
        "tradeable_count": len(tradeable),
        "entries": [{k: e.get(k) for k in cols} for e in tradeable],
    }, issue_date=_daily_date())


LAYER_D_ITEMS = [
    ("1", "Exit schedule (enter positions manually)", do_daily_exit_schedule),
    ("2", "Exit schedule (from Schwab positions JSON file)", do_daily_exit_from_schwab),
    ("3", "Weekly intelligence context", do_daily_issue_context),
    ("4", "Watchlist reference rules", do_daily_watchlist_reference),
    ("5", "Tradeable ideas only", do_daily_tradeable_ideas),
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
    print("    C. Newsletter Analysis")
    print("    D. Daily Bridge")
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


def enter_analysis():
    global _active_issue_date
    default = _get_latest_week_ended()
    try:
        _active_issue_date = _prompt("Issue date", default)
    except _Cancel:
        _active_issue_date = None
        return
    print(f"  Analyzing issue: {_active_issue_date}")
    run_layer("C", "Newsletter Analysis", LAYER_C_ITEMS,
              context=_active_issue_date)
    _active_issue_date = None


def enter_daily():
    global _daily_issue_date
    default = _get_latest_week_ended()
    try:
        _daily_issue_date = _prompt("Published issue date", default)
    except _Cancel:
        _daily_issue_date = None
        return
    print(f"  Daily bridge using issue: {_daily_issue_date}")
    run_layer("D", "Daily Bridge", LAYER_D_ITEMS,
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
                enter_analysis()
            except SystemExit:
                print("Bye.")
                break
        elif choice == "D":
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
