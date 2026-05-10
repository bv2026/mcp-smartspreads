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
    nl_date = issue_date or date.today().isoformat()
    report_dir = REPORTS_ROOT / nl_date
    report_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{nl_date}-{func_name}.md"
    path = report_dir / filename
    path.write_text(_build_report_md(func_name, result), encoding="utf-8")
    return path


def _run_and_report(func_name: str, result: Any,
                    issue_date: str | None = None) -> None:
    print(_format_json(result))
    path = _save_report(func_name, result, issue_date=issue_date)
    print(f"\n[saved: {path.relative_to(PROJECT_ROOT)}]")


def _prompt(msg: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"  {msg}{suffix}: ").strip()
    return val or (default or "")


def _prompt_optional(msg: str) -> str | None:
    val = input(f"  {msg} (Enter to skip): ").strip()
    return val or None


# ===================================================================
# A - Newsletter Management
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


def do_schwab_catalog():
    limit = int(_prompt("Limit", "25"))
    cat = _prompt_optional("Category filter")
    _run_and_report("list_schwab_futures_catalog",
                    _get_server().list_schwab_futures_catalog(limit=limit,
                                                             category=cat))


def do_commodity_catalog():
    _run_and_report("list_newsletter_commodity_catalog",
                    _get_server().list_newsletter_commodity_catalog())


def do_contract_codes():
    _run_and_report("list_contract_month_codes",
                    _get_server().list_contract_month_codes())


def do_import_strategy_manual():
    path = _prompt_optional("PDF path (Enter for default)")
    _run_and_report("import_strategy_manual",
                    _get_server().import_strategy_manual(pdf_path=path))


def do_strategy_principles():
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
    ("7", "View Schwab futures catalog", do_schwab_catalog),
    ("8", "View commodity catalog", do_commodity_catalog),
    ("9", "View contract month codes", do_contract_codes),
    ("10", "Import strategy manual", do_import_strategy_manual),
    ("11", "View strategy principles", do_strategy_principles),
]


# ===================================================================
# B - Newsletter Analysis (issue date set once at entry)
# ===================================================================

_active_issue_date: str | None = None


def _issue_date() -> str:
    assert _active_issue_date is not None
    return _active_issue_date


def do_issue_summary():
    _run_and_report("get_issue_summary",
                    _get_server().get_issue_summary(week_ended=_issue_date()),
                    issue_date=_issue_date())


def do_watchlist():
    quality = _prompt_optional("Min trade quality (e.g. 'Tier 2')")
    _run_and_report("get_watchlist",
                    _get_server().get_watchlist(week_ended=_issue_date(),
                                               min_trade_quality=quality),
                    issue_date=_issue_date())


def do_watchlist_reference():
    _run_and_report("get_watchlist_reference",
                    _get_server().get_watchlist_reference(
                        week_ended=_issue_date()),
                    issue_date=_issue_date())


def do_validated_report():
    _run_and_report("get_validated_watchlist_report",
                    _get_server().get_validated_watchlist_report(
                        week_ended=_issue_date()),
                    issue_date=_issue_date())


def do_exit_schedule():
    print("  Enter positions as JSON array "
          '(e.g. [{"symbol": "/ZCZ26-/ZCH27"}]):')
    raw = input("  > ").strip()
    positions = json.loads(raw) if raw else []
    as_of = _prompt("As-of date", date.today().isoformat())
    _run_and_report("resolve_open_position_exit_schedule",
                    _get_server().resolve_open_position_exit_schedule(
                        positions=positions, as_of=as_of),
                    issue_date=_issue_date())


def do_export_csv():
    section = _prompt_optional("Section name filter")
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


def do_refresh_and_publish():
    out = _prompt_optional("Output directory")
    _run_and_report("refresh_and_publish_issue",
                    _get_server().refresh_and_publish_issue(
                        week_ended=_issue_date(), output_dir=out),
                    issue_date=_issue_date())


LAYER_B_ITEMS = [
    ("1", "Issue summary", do_issue_summary),
    ("2", "Watchlist", do_watchlist),
    ("3", "Watchlist reference", do_watchlist_reference),
    ("4", "Validated watchlist report", do_validated_report),
    ("5", "Exit schedule", do_exit_schedule),
    ("6", "Export watchlist CSV", do_export_csv),
    ("7", "Export watchlist bundle (date range)", do_export_bundle),
    ("8", "Publish issue", do_publish),
    ("9", "Refresh & publish issue", do_refresh_and_publish),
]


# ===================================================================
# Menu engine
# ===================================================================

def print_top_menu():
    print("\n" + "=" * 60)
    print("  SmartSpreads CLI - Offline MCP Tool Runner")
    print("  Reports: reports/<issue-date>/<issue-date>-<func>.md")
    print("=" * 60)
    print("    A. Newsletter Management & Reference")
    print("    B. Newsletter Analysis")
    print("\n    q. Quit")
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
        except KeyboardInterrupt:
            print("\n  [cancelled]")
        except Exception as e:
            print(f"\n  ERROR: {e}")


def enter_analysis():
    global _active_issue_date
    default = _get_latest_week_ended()
    _active_issue_date = _prompt("Issue date", default)
    print(f"  Using issue: {_active_issue_date}")
    run_layer("B", "Newsletter Analysis", LAYER_B_ITEMS,
              context=_active_issue_date)
    _active_issue_date = None


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
                run_layer("A", "Newsletter Management & Reference",
                          LAYER_A_ITEMS)
            except SystemExit:
                print("Bye.")
                break
            print_top_menu()
        elif choice == "B":
            try:
                enter_analysis()
            except SystemExit:
                print("Bye.")
                break
            print_top_menu()
        else:
            print(f"  Unknown option '{choice}'. Type ? for menu.")


if __name__ == "__main__":
    main()
