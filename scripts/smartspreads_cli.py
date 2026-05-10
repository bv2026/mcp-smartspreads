#!/usr/bin/env python3
"""
SmartSpreads CLI — menu-driven access to core MCP functions.

Use this when Claude Code is unavailable (rate limits, outages, etc.).
Run from the SmartSpreads project root:

    python scripts/smartspreads_cli.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

# Ensure src/ is importable
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

# ── lazy import of server module (heavy) ─────────────────────────────────────
_server = None

def _get_server():
    global _server
    if _server is None:
        import newsletter_mcp.server as srv
        _server = srv
    return _server


def _pp(result: Any) -> None:
    """Pretty-print a dict/list result."""
    if isinstance(result, (dict, list)):
        print(json.dumps(result, indent=2, default=str))
    else:
        print(result)


def _prompt(msg: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{msg}{suffix}: ").strip()
    return val or (default or "")


def _prompt_optional(msg: str) -> str | None:
    val = input(f"{msg} (Enter to skip): ").strip()
    return val or None


# ── Menu items ───────────────────────────────────────────────────────────────

def do_list_issues():
    limit = int(_prompt("How many issues", "10"))
    srv = _get_server()
    _pp(srv.list_issues(limit=limit))


def do_verify_newsletter():
    week = _prompt_optional("Week ended date (YYYY-MM-DD)")
    srv = _get_server()
    _pp(srv.verify_newsletter_ingested(week_ended=week))


def do_ingest_newsletter():
    path = _prompt_optional("PDF path (Enter for latest in data/)")
    srv = _get_server()
    _pp(srv.ingest_newsletter(pdf_path=path))


def do_ingest_pending():
    srv = _get_server()
    _pp(srv.ingest_pending_newsletters())


def do_get_issue_summary():
    week = _prompt("Week ended date (YYYY-MM-DD)")
    srv = _get_server()
    _pp(srv.get_issue_summary(week_ended=week))


def do_get_watchlist():
    week = _prompt("Week ended date (YYYY-MM-DD)")
    quality = _prompt_optional("Min trade quality (e.g. 'Tier 2')")
    srv = _get_server()
    _pp(srv.get_watchlist(week_ended=week, min_trade_quality=quality))


def do_get_watchlist_reference():
    week = _prompt("Week ended date (YYYY-MM-DD)")
    srv = _get_server()
    _pp(srv.get_watchlist_reference(week_ended=week))


def do_get_validated_report():
    week = _prompt("Week ended date (YYYY-MM-DD)")
    srv = _get_server()
    _pp(srv.get_validated_watchlist_report(week_ended=week))


def do_publish_issue():
    week = _prompt("Week ended date (YYYY-MM-DD)")
    out = _prompt_optional("Output directory")
    srv = _get_server()
    _pp(srv.publish_issue(week_ended=week, output_dir=out))


def do_refresh_and_publish():
    week = _prompt("Week ended date (YYYY-MM-DD)")
    out = _prompt_optional("Output directory")
    srv = _get_server()
    _pp(srv.refresh_and_publish_issue(week_ended=week, output_dir=out))


def do_export_csv():
    week = _prompt("Week ended date (YYYY-MM-DD)")
    section = _prompt_optional("Section name filter")
    quality = _prompt_optional("Min trade quality")
    out_path = _prompt_optional("Output CSV path")
    srv = _get_server()
    _pp(srv.export_watchlist_csv(
        week_ended=week,
        section_name=section,
        min_trade_quality=quality,
        output_path=out_path,
    ))


def do_export_package():
    week = _prompt("Week ended date (YYYY-MM-DD)")
    out = _prompt_optional("Output directory")
    srv = _get_server()
    _pp(srv.export_watchlist_package(week_ended=week, output_dir=out))


def do_export_bundle():
    date_from = _prompt("Date from (YYYY-MM-DD)")
    date_to = _prompt("Date to (YYYY-MM-DD)")
    out = _prompt_optional("Output directory")
    srv = _get_server()
    _pp(srv.export_watchlist_bundle(date_from=date_from, date_to=date_to, output_dir=out))


def do_backfill_intelligence():
    srv = _get_server()
    _pp(srv.backfill_phase1_intelligence())


def do_list_schwab_catalog():
    limit = int(_prompt("Limit", "25"))
    cat = _prompt_optional("Category filter")
    srv = _get_server()
    _pp(srv.list_schwab_futures_catalog(limit=limit, category=cat))


def do_import_schwab_catalog():
    path = _prompt_optional("CSV path (Enter for default)")
    srv = _get_server()
    _pp(srv.import_schwab_futures_catalog(csv_path=path))


def do_list_commodity_catalog():
    srv = _get_server()
    _pp(srv.list_newsletter_commodity_catalog())


def do_import_commodity_catalog():
    week = _prompt_optional("Week ended (Enter for latest)")
    srv = _get_server()
    _pp(srv.import_newsletter_commodity_catalog(week_ended=week))


def do_list_contract_codes():
    srv = _get_server()
    _pp(srv.list_contract_month_codes())


def do_import_contract_codes():
    week = _prompt_optional("Week ended (Enter for latest)")
    srv = _get_server()
    _pp(srv.import_contract_month_codes(week_ended=week))


def do_list_strategy_docs():
    srv = _get_server()
    _pp(srv.list_strategy_documents())


def do_list_strategy_sections():
    ch = _prompt_optional("Chapter number")
    srv = _get_server()
    _pp(srv.list_strategy_sections(chapter_number=int(ch) if ch else None))


def do_list_strategy_principles():
    cat = _prompt_optional("Category filter")
    srv = _get_server()
    _pp(srv.list_strategy_principles(category=cat))


def do_import_strategy_manual():
    path = _prompt_optional("PDF path (Enter for default)")
    srv = _get_server()
    _pp(srv.import_strategy_manual(pdf_path=path))


def do_exit_schedule():
    week = _prompt("Week ended date of latest issue (YYYY-MM-DD)")
    print("Enter positions as JSON array (e.g. [{\"symbol\": \"/ZCZ26-/ZCH27\"}]):")
    raw = input("> ").strip()
    positions = json.loads(raw) if raw else []
    as_of = _prompt("As-of date", date.today().isoformat())
    srv = _get_server()
    _pp(srv.resolve_open_position_exit_schedule(positions=positions, as_of=as_of))


# ── Menu definition ──────────────────────────────────────────────────────────

MENU_SECTIONS = [
    ("Newsletter Management", [
        ("1", "List issues", do_list_issues),
        ("2", "Verify newsletter ingested", do_verify_newsletter),
        ("3", "Ingest single newsletter PDF", do_ingest_newsletter),
        ("4", "Ingest all pending newsletters", do_ingest_pending),
        ("5", "Get issue summary", do_get_issue_summary),
    ]),
    ("Watchlist & Reporting", [
        ("6", "Get watchlist", do_get_watchlist),
        ("7", "Get watchlist reference", do_get_watchlist_reference),
        ("8", "Get validated watchlist report", do_get_validated_report),
        ("9", "Publish issue", do_publish_issue),
        ("10", "Refresh & publish issue", do_refresh_and_publish),
    ]),
    ("Export", [
        ("11", "Export watchlist CSV", do_export_csv),
        ("12", "Export watchlist package", do_export_package),
        ("13", "Export watchlist bundle (date range)", do_export_bundle),
    ]),
    ("Intelligence & Backfill", [
        ("14", "Backfill Phase 1 intelligence", do_backfill_intelligence),
        ("15", "Resolve exit schedule", do_exit_schedule),
    ]),
    ("Catalogs & Mappings", [
        ("16", "List Schwab futures catalog", do_list_schwab_catalog),
        ("17", "Import Schwab futures catalog", do_import_schwab_catalog),
        ("18", "List commodity catalog", do_list_commodity_catalog),
        ("19", "Import commodity catalog", do_import_commodity_catalog),
        ("20", "List contract month codes", do_list_contract_codes),
        ("21", "Import contract month codes", do_import_contract_codes),
    ]),
    ("Strategy & Doctrine", [
        ("22", "List strategy documents", do_list_strategy_docs),
        ("23", "List strategy sections", do_list_strategy_sections),
        ("24", "List strategy principles", do_list_strategy_principles),
        ("25", "Import strategy manual", do_import_strategy_manual),
    ]),
]


def print_menu():
    print("\n" + "=" * 60)
    print("  SmartSpreads CLI - Offline MCP Tool Runner")
    print("=" * 60)
    for section_name, items in MENU_SECTIONS:
        print(f"\n  {section_name}")
        print("  " + "-" * len(section_name))
        for key, label, _ in items:
            print(f"    {key:>2}. {label}")
    print(f"\n     q. Quit")
    print("=" * 60)


def main():
    print_menu()
    while True:
        choice = input("\nSelect> ").strip().lower()
        if choice in ("q", "quit", "exit"):
            print("Bye.")
            break

        if choice == "?":
            print_menu()
            continue

        handler = None
        for _, items in MENU_SECTIONS:
            for key, label, fn in items:
                if choice == key:
                    handler = (label, fn)
                    break
            if handler:
                break

        if handler is None:
            print(f"Unknown option '{choice}'. Type ? for menu.")
            continue

        label, fn = handler
        print(f"\n-- {label} --")
        try:
            fn()
        except KeyboardInterrupt:
            print("\n[cancelled]")
        except Exception as e:
            print(f"\nERROR: {e}")


if __name__ == "__main__":
    main()
