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


def _get_server():
    global _server
    if _server is None:
        import newsletter_mcp.server as srv
        _server = srv
    return _server


def _format_result(result: Any) -> str:
    if isinstance(result, (dict, list)):
        return json.dumps(result, indent=2, default=str)
    return str(result)


def _save_report(func_name: str, result: Any) -> Path:
    today = date.today().isoformat()
    ts = datetime.now().strftime("%H%M%S")
    report_dir = REPORTS_ROOT / today
    report_dir.mkdir(parents=True, exist_ok=True)
    filename = f"TS-{func_name}-{ts}.md"
    path = report_dir / filename
    content = _format_result(result)
    path.write_text(
        f"# {func_name}\n\n"
        f"**Generated:** {datetime.now().isoformat()}\n\n"
        f"```json\n{content}\n```\n",
        encoding="utf-8",
    )
    return path


def _run_and_report(func_name: str, result: Any) -> None:
    content = _format_result(result)
    print(content)
    path = _save_report(func_name, result)
    print(f"\n[saved: {path.relative_to(PROJECT_ROOT)}]")


def _prompt(msg: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"  {msg}{suffix}: ").strip()
    return val or (default or "")


def _prompt_optional(msg: str) -> str | None:
    val = input(f"  {msg} (Enter to skip): ").strip()
    return val or None


# ---------------------------------------------------------------------------
# Layer 1: Newsletter Management
# ---------------------------------------------------------------------------

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


def do_get_issue_summary():
    week = _prompt("Week ended date (YYYY-MM-DD)")
    _run_and_report("get_issue_summary",
                    _get_server().get_issue_summary(week_ended=week))


# ---------------------------------------------------------------------------
# Layer 2: Watchlist & Reporting
# ---------------------------------------------------------------------------

def do_get_watchlist():
    week = _prompt("Week ended date (YYYY-MM-DD)")
    quality = _prompt_optional("Min trade quality (e.g. 'Tier 2')")
    _run_and_report("get_watchlist",
                    _get_server().get_watchlist(week_ended=week,
                                               min_trade_quality=quality))


def do_get_watchlist_reference():
    week = _prompt("Week ended date (YYYY-MM-DD)")
    _run_and_report("get_watchlist_reference",
                    _get_server().get_watchlist_reference(week_ended=week))


def do_get_validated_report():
    week = _prompt("Week ended date (YYYY-MM-DD)")
    _run_and_report("get_validated_watchlist_report",
                    _get_server().get_validated_watchlist_report(week_ended=week))


def do_publish_issue():
    week = _prompt("Week ended date (YYYY-MM-DD)")
    out = _prompt_optional("Output directory")
    _run_and_report("publish_issue",
                    _get_server().publish_issue(week_ended=week, output_dir=out))


def do_refresh_and_publish():
    week = _prompt("Week ended date (YYYY-MM-DD)")
    out = _prompt_optional("Output directory")
    _run_and_report("refresh_and_publish_issue",
                    _get_server().refresh_and_publish_issue(week_ended=week,
                                                           output_dir=out))


# ---------------------------------------------------------------------------
# Layer 3: Export
# ---------------------------------------------------------------------------

def do_export_csv():
    week = _prompt("Week ended date (YYYY-MM-DD)")
    section = _prompt_optional("Section name filter")
    quality = _prompt_optional("Min trade quality")
    out_path = _prompt_optional("Output CSV path")
    _run_and_report("export_watchlist_csv",
                    _get_server().export_watchlist_csv(
                        week_ended=week, section_name=section,
                        min_trade_quality=quality, output_path=out_path))


def do_export_package():
    week = _prompt("Week ended date (YYYY-MM-DD)")
    out = _prompt_optional("Output directory")
    _run_and_report("export_watchlist_package",
                    _get_server().export_watchlist_package(week_ended=week,
                                                          output_dir=out))


def do_export_bundle():
    date_from = _prompt("Date from (YYYY-MM-DD)")
    date_to = _prompt("Date to (YYYY-MM-DD)")
    out = _prompt_optional("Output directory")
    _run_and_report("export_watchlist_bundle",
                    _get_server().export_watchlist_bundle(
                        date_from=date_from, date_to=date_to, output_dir=out))


# ---------------------------------------------------------------------------
# Layer 4: Intelligence & Backfill
# ---------------------------------------------------------------------------

def do_backfill_intelligence():
    _run_and_report("backfill_phase1_intelligence",
                    _get_server().backfill_phase1_intelligence())


def do_exit_schedule():
    print("  Enter positions as JSON array (e.g. "
          '[{"symbol": "/ZCZ26-/ZCH27"}]):')
    raw = input("  > ").strip()
    positions = json.loads(raw) if raw else []
    as_of = _prompt("As-of date", date.today().isoformat())
    _run_and_report("resolve_open_position_exit_schedule",
                    _get_server().resolve_open_position_exit_schedule(
                        positions=positions, as_of=as_of))


# ---------------------------------------------------------------------------
# Layer 5: Catalogs & Mappings
# ---------------------------------------------------------------------------

def do_list_schwab_catalog():
    limit = int(_prompt("Limit", "25"))
    cat = _prompt_optional("Category filter")
    _run_and_report("list_schwab_futures_catalog",
                    _get_server().list_schwab_futures_catalog(limit=limit,
                                                             category=cat))


def do_import_schwab_catalog():
    path = _prompt_optional("CSV path (Enter for default)")
    _run_and_report("import_schwab_futures_catalog",
                    _get_server().import_schwab_futures_catalog(csv_path=path))


