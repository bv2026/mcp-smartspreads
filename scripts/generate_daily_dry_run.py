from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(r"C:\work\SmartSpreads")
SCHWAB_ROOT = Path(r"C:\work\schwab-mcp-file")
SAMPLE_PATH = Path(r"C:\Users\vsbra\OneDrive\Downloads1\SmartSpreads\Apr-15-2026-Spreads.md")
OUTPUT_PATH = ROOT / "export" / "daily-report-dry-run-2026-04-16.md"
COMPARE_PATH = ROOT / "export" / "daily-report-dry-run-2026-04-16-comparison.md"
WATCHLIST_PATH = ROOT / "published" / "watchlist.yaml"
INTELLIGENCE_PATH = ROOT / "published" / "weekly_intelligence.json"
POSITIONS_PATH = SCHWAB_ROOT / "config" / "positions.yaml"
TOS_CSV_PATH = SCHWAB_ROOT / "config" / "tos-statement.csv"
TOS_PNG_PATH = SCHWAB_ROOT / "config" / "tos-screenshot.png"
STREAM_LOG_PATH = Path(r"C:\Users\vsbra\AppData\Roaming\Claude\logs\mcp-server-schwab-smartspreads-file.log")

sys.path.insert(0, str(SCHWAB_ROOT / "src"))
sys.path.insert(0, str(ROOT / "src"))

from schwab_mcp.tos_parser import parse_futures_ytd_pl, parse_tos_futures  # noqa: E402
from newsletter_mcp import server as newsletter_server  # noqa: E402


ROOT_NAMES = {
    "/GC": "Gold",
    "/HG": "Copper",
    "/KE": "KC Wheat",
    "/VXM": "Mini VIX",
    "/ZC": "Corn butterfly",
    "/ZL": "Bean Oil butterfly",
    "/ZS": "Soybeans butterfly",
    "/ZW": "Chicago Wheat",
}


@dataclass
class SpreadSummary:
    root: str
    label: str
    spread_type: str
    legs: list[dict[str, Any]]
    entry_value: float | None
    current_value: float
    pl_dollars: float
    exit_date: str | None
    urgency_bucket: str = "unknown"
    days_to_exit: int | None = None
    alignment_status: str = "unmatched"


def _parse_sample_spread_rows(sample_text: str) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    pattern = re.compile(
        r"^\| \*\*(?P<label>.+?)\*\* \| .*? \| \*\*(?P<pl>[+\-$0-9\.,]+)\*\* \| (?P<exit>[A-Za-z]{3} \d{1,2}, \d{4}) \|$",
        re.MULTILINE,
    )
    for match in pattern.finditer(sample_text):
        label = match.group("label")
        root = "/" + label.split()[0]
        rows[root] = {
            "label": label,
            "pl": match.group("pl"),
            "exit": match.group("exit"),
        }
    return rows


def _parse_sample_sections(sample_text: str) -> list[str]:
    return re.findall(r"^(## .+|### .+)$", sample_text, flags=re.MULTILINE)


def _contract_root(symbol: str) -> str:
    match = re.match(r"(/[A-Z]+)[FGHJKMNQUVXZ]\d{2}$", symbol)
    if match:
        return match.group(1)
    return symbol


def _calc_spread_value(marks: list[float], spread_type: str) -> float:
    if spread_type == "calendar":
        return round(marks[0] - marks[1], 6)
    if spread_type == "butterfly":
        return round(marks[0] - 2 * marks[1] + marks[2], 6)
    return 0.0


def _calc_entry_value(trade_prices: list[float], spread_type: str) -> float:
    if spread_type == "calendar":
        return round(trade_prices[0] - trade_prices[1], 6)
    if spread_type == "butterfly":
        return round(trade_prices[0] - 2 * trade_prices[1] + trade_prices[2], 6)
    return 0.0


def _infer_spreads(legs: list[dict[str, Any]], sample_rows: dict[str, dict[str, str]]) -> list[SpreadSummary]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for leg in legs:
        grouped[_contract_root(leg["symbol"])].append(leg)

    summaries: list[SpreadSummary] = []
    for root, root_legs in sorted(grouped.items()):
        root_legs = sorted(root_legs, key=lambda item: item["symbol"])
        spread_type = "butterfly" if len(root_legs) == 3 else "calendar"
        current_value = _calc_spread_value([leg["mark"] for leg in root_legs], spread_type)
        entry_value = _calc_entry_value([leg["trade_price"] for leg in root_legs], spread_type)
        pl_dollars = round(sum(leg["pl_open"] for leg in root_legs), 2)
        sample_meta = sample_rows.get(root)
        label = sample_meta["label"] if sample_meta else f"{root} {ROOT_NAMES.get(root, root)}"
        summaries.append(
            SpreadSummary(
                root=root,
                label=label,
                spread_type=spread_type,
                legs=root_legs,
                entry_value=entry_value,
                current_value=current_value,
                pl_dollars=pl_dollars,
                exit_date=None,
            )
        )
    return summaries


def _find_watchlist_conflicts(watchlist: list[dict[str, Any]], open_leg_symbols: set[str]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for entry in watchlist:
        legs = set(entry.get("legs", []))
        overlap = sorted(legs & open_leg_symbols)
        if overlap:
            conflicts.append(
                {
                    "name": entry["commodity_name"],
                    "spread_code": entry["spread_code"],
                    "tier": entry.get("tier"),
                    "valid_until": entry.get("valid_until"),
                    "spread_value": entry.get("_dry_run_spread_value"),
                    "overlap": overlap,
                }
            )
    return conflicts


def _format_money(value: float | None) -> str:
    if value is None:
        return "N/A"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def _format_plain(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "NO DATA"
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


def _load_latest_dead_symbols() -> list[str]:
    if not STREAM_LOG_PATH.exists():
        return []
    text = STREAM_LOG_PATH.read_text(encoding="utf-8", errors="ignore")
    matches = re.findall(r'"dead_symbols": \[(.*?)\]', text)
    if matches:
        last = matches[-1]
        return [item.strip().strip('"') for item in last.split(",") if item.strip()]
    match = re.findall(r'"symbols": \[(.*?)\], "reason": "No ticks received after grace period', text)
    if not match:
        return []
    last = match[-1]
    return [item.strip().strip('"') for item in last.split(",") if item.strip()]


def _build_watchlist_rows(watchlist: list[dict[str, Any]], mark_lookup: dict[str, float], open_leg_symbols: set[str]) -> tuple[list[str], list[dict[str, Any]]]:
    lines: list[str] = []
    enriched: list[dict[str, Any]] = []
    idx = 1
    intra_rows = [item for item in watchlist if item.get("section") == "intra_commodity"]
    lines.append("| # | Spread | Tier | Win% | Avg $ | Legs | Spread Value | Entry Plan |")
    lines.append("|---|--------|------|------|-------|------|--------------|------------|")
    for item in intra_rows:
        leg_values = [mark_lookup.get(symbol) for symbol in item.get("legs", [])]
        spread_value = None
        if all(value is not None for value in leg_values):
            if item.get("type") == "butterfly" and len(leg_values) == 3:
                spread_value = round(leg_values[0] - 2 * leg_values[1] + leg_values[2], 6)
            elif item.get("type") == "calendar" and len(leg_values) == 2:
                spread_value = round(leg_values[0] - leg_values[1], 6)
        item["_dry_run_spread_value"] = spread_value
        entry_plan = "Watch"
        if item.get("manual_legs_required"):
            entry_plan = "Manual legs required in TOS"
        if not item.get("tradeable", True):
            entry_plan = f"Blocked: {item.get('blocked_reason')}"
        overlap = set(item.get("legs", [])) & open_leg_symbols
        if overlap:
            entry_plan = f"Conflict / overlap: {', '.join(sorted(overlap))}"
        if item["commodity_name"] == "Gold" and set(item.get("legs", [])) <= open_leg_symbols:
            entry_plan = "Entered / aligned"
        if item["commodity_name"] == "S&P 500 VIX" and "/VXMN26" in open_leg_symbols and "/VXMU26" in open_leg_symbols:
            entry_plan = "Entered manually as /VXM legs"

        legs_label = ", ".join(item.get("legs", []))
        spread_label = f"**{item['spread_code']} {item['side']}**"
        lines.append(
            f"| {idx} | {spread_label} | {item.get('tier','')} | {item.get('win_pct','')} | "
            f"{_format_money(item.get('avg_profit'))} | {legs_label} | {_format_plain(spread_value, 3)} | {entry_plan} |"
        )
        idx += 1
        enriched.append(item)
    return lines, enriched


def main() -> None:
    sample_text = SAMPLE_PATH.read_text(encoding="utf-8", errors="ignore")
    sample_rows = _parse_sample_spread_rows(sample_text)
    sample_sections = _parse_sample_sections(sample_text)

    futures = parse_tos_futures(TOS_CSV_PATH)
    ytd = parse_futures_ytd_pl(TOS_CSV_PATH)
    watchlist_doc = yaml.safe_load(WATCHLIST_PATH.read_text(encoding="utf-8"))
    intelligence = json.loads(INTELLIGENCE_PATH.read_text(encoding="utf-8"))
    positions_doc = yaml.safe_load(POSITIONS_PATH.read_text(encoding="utf-8"))

    legs = futures["futures_legs"]
    mark_lookup = {leg["symbol"]: leg["mark"] for leg in legs}
    open_leg_symbols = set(mark_lookup)
    spread_summaries = _infer_spreads(legs, sample_rows)
    exit_schedule = newsletter_server.resolve_open_position_exit_schedule(
        positions=[
            {
                "id": spread.root.lower().strip("/"),
                "name": spread.label,
                "legs": [leg["symbol"] for leg in spread.legs],
                "leg_quantities": {
                    leg["symbol"]: abs(int(leg.get("quantity", 1) or 1))
                    for leg in spread.legs
                },
            }
            for spread in spread_summaries
        ],
        as_of=futures["statement_date"],
    )
    exit_schedule_by_id = {
        position["position_id"]: position for position in exit_schedule["positions"]
    }
    for spread in spread_summaries:
        resolved = exit_schedule_by_id.get(spread.root.lower().strip("/"))
        if resolved:
            spread.exit_date = resolved.get("exit_date")
            spread.urgency_bucket = resolved.get("urgency_bucket", "unknown")
            spread.days_to_exit = resolved.get("days_to_exit")
            spread.alignment_status = resolved.get("alignment_status", "unmatched")
    configured_spread_count = len(positions_doc.get("positions", []))

    watchlist_lines, _ = _build_watchlist_rows(watchlist_doc["watchlist"], mark_lookup, open_leg_symbols)
    conflicts = _find_watchlist_conflicts(watchlist_doc["watchlist"], open_leg_symbols)
    dead_symbols = _load_latest_dead_symbols()

    statement_mtime = datetime.fromtimestamp(TOS_CSV_PATH.stat().st_mtime)
    screenshot_mtime = datetime.fromtimestamp(TOS_PNG_PATH.stat().st_mtime)
    report_date = datetime.fromisoformat(futures["statement_date"])

    lines: list[str] = []
    lines.append("## RUN STATUS")
    lines.append(f"**Thursday, {report_date.strftime('%B %d, %Y')}**")
    lines.append("")
    lines.append(f"- Published newsletter week: `{watchlist_doc['week_ended']}` ({watchlist_doc['publication_version']})")
    lines.append(f"- TOS statement freshness: `{statement_mtime.strftime('%Y-%m-%d %I:%M:%S %p')}`")
    lines.append(f"- TOS screenshot freshness: `{screenshot_mtime.strftime('%Y-%m-%d %I:%M:%S %p')}`")
    lines.append(f"- Stream dead symbols currently observed: `{', '.join(dead_symbols) if dead_symbols else 'none'}`")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## COMPLETE INTRA-COMMODITY WATCHLIST - Dry-Run Spread Values")
    lines.append(f"**{report_date.strftime('%A, %B %d, %Y')}**")
    lines.append("")
    lines.append("### ALL WATCHLIST SIGNALS")
    lines.extend(watchlist_lines)
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("### OPEN POSITIONS - From TOS CSV Export")
    lines.append("")
    lines.append("| Symbol | Side | Qty | Trade Price | Mark | P/L Open | P/L YTD | Margin Req |")
    lines.append("|--------|------|-----|-------------|------|----------|---------|------------|")
    for leg in legs:
        lines.append(
            f"| {leg['symbol']} | {leg['side']} | {leg['quantity']} | {leg['trade_price']} | {leg['mark']} | "
            f"{_format_money(leg['pl_open'])} | {_format_money(leg.get('pl_ytd'))} | {_format_money(leg.get('margin_req'))} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("### SPREAD VALUE CALCULATIONS - From TOS Marks")
    lines.append("")
    lines.append("| Spread | Type | Legs | Spread Value | Entry | P/L | Exit Date |")
    lines.append("|--------|------|------|--------------|-------|-----|-----------|")
    for spread in spread_summaries:
        legs_label = ", ".join(leg["symbol"] for leg in spread.legs)
        lines.append(
            f"| **{spread.label}** | {spread.spread_type} | {legs_label} | {_format_plain(spread.current_value, 4)} | "
            f"{_format_plain(spread.entry_value, 4)} | {_format_money(spread.pl_dollars)} | {spread.exit_date or 'Unknown'} |"
        )
    total_pl = round(sum(spread.pl_dollars for spread in spread_summaries), 2)
    lines.append("")
    lines.append(f"**Total Open Positions P/L:** **{_format_money(total_pl)}**")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## POSITION CHANGES vs. Yesterday (Apr 15)")
    lines.append("")
    lines.append("| Position | Yesterday P/L | Today P/L | Change | Status |")
    lines.append("|----------|---------------|-----------|--------|--------|")
    for spread in spread_summaries:
        sample_meta = sample_rows.get(spread.root)
        yesterday = sample_meta["pl"] if sample_meta else "N/A"
        yesterday_value = None
        if sample_meta:
            cleaned = sample_meta["pl"].replace("$", "").replace(",", "").replace("**", "")
            cleaned = cleaned.replace("(", "-").replace(")", "")
            try:
                yesterday_value = float(cleaned)
            except ValueError:
                yesterday_value = None
        delta = None if yesterday_value is None else round(spread.pl_dollars - yesterday_value, 2)
        status = "UNCH"
        if delta is not None and delta > 0:
            status = "IMPROVED"
        elif delta is not None and delta < 0:
            status = "WORSE"
        lines.append(
            f"| {spread.root} {ROOT_NAMES.get(spread.root, '')} | {yesterday} | {_format_money(spread.pl_dollars)} | "
            f"{_format_money(delta) if delta is not None else 'N/A'} | {status} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## WATCHLIST CONFLICTS")
    lines.append("")
    if conflicts:
        for conflict in conflicts:
            lines.append(f"### {conflict['spread_code']} ({conflict['tier']}, valid until {conflict['valid_until']})")
            lines.append(f"- Live dry-run spread value: `{_format_plain(conflict['spread_value'], 3)}`")
            lines.append(f"- Overlapping legs: `{', '.join(conflict['overlap'])}`")
            lines.append("- Action: do not enter while the current position set remains open.")
            lines.append("")
    else:
        lines.append("No direct watchlist leg-overlap conflicts detected.")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## EXIT SCHEDULE")
    lines.append("")
    lines.append("| Urgency | Exit Date | Days | Position | Action | Notes |")
    lines.append("|---------|-----------|------|----------|--------|-------|")
    urgency_order = {
        "overdue": 0,
        "due_today": 1,
        "due_this_week": 2,
        "next_2_weeks": 3,
        "later": 4,
        "unknown": 5,
    }
    for spread in sorted(
        spread_summaries,
        key=lambda item: (
            urgency_order.get(item.urgency_bucket, 99),
            item.days_to_exit if item.days_to_exit is not None else 9999,
            item.exit_date or "9999-12-31",
        ),
    ):
        if spread.exit_date:
            action = "EXIT / REVIEW" if spread.urgency_bucket in {"overdue", "due_today", "due_this_week"} else "MONITOR"
            lines.append(
                f"| {spread.urgency_bucket} | {spread.exit_date} | {spread.days_to_exit if spread.days_to_exit is not None else 'N/A'} | "
                f"{spread.label} | {action} | {spread.alignment_status}; current P/L {_format_money(spread.pl_dollars)} |"
            )
        else:
            lines.append(
                f"| unknown | Unknown | N/A | {spread.label} | REVIEW | No newsletter-derived exit match found |"
            )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## PORTFOLIO SUMMARY")
    lines.append("")
    lines.append(f"**Net P/L (Open Positions):** {_format_money(total_pl)}")
    ytd_value = ytd.get("net_pl")
    ytd_text = _format_money(ytd_value) if isinstance(ytd_value, (int, float)) and abs(ytd_value) < 100000 else "Validation required"
    total_margin = sum(abs(leg.get("margin_req") or 0.0) for leg in legs)
    lines.append(f"**Net P/L (YTD):** {ytd_text}")
    lines.append(f"**Total Open Spread Groupings:** {len(spread_summaries)}")
    lines.append(f"**Raw Futures Legs:** {len(legs)}")
    lines.append(f"**Total Margin Requirement (gross from CSV):** {_format_money(total_margin)}")
    lines.append(f"**Data Source:** TOS CSV Export through {futures['statement_date']}")
    lines.append("**Data Quality:** Dry run uses TOS CSV marks for legs; live stream support remains partial.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## CURRENT PORTFOLIO STATUS")
    lines.append("")
    winners = [spread for spread in spread_summaries if spread.pl_dollars > 0]
    losers = [spread for spread in spread_summaries if spread.pl_dollars <= 0]
    lines.append(f"**Winners ({len(winners)} positions):**")
    for spread in winners:
        lines.append(f"- {spread.label}: {_format_money(spread.pl_dollars)}")
    lines.append("")
    lines.append(f"**Losers / flat ({len(losers)} positions):**")
    for spread in losers:
        lines.append(f"- {spread.label}: {_format_money(spread.pl_dollars)}")
    lines.append("")
    lines.append(f"**Total drawdown:** {_format_money(total_pl)}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## NEXT ACTIONS")
    lines.append("")
    urgent_spreads = [
        spread for spread in spread_summaries if spread.urgency_bucket in {"overdue", "due_today", "due_this_week"}
    ]
    if urgent_spreads:
        lines.append(
            "1. Review exit-driven positions first: "
            + ", ".join(f"{spread.label} ({spread.urgency_bucket})" for spread in urgent_spreads[:3])
            + "."
        )
    else:
        lines.append("1. No immediate newsletter-derived exit deadlines are in the highest urgency buckets.")
    if conflicts:
        lines.append(f"2. Do not enter conflicting watchlist ideas: {', '.join(item['spread_code'] for item in conflicts)}.")
    else:
        lines.append("2. No direct watchlist leg-overlap conflicts were detected in the dry run.")
    lines.append("3. Treat VIX-family setups as manual-leg-only workflow items, not native spread entries.")
    if dead_symbols:
        lines.append(f"4. Treat these symbols as unsupported/no-tick until proven otherwise: {', '.join(dead_symbols)}.")
    if configured_spread_count != len(spread_summaries):
        lines.append(
            "5. Reconcile positions.yaml with the live TOS spread set before trusting the spread-group section fully."
        )
    else:
        lines.append(
            "5. Next hardening step: validate YTD parsing and extend TOS parsing if you want days held, mark change, and margin fields."
        )

    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    generated_sections = _parse_sample_sections("\n".join(lines))
    missing_sections = [section for section in sample_sections if section not in generated_sections]
    comparison_lines = [
        "# Daily Dry-Run Comparison",
        "",
        "## Summary",
        "",
        f"- Generated report: `{OUTPUT_PATH}`",
        f"- Sample report: `{SAMPLE_PATH}`",
        f"- Sample sections: `{len(sample_sections)}`",
        f"- Generated sections: `{len(generated_sections)}`",
        "",
        "## Matches",
        "",
        "- The generated report includes the same major workflow sections: watchlist values, imported positions, spread calculations, position changes, conflicts, exit schedule, portfolio summary, portfolio status, and next actions.",
        "- The generated report now surfaces VIX manual-leg support limits explicitly, which is an improvement over treating those as unexplained dead symbols.",
        "",
        "## Discrepancies",
        "",
        "- The current parser now extracts `P/L YTD` and `Margin Req`, but `Days` and `Mrk Chng` are still not available from this workflow.",
        "- Live watchlist pricing remains partial in the dry run because several symbols still have no ticks from Schwab streaming.",
        "- Position changes versus yesterday were computed against the sample markdown rather than a persisted daily snapshot.",
        "- The current YTD parser needs validation before its output should be trusted in a daily report.",
        "",
        "## Missing sample sections",
        "",
    ]
    if configured_spread_count != len(spread_summaries):
        comparison_lines.insert(
            15,
            f"- The current Schwab-side `positions.yaml` defines {configured_spread_count} spread groupings, while the TOS CSV produced {len(spread_summaries)} active spread groupings in the dry run.",
        )
    if missing_sections:
        comparison_lines.extend([f"- `{section}`" for section in missing_sections])
    else:
        comparison_lines.append("- None. All sample section headings are represented.")
    comparison_lines.extend(
        [
            "",
            "## Recommended fixes",
            "",
            "- Extend TOS parsing or add a screenshot-derived reconciliation path if you want `Days` and `Mrk Chng` in the generated daily report.",
            "- Persist daily snapshots in Phase 2 so `Position Changes vs. Yesterday` uses stored data instead of sample markdown parsing.",
        ]
    )
    if configured_spread_count != len(spread_summaries):
        comparison_lines.append("- Reconcile `positions.yaml` with the live TOS spread set before trusting the spread-group section fully.")
    COMPARE_PATH.write_text("\n".join(comparison_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