def do_list_commodity_catalog():
    _run_and_report("list_newsletter_commodity_catalog",
                    _get_server().list_newsletter_commodity_catalog())


def do_import_commodity_catalog():
    week = _prompt_optional("Week ended (Enter for latest)")
    _run_and_report("import_newsletter_commodity_catalog",
                    _get_server().import_newsletter_commodity_catalog(
                        week_ended=week))


def do_list_contract_codes():
    _run_and_report("list_contract_month_codes",
                    _get_server().list_contract_month_codes())


def do_import_contract_codes():
    week = _prompt_optional("Week ended (Enter for latest)")
    _run_and_report("import_contract_month_codes",
                    _get_server().import_contract_month_codes(week_ended=week))


# ---------------------------------------------------------------------------
# Layer 6: Strategy & Doctrine
# ---------------------------------------------------------------------------

def do_list_strategy_docs():
    _run_and_report("list_strategy_documents",
                    _get_server().list_strategy_documents())


def do_list_strategy_sections():
    ch = _prompt_optional("Chapter number")
    _run_and_report("list_strategy_sections",
                    _get_server().list_strategy_sections(
                        chapter_number=int(ch) if ch else None))


def do_list_strategy_principles():
    cat = _prompt_optional("Category filter")
    _run_and_report("list_strategy_principles",
                    _get_server().list_strategy_principles(category=cat))


def do_import_strategy_manual():
    path = _prompt_optional("PDF path (Enter for default)")
    _run_and_report("import_strategy_manual",
                    _get_server().import_strategy_manual(pdf_path=path))


# ---------------------------------------------------------------------------
# Menu structure - layered
# ---------------------------------------------------------------------------

LAYERS = [
    ("A", "Newsletter Management", [
        ("1", "List issues", do_list_issues),
        ("2", "Verify newsletter ingested", do_verify_newsletter),
        ("3", "Ingest single newsletter PDF", do_ingest_newsletter),
        ("4", "Ingest all pending newsletters", do_ingest_pending),
        ("5", "Get issue summary", do_get_issue_summary),
    ]),
    ("B", "Watchlist & Reporting", [
        ("1", "Get watchlist", do_get_watchlist),
        ("2", "Get watchlist reference", do_get_watchlist_reference),
        ("3", "Get validated watchlist report", do_get_validated_report),
        ("4", "Publish issue", do_publish_issue),
        ("5", "Refresh & publish issue", do_refresh_and_publish),
    ]),
    ("C", "Export", [
        ("1", "Export watchlist CSV", do_export_csv),
        ("2", "Export watchlist package", do_export_package),
        ("3", "Export watchlist bundle (date range)", do_export_bundle),
    ]),
    ("D", "Intelligence & Backfill", [
        ("1", "Backfill Phase 1 intelligence", do_backfill_intelligence),
        ("2", "Resolve exit schedule", do_exit_schedule),
    ]),
    ("E", "Catalogs & Mappings", [
        ("1", "List Schwab futures catalog", do_list_schwab_catalog),
        ("2", "Import Schwab futures catalog", do_import_schwab_catalog),
        ("3", "List commodity catalog", do_list_commodity_catalog),
        ("4", "Import commodity catalog", do_import_commodity_catalog),
        ("5", "List contract month codes", do_list_contract_codes),
        ("6", "Import contract month codes", do_import_contract_codes),
    ]),
    ("F", "Strategy & Doctrine", [
        ("1", "List strategy documents", do_list_strategy_docs),
        ("2", "List strategy sections", do_list_strategy_sections),
        ("3", "List strategy principles", do_list_strategy_principles),
        ("4", "Import strategy manual", do_import_strategy_manual),
    ]),
]


def print_top_menu():
    print("\n" + "=" * 60)
    print("  SmartSpreads CLI - Offline MCP Tool Runner")
    print("  Reports saved to: reports/<date>/TS-<name>-<time>.md")
    print("=" * 60)
    for key, name, _ in LAYERS:
        print(f"    {key}. {name}")
    print(f"\n    q. Quit")
    print("=" * 60)


def print_layer_menu(key: str, name: str, items: list):
    print(f"\n  [{key}] {name}")
    print("  " + "-" * (len(name) + 4))
    for num, label, _ in items:
        print(f"    {num}. {label}")
    print(f"\n    b. Back    q. Quit")


def run_layer(key: str, name: str, items: list):
    while True:
        print_layer_menu(key, name, items)
        choice = input(f"\n  {key}> ").strip().lower()
        if choice in ("b", "back"):
            return
        if choice in ("q", "quit", "exit"):
            raise SystemExit(0)
        handler = None
        for num, label, fn in items:
            if choice == num:
                handler = (label, fn)
                break
        if handler is None:
            print(f"  Unknown option '{choice}'.")
            continue
        label, fn = handler
        print(f"\n  -- {label} --")
        try:
            fn()
        except KeyboardInterrupt:
            print("\n  [cancelled]")
        except Exception as e:
            print(f"\n  ERROR: {e}")


def main():
    print_top_menu()
    while True:
        choice = input("\nSelect layer> ").strip().upper()
        if choice in ("Q", "QUIT", "EXIT"):
            print("Bye.")
            break
        if choice == "?":
            print_top_menu()
            continue
        layer = None
        for key, name, items in LAYERS:
            if choice == key:
                layer = (key, name, items)
                break
        if layer is None:
            print(f"  Unknown layer '{choice}'. Type ? for menu.")
            continue
        try:
            run_layer(*layer)
        except SystemExit:
            print("Bye.")
            break
        print_top_menu()


if __name__ == "__main__":
    main()
