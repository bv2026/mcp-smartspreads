from __future__ import annotations

from collections import Counter
import csv
import hashlib
from datetime import UTC, date, datetime, timedelta
import json
from io import StringIO
from pathlib import Path
import re
from typing import Any

from mcp.server.fastmcp import FastMCP
from sqlalchemy import desc, select

from .config import Settings
from .business import IssueBriefDraft, IssueBriefService
from .database import (
    Database,
    IssueBrief,
    IssueDelta,
    Newsletter,
    NewsletterSection,
    NewsletterCommodityCatalog,
    ParserRun,
    PublicationArtifact,
    PublicationRun,
    SchwabFuturesCatalog,
    WatchlistEntry,
    WatchlistReferenceRecord,
)
from .parser import parse_newsletter


PARSER_VERSION = "phase1-v1"
PUBLICATION_SCHEMA_VERSION = "1.0"
CONTRACT_CODE_RE = re.compile(r"^(?P<root>[A-Z]+)(?P<month>[FGHJKMNQUVXZ])(?P<year>\d{2})$")
SPREAD_TOKEN_RE = re.compile(r"([+-]?)(?:(\d+)\*)?([A-Z]+[FGHJKMNQUVXZ]\d{2})")
ROOT_SYMBOL_MAP = {
    "BO": "/ZL",
    "C": "/ZC",
    "CC": "/CC",
    "CL": "/CL",
    "CT": "/CT",
    "FC": "/GF",
    "GC": "/GC",
    "GO": None,
    "HG": "/HG",
    "HO": "/HO",
    "KW": "/KE",
    "LC": "/LE",
    "LH": "/HE",
    "MW": "/MWE",
    "NG": "/NG",
    "RB": "/RB",
    "S": "/ZS",
    "SB": "/SB",
    "SI": "/SI",
    "SM": "/ZM",
    "VX": "/VX",
    "W": "/ZW",
}
ROOT_BLOCK_REASONS = {
    "BC": "Brent crude is not available in TOS.",
    "FC": "Feeder Cattle is in the doghouse and should never be traded.",
    "GO": "Gasoil is not available in TOS.",
    "SB": "Sugar #11 is not tradeable as a spread in TOS.",
}
settings = Settings.from_env()
database = Database(settings.database_url)
database.create_schema()
mcp = FastMCP("newsletter-mcp")
DEFAULT_SCHWAB_CATALOG_CSV = Path(r"C:\Users\vsbra\OneDrive\Downloads1\futures-tradelog - Sheet13.csv")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _seed_record(parsed) -> dict[str, Any]:
    return {
        "source_file": str(parsed.source_file),
        "file_hash": parsed.file_hash,
        "title": parsed.title,
        "week_ended": parsed.week_ended,
        "raw_text": parsed.raw_text,
        "overall_summary": parsed.overall_summary,
        "metadata_json": parsed.metadata,
        "issue_code": parsed.source_file.stem,
        "issue_version": None,
        "issue_status": "validated",
        "page_count": parsed.metadata.get("page_count"),
        "source_modified_at": datetime.fromtimestamp(parsed.source_file.stat().st_mtime),
    }


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_key_part(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized


def _build_entry_key(week_ended: date, row: Any) -> str:
    return "|".join(
        [
            _normalize_key_part(row.section_name),
            _normalize_key_part(row.commodity_name),
            _normalize_key_part(row.spread_code),
            row.side.lower(),
        ]
    )


def _canonical_entry_key(newsletter: Newsletter, entry: WatchlistEntry) -> str:
    return _build_entry_key(newsletter.week_ended, entry)


def _classify_section_type(section_name: str) -> str:
    name = section_name.lower()
    if "watch list" in name:
        return "watchlist_page"
    if "trade calendar" in name:
        return "trade_calendar"
    if "margin summary" in name:
        return "margin_summary"
    if "macro" in name:
        return "macro_commentary"
    return "article"


def _parse_contract_code(contract_code: str) -> dict[str, str]:
    match = CONTRACT_CODE_RE.match(contract_code)
    if match is None:
        return {"root": contract_code, "month": "", "year": ""}
    return match.groupdict()


def _resolve_newsletter_root_symbol(root: str) -> dict[str, Any]:
    if root in ROOT_BLOCK_REASONS:
        return {
            "root_code": root,
            "schwab_root": None,
            "blocked_reason": ROOT_BLOCK_REASONS[root],
            "mapping_source": "policy_block",
        }

    with database.session() as session:
        active_schwab_roots = set(
            session.execute(
                select(SchwabFuturesCatalog.symbol_root).where(SchwabFuturesCatalog.is_active.is_(True))
            ).scalars().all()
        )
        has_catalog = bool(active_schwab_roots)
        newsletter_mapping = session.execute(
            select(NewsletterCommodityCatalog).where(NewsletterCommodityCatalog.newsletter_root == root)
        ).scalar_one_or_none()

        if newsletter_mapping is not None and newsletter_mapping.is_tradeable_by_policy is False:
            return {
                "root_code": root,
                "schwab_root": newsletter_mapping.preferred_schwab_root,
                "blocked_reason": newsletter_mapping.policy_block_reason
                or f"Newsletter policy marks {root} as not tradeable.",
                "mapping_source": "newsletter_policy",
            }

        if newsletter_mapping is not None and newsletter_mapping.preferred_schwab_root:
            schwab_root = newsletter_mapping.preferred_schwab_root
            mapping_source = "newsletter_catalog"
        else:
            direct_root = f"/{root}"
            if direct_root in active_schwab_roots:
                schwab_root = direct_root
                mapping_source = "schwab_catalog_direct"
            else:
                schwab_root = ROOT_SYMBOL_MAP.get(root)
                mapping_source = "fallback_map"

        if schwab_root is None:
            return {
                "root_code": root,
                "schwab_root": None,
                "blocked_reason": f"No Schwab symbol mapping configured for contract root {root}.",
                "mapping_source": mapping_source,
            }

        if has_catalog and schwab_root not in active_schwab_roots:
            return {
                "root_code": root,
                "schwab_root": schwab_root,
                "blocked_reason": f"{schwab_root} is not present in the imported Schwab futures catalog.",
                "mapping_source": mapping_source,
            }

        return {
            "root_code": root,
            "schwab_root": schwab_root,
            "blocked_reason": None,
            "mapping_source": mapping_source,
        }


def _tos_symbol_for_contract(contract_code: str) -> tuple[str | None, str | None, str]:
    parsed = _parse_contract_code(contract_code)
    root = parsed["root"]
    resolution = _resolve_newsletter_root_symbol(root)
    if resolution["schwab_root"] is None:
        return None, resolution["blocked_reason"], root
    return f"{resolution['schwab_root']}{parsed['month']}{parsed['year']}", resolution["blocked_reason"], root


def _parse_spread_legs(spread_code: str) -> list[dict[str, Any]]:
    legs: list[dict[str, Any]] = []
    for sign, multiplier_text, contract_code in SPREAD_TOKEN_RE.findall(spread_code):
        multiplier = int(multiplier_text or "1")
        operator = sign or "+"
        tos_symbol, blocked_reason, root = _tos_symbol_for_contract(contract_code)
        resolution = _resolve_newsletter_root_symbol(root)
        for copy_index in range(multiplier):
            legs.append(
                {
                    "operator": operator,
                    "multiplier": multiplier,
                    "copy_index": copy_index,
                    "contract_code": contract_code,
                    "root_code": root,
                    "resolved_root": resolution["schwab_root"],
                    "mapping_source": resolution["mapping_source"],
                    "tos_symbol": tos_symbol,
                    "tradeable": blocked_reason is None,
                    "blocked_reason": blocked_reason,
                }
            )
    return legs


def _infer_watchlist_type(entry: WatchlistEntry, legs: list[dict[str, Any]]) -> str:
    unique_roots = {leg["root_code"] for leg in legs}
    multiplier_pattern = [leg["multiplier"] for leg in legs]
    if entry.section_name == "inter_commodity" or len(unique_roots) > 1:
        return "intermarket"
    if len(legs) == 2:
        return "calendar"
    if len(legs) >= 3 and max(multiplier_pattern, default=1) >= 2:
        return "butterfly"
    return "multi_leg"


def _derive_watchlist_tier(entry: WatchlistEntry) -> str:
    if entry.trade_quality:
        return entry.trade_quality
    if entry.risk_level is not None:
        return f"Risk {entry.risk_level}"
    if entry.portfolio:
        return entry.portfolio
    return "Unclassified"


def _derive_entry_tradeability(entry: WatchlistEntry, legs: list[dict[str, Any]]) -> tuple[bool, str | None]:
    reasons = [leg["blocked_reason"] for leg in legs if leg["blocked_reason"]]
    if entry.trade_quality == "Tier 4":
        reasons.append("Tier 4 trades are excluded by policy.")
    if entry.ridx < 30:
        reasons.append("RIDX is below the minimum threshold of 30.")
    if reasons:
        deduped = []
        for reason in reasons:
            if reason not in deduped:
                deduped.append(reason)
        return False, " ".join(deduped)
    return True, None


def _build_watchlist_publication_entry(
    newsletter: Newsletter,
    entry: WatchlistEntry,
) -> dict[str, Any]:
    legs = _parse_spread_legs(entry.spread_code)
    tradeable, blocked_reason = _derive_entry_tradeability(entry, legs)
    tos_symbols = [leg["tos_symbol"] for leg in legs if leg["tos_symbol"]]
    unique_symbols = list(dict.fromkeys(tos_symbols))
    unique_roots = list(dict.fromkeys(leg["root_code"] for leg in legs))
    canonical_key = _canonical_entry_key(newsletter, entry)

    if len(unique_roots) == 1 and ROOT_SYMBOL_MAP.get(unique_roots[0]) is not None:
        symbol = ROOT_SYMBOL_MAP[unique_roots[0]]
    else:
        symbol = ",".join(symbol for symbol in dict.fromkeys(unique_symbols) if symbol)

    return {
        "id": f"wl_{canonical_key.replace('|', '_')}",
        "entry_key": canonical_key,
        "name": entry.commodity_name,
        "commodity_name": entry.commodity_name,
        "spread_code": entry.spread_code,
        "symbol": symbol,
        "legs": tos_symbols,
        "leg_details": legs,
        "type": _infer_watchlist_type(entry, legs),
        "side": entry.side,
        "section": entry.section_name,
        "category": entry.category,
        "enter_date": entry.enter_date.isoformat(),
        "exit_date": entry.exit_date.isoformat(),
        "valid_until": (newsletter.week_ended + timedelta(days=7)).isoformat(),
        "win_pct": entry.win_pct,
        "avg_value": entry.avg_profit,
        "avg_profit": entry.avg_profit,
        "tier": _derive_watchlist_tier(entry),
        "volatility_structure": entry.volatility_structure,
        "portfolio": entry.portfolio,
        "risk_level": entry.risk_level,
        "trade_quality": entry.trade_quality,
        "ridx": entry.ridx,
        "five_year_corr": entry.five_year_corr,
        "page_number": entry.page_number,
        "action": f"Review {entry.section_name} idea from {newsletter.week_ended.isoformat()} newsletter.",
        "tradeable": tradeable,
        "blocked_reason": blocked_reason,
    }


def _serialize_publication_yaml(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2)


def _normalize_catalog_text(value: str | None) -> str:
    if value is None:
        return ""
    cleaned = value.replace("\ufeff", "").replace("Â®", "®").replace("Â", "").strip()
    return cleaned


def _parse_yes_no(value: str | None) -> bool | None:
    normalized = _normalize_catalog_text(value).lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    return None


def _is_catalog_section_row(row: list[str]) -> bool:
    if not row:
        return False
    first = _normalize_catalog_text(row[0])
    if not first or first == "View Less":
        return False
    remaining = [_normalize_catalog_text(cell) for cell in row[1:]]
    return all(not cell for cell in remaining)


def _extract_schwab_catalog_rows(csv_path: Path) -> list[dict[str, Any]]:
    parsed_rows: list[dict[str, Any]] = []
    seen_roots: set[str] = set()
    current_category = "Uncategorized"

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for raw_row in reader:
            row = [_normalize_catalog_text(cell) for cell in raw_row]
            if not any(row):
                continue
            if _is_catalog_section_row(row):
                current_category = row[0]
                continue
            if row[0] == "View Less":
                continue
            if row[0] == "" and len(row) > 1 and row[1] == "Symbol":
                continue

            display_name = row[0] if len(row) > 0 else ""
            symbol_root = row[1] if len(row) > 1 else ""
            if not display_name or not symbol_root.startswith("/"):
                continue
            if symbol_root in seen_roots:
                continue
            seen_roots.add(symbol_root)

            parsed_rows.append(
                {
                    "symbol_root": symbol_root,
                    "display_name": display_name,
                    "category": current_category,
                    "options_tradable": _parse_yes_no(row[2] if len(row) > 2 else None),
                    "multiplier": row[3] if len(row) > 3 else None,
                    "minimum_tick_size": row[4] if len(row) > 4 else None,
                    "settlement_type": row[5] if len(row) > 5 else None,
                    "trading_hours": row[6] if len(row) > 6 else None,
                    "is_micro": "micro" in display_name.lower(),
                    "stream_supported": None,
                }
            )

    return parsed_rows


def _serialize_schwab_catalog_row(record: SchwabFuturesCatalog) -> dict[str, Any]:
    return {
        "symbol_root": record.symbol_root,
        "display_name": record.display_name,
        "category": record.category,
        "options_tradable": record.options_tradable,
        "multiplier": record.multiplier,
        "minimum_tick_size": record.minimum_tick_size,
        "settlement_type": record.settlement_type,
        "trading_hours": record.trading_hours,
        "is_micro": record.is_micro,
        "stream_supported": record.stream_supported,
        "is_active": record.is_active,
        "source_file": record.source_file,
        "source_modified_at": record.source_modified_at.isoformat() if record.source_modified_at else None,
    }


def _build_issue_brief_markdown(
    newsletter: Newsletter,
    brief: IssueBrief | None,
    delta: IssueDelta | None,
    reference: WatchlistReferenceRecord | None,
    entries: list[WatchlistEntry],
) -> str:
    brief_data = _issue_brief_fallback(newsletter, entries, delta, reference, brief)
    return IssueBriefService.build_issue_brief_markdown(
        week_ended=newsletter.week_ended.isoformat(),
        title=newsletter.title,
        executive_summary=brief_data.executive_summary,
        entries=entries,
        brief_data=brief_data,
        delta_summary_text=delta.summary_text if delta is not None else None,
        reference=reference,
    )


def _build_weekly_intelligence_payload(
    newsletter: Newsletter,
    entries: list[WatchlistEntry],
    brief: IssueBrief | None,
    delta: IssueDelta | None,
    reference: WatchlistReferenceRecord | None,
) -> dict[str, Any]:
    brief_data = _issue_brief_fallback(newsletter, entries, delta, reference, brief)
    return {
        "schema_version": PUBLICATION_SCHEMA_VERSION,
        "week_ended": newsletter.week_ended.isoformat(),
        "newsletter_id": newsletter.id,
        "title": newsletter.title,
        "issue_status": newsletter.issue_status,
        "source_file": newsletter.source_file,
        "published_context": {
            "entry_count": len(entries),
            "section_counts": brief_data.watchlist_summary.get("section_counts", {}),
        },
        "issue_brief": {
            "headline": brief_data.headline,
            "executive_summary": brief_data.executive_summary,
            "watchlist_summary": brief_data.watchlist_summary,
            "change_summary": brief_data.change_summary,
            "key_themes": brief_data.key_themes,
            "notable_risks": brief_data.notable_risks,
            "notable_opportunities": brief_data.notable_opportunities,
        },
        "issue_delta": {
            "summary_text": delta.summary_text if delta is not None else None,
            "added_entries": delta.added_entries_json if delta is not None else [],
            "removed_entries": delta.removed_entries_json if delta is not None else [],
            "changed_entries": delta.changed_entries_json if delta is not None else [],
        },
        "watchlist_reference": _serialize_watchlist_reference(reference),
    }


def _build_publication_manifest(
    *,
    newsletter: Newsletter,
    publication_version: str,
    publication_run_id: int,
    output_root: Path,
    files: dict[str, str],
    watchlist_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": PUBLICATION_SCHEMA_VERSION,
        "publication_run_id": publication_run_id,
        "publication_version": publication_version,
        "week_ended": newsletter.week_ended.isoformat(),
        "newsletter_id": newsletter.id,
        "title": newsletter.title,
        "published_at": _utcnow().isoformat(),
        "output_root": str(output_root),
        "files": files,
        "watchlist_count": len(watchlist_payload["watchlist"]),
}


def _summarize_watchlist_rows(rows: list[Any]) -> dict[str, Any]:
    return IssueBriefService.summarize_watchlist_rows(rows)


def _build_issue_brief_draft(
    *,
    title: str,
    executive_summary: str,
    entries: list[Any],
    delta: IssueDelta | None,
    reference: WatchlistReferenceRecord | None,
) -> IssueBriefDraft:
    return IssueBriefService.build_issue_brief(
        title=title,
        executive_summary=executive_summary,
        entries=entries,
        delta=delta,
        reference=reference,
    )


def _apply_issue_brief_draft(
    issue_brief: IssueBrief,
    *,
    parser_run_id: int | None,
    brief_data: IssueBriefDraft,
) -> None:
    issue_brief.parser_run_id = parser_run_id
    issue_brief.brief_status = issue_brief.brief_status or "draft"
    issue_brief.headline = brief_data.headline
    issue_brief.executive_summary = brief_data.executive_summary
    issue_brief.key_themes_json = brief_data.key_themes
    issue_brief.notable_risks_json = brief_data.notable_risks
    issue_brief.notable_opportunities_json = brief_data.notable_opportunities
    issue_brief.watchlist_summary_json = brief_data.watchlist_summary
    issue_brief.change_summary_json = brief_data.change_summary


def _issue_brief_fallback(
    newsletter: Newsletter,
    entries: list[WatchlistEntry],
    delta: IssueDelta | None,
    reference: WatchlistReferenceRecord | None,
    brief: IssueBrief | None,
) -> IssueBriefDraft:
    if brief is not None:
        return IssueBriefDraft(
            headline=brief.headline or newsletter.title,
            executive_summary=brief.executive_summary,
            key_themes=brief.key_themes_json,
            notable_risks=brief.notable_risks_json,
            notable_opportunities=brief.notable_opportunities_json,
            watchlist_summary=brief.watchlist_summary_json,
            change_summary=brief.change_summary_json,
        )
    return _build_issue_brief_draft(
        title=newsletter.title,
        executive_summary=newsletter.overall_summary,
        entries=entries,
        delta=delta,
        reference=reference,
    )


def _serialize_entry_delta(current: WatchlistEntry, previous: WatchlistEntry) -> dict[str, Any]:
    changed_fields: list[str] = []
    for field_name in ("side", "enter_date", "exit_date", "trade_quality", "risk_level", "volatility_structure"):
        if getattr(current, field_name) != getattr(previous, field_name):
            changed_fields.append(field_name)

    return {
        "entry_key": current.entry_key,
        "commodity_name": current.commodity_name,
        "spread_code": current.spread_code,
        "changed_fields": changed_fields,
        "current": _serialize_watchlist_entry(current),
        "previous": _serialize_watchlist_entry(previous),
    }


def _compute_issue_delta(
    current_entries: list[WatchlistEntry],
    previous_entries: list[WatchlistEntry],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str]:
    current_map = {entry.entry_key: entry for entry in current_entries if entry.entry_key}
    previous_map = {entry.entry_key: entry for entry in previous_entries if entry.entry_key}

    added_keys = sorted(set(current_map) - set(previous_map))
    removed_keys = sorted(set(previous_map) - set(current_map))
    changed_keys = sorted(
        key
        for key in set(current_map) & set(previous_map)
        if any(
            getattr(current_map[key], field_name) != getattr(previous_map[key], field_name)
            for field_name in ("side", "enter_date", "exit_date", "trade_quality", "risk_level", "volatility_structure")
        )
    )

    added = [_serialize_watchlist_entry(current_map[key]) for key in added_keys]
    removed = [_serialize_watchlist_entry(previous_map[key]) for key in removed_keys]
    changed = [_serialize_entry_delta(current_map[key], previous_map[key]) for key in changed_keys]

    summary = (
        f"Added {len(added)} entries, removed {len(removed)} entries, "
        f"and changed {len(changed)} carried entries versus the prior issue."
    )
    return added, removed, changed, summary


def _seed_phase1_records(session: Any, newsletter: Newsletter) -> dict[str, Any]:
    parser_run = session.execute(
        select(ParserRun).where(ParserRun.newsletter_id == newsletter.id)
    ).scalar_one_or_none()
    if parser_run is None:
        parser_run = ParserRun(
            newsletter_id=newsletter.id,
            parser_version=PARSER_VERSION,
            status="completed",
            run_started_at=newsletter.ingested_at,
            run_completed_at=newsletter.ingested_at,
            page_count_detected=newsletter.page_count or newsletter.metadata_json.get("page_count"),
            pages_parsed=newsletter.page_count or newsletter.metadata_json.get("page_count"),
            watchlist_entry_count=len(newsletter.watchlist_entries),
            section_count=len(newsletter.sections),
            warning_count=0,
            warnings_json=[],
            metrics_json={
                "has_watchlist_reference": newsletter.watchlist_reference is not None,
                "source_filename": Path(newsletter.source_file).name,
                "backfilled": True,
            },
        )
        session.add(parser_run)
        session.flush()

    if not newsletter.issue_status:
        newsletter.issue_status = "validated"
    if newsletter.page_count is None:
        newsletter.page_count = newsletter.metadata_json.get("page_count")

    for section in newsletter.sections:
        if section.parser_run_id is None:
            section.parser_run_id = parser_run.id
        if section.section_type is None:
            section.section_type = _classify_section_type(section.name)
        if section.extraction_confidence is None:
            section.extraction_confidence = 0.95
        if section.metadata_json is None:
            section.metadata_json = {}

    for entry in newsletter.watchlist_entries:
        canonical_key = _canonical_entry_key(newsletter, entry)
        if entry.entry_key != canonical_key:
            entry.entry_key = canonical_key
        if entry.parser_run_id is None:
            entry.parser_run_id = parser_run.id
        if entry.publication_state is None:
            entry.publication_state = "candidate"
        if entry.metadata_json is None:
            entry.metadata_json = {}

    if newsletter.watchlist_reference is not None:
        reference = newsletter.watchlist_reference
        if reference.parser_run_id is None:
            reference.parser_run_id = parser_run.id
        if reference.reference_version is None:
            reference.reference_version = "v1"
        if reference.metadata_json is None:
            reference.metadata_json = {}

    session.flush()

    previous_newsletter = _get_previous_newsletter(session, newsletter.week_ended)
    previous_entries = previous_newsletter.watchlist_entries if previous_newsletter is not None else []
    if previous_newsletter is None:
        added_entries = []
        removed_entries = []
        changed_entries = []
        delta_summary = "No prior issue available for comparison."
    else:
        added_entries, removed_entries, changed_entries, delta_summary = _compute_issue_delta(
            list(newsletter.watchlist_entries),
            list(previous_entries),
        )

    issue_delta = session.execute(
        select(IssueDelta).where(IssueDelta.newsletter_id == newsletter.id)
    ).scalar_one_or_none()
    if issue_delta is None:
        issue_delta = IssueDelta(
            newsletter_id=newsletter.id,
            previous_newsletter_id=previous_newsletter.id if previous_newsletter is not None else None,
            delta_status="generated",
            added_entries_json=added_entries,
            removed_entries_json=removed_entries,
            changed_entries_json=changed_entries,
            summary_text=delta_summary,
        )
        session.add(issue_delta)
    else:
        issue_delta.previous_newsletter_id = previous_newsletter.id if previous_newsletter is not None else None
        issue_delta.delta_status = "generated"
        issue_delta.added_entries_json = added_entries
        issue_delta.removed_entries_json = removed_entries
        issue_delta.changed_entries_json = changed_entries
        issue_delta.summary_text = delta_summary

    issue_brief = session.execute(
        select(IssueBrief).where(IssueBrief.newsletter_id == newsletter.id)
    ).scalar_one_or_none()
    brief_data = _build_issue_brief_draft(
        title=newsletter.title,
        executive_summary=newsletter.overall_summary,
        entries=list(newsletter.watchlist_entries),
        delta=issue_delta,
        reference=newsletter.watchlist_reference,
    )
    if issue_brief is None:
        session.add(
            IssueBrief(
                newsletter_id=newsletter.id,
                parser_run_id=parser_run.id,
                brief_status="draft",
                headline=brief_data.headline,
                executive_summary=brief_data.executive_summary,
                key_themes_json=brief_data.key_themes,
                notable_risks_json=brief_data.notable_risks,
                notable_opportunities_json=brief_data.notable_opportunities,
                watchlist_summary_json=brief_data.watchlist_summary,
                change_summary_json=brief_data.change_summary,
            )
        )
    else:
        _apply_issue_brief_draft(
            issue_brief,
            parser_run_id=parser_run.id,
            brief_data=brief_data,
        )

    publication_run = session.execute(
        select(PublicationRun)
        .where(PublicationRun.newsletter_id == newsletter.id)
        .order_by(desc(PublicationRun.created_at))
    ).scalars().first()
    if publication_run is None:
        session.add(
            PublicationRun(
                newsletter_id=newsletter.id,
                publication_version="draft-1",
                status="draft",
                manifest_json={
                    "week_ended": newsletter.week_ended.isoformat(),
                    "entry_count": len(newsletter.watchlist_entries),
                    "backfilled": True,
                },
            )
        )

    return {
        "parser_run_id": parser_run.id,
        "delta_summary": None if previous_newsletter is None else delta_summary,
    }


def _get_previous_newsletter(session: Any, current_week_ended: date) -> Newsletter | None:
    stmt = (
        select(Newsletter)
        .where(Newsletter.week_ended < current_week_ended)
        .order_by(desc(Newsletter.week_ended))
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def _save_parsed_newsletter(parsed) -> dict[str, Any]:
    with database.session() as session:
        existing = session.execute(
            select(Newsletter).where(Newsletter.file_hash == parsed.file_hash)
        ).scalar_one_or_none()
        if existing is not None:
            return {
                "status": "skipped",
                "week_ended": existing.week_ended.isoformat(),
                "source_file": existing.source_file,
                "reason": "already_ingested",
            }

        newsletter = Newsletter(**_seed_record(parsed))
        session.add(newsletter)
        session.flush()

        parser_run = ParserRun(
            newsletter_id=newsletter.id,
            parser_version=PARSER_VERSION,
            status="completed",
            run_started_at=_utcnow(),
            run_completed_at=_utcnow(),
            page_count_detected=parsed.metadata.get("page_count"),
            pages_parsed=parsed.metadata.get("page_count"),
            watchlist_entry_count=len(parsed.watchlist_rows),
            section_count=len(parsed.section_summaries),
            warning_count=0,
            warnings_json=[],
            metrics_json={
                "has_watchlist_reference": parsed.watchlist_reference is not None,
                "source_filename": parsed.source_file.name,
            },
        )
        session.add(parser_run)
        session.flush()

        for section in parsed.section_summaries:
            session.add(
                NewsletterSection(
                    newsletter_id=newsletter.id,
                    name=section.name,
                    page_start=section.page_start,
                    page_end=section.page_end,
                    raw_text=section.raw_text,
                    summary_text=section.summary_text,
                    section_type=_classify_section_type(section.name),
                    extraction_confidence=0.95,
                    parser_run_id=parser_run.id,
                    metadata_json={},
                )
            )

        if parsed.watchlist_reference is not None:
            session.add(
                WatchlistReferenceRecord(
                    newsletter_id=newsletter.id,
                    page_number=parsed.watchlist_reference.page_number,
                    raw_text=parsed.watchlist_reference.raw_text,
                    summary_text=parsed.watchlist_reference.summary_text,
                    column_definitions_json=parsed.watchlist_reference.column_definitions,
                    trading_rules_json=parsed.watchlist_reference.trading_rules,
                    classification_rules_json=parsed.watchlist_reference.classification_rules,
                    parser_run_id=parser_run.id,
                    reference_version="v1",
                    metadata_json={},
                )
            )

        for row in parsed.watchlist_rows:
            session.add(
                WatchlistEntry(
                    newsletter_id=newsletter.id,
                    commodity_name=row.commodity_name,
                    spread_code=row.spread_code,
                    side=row.side,
                    legs=row.legs,
                    category=row.category,
                    enter_date=row.enter_date,
                    exit_date=row.exit_date,
                    win_pct=row.win_pct,
                    avg_profit=row.avg_profit,
                    avg_best_profit=row.avg_best_profit,
                    avg_worst_loss=row.avg_worst_loss,
                    avg_draw_down=row.avg_draw_down,
                    apw_pct=row.apw_pct,
                    ridx=row.ridx,
                    five_year_corr=row.five_year_corr,
                    portfolio=row.portfolio,
                    risk_level=row.risk_level,
                    trade_quality=row.trade_quality,
                    volatility_structure=row.volatility_structure,
                    section_name=row.section_name,
                    page_number=row.page_number,
                    raw_row=row.raw_row,
                    entry_key=_build_entry_key(parsed.week_ended, row),
                    tradeable=None,
                    blocked_reason=None,
                    parser_run_id=parser_run.id,
                    publication_state="candidate",
                    metadata_json={},
                )
            )

        session.flush()

        current_entries = session.execute(
            select(WatchlistEntry)
            .where(WatchlistEntry.newsletter_id == newsletter.id)
            .order_by(WatchlistEntry.id)
        ).scalars().all()
        previous_newsletter = _get_previous_newsletter(session, newsletter.week_ended)
        previous_entries: list[WatchlistEntry] = []
        if previous_newsletter is not None:
            previous_entries = session.execute(
                select(WatchlistEntry)
                .where(WatchlistEntry.newsletter_id == previous_newsletter.id)
                .order_by(WatchlistEntry.id)
            ).scalars().all()

        if previous_newsletter is None:
            added_entries = []
            removed_entries = []
            changed_entries = []
            delta_summary = "No prior issue available for comparison."
        else:
            added_entries, removed_entries, changed_entries, delta_summary = _compute_issue_delta(
                current_entries,
                previous_entries,
            )

        issue_delta = IssueDelta(
            newsletter_id=newsletter.id,
            previous_newsletter_id=previous_newsletter.id if previous_newsletter is not None else None,
            delta_status="generated",
            added_entries_json=added_entries,
            removed_entries_json=removed_entries,
            changed_entries_json=changed_entries,
            summary_text=delta_summary,
        )
        session.add(
            issue_delta
        )
        brief_data = _build_issue_brief_draft(
            title=newsletter.title,
            executive_summary=newsletter.overall_summary,
            entries=current_entries,
            delta=issue_delta,
            reference=newsletter.watchlist_reference,
        )
        session.add(
            IssueBrief(
                newsletter_id=newsletter.id,
                parser_run_id=parser_run.id,
                brief_status="draft",
                headline=brief_data.headline,
                executive_summary=brief_data.executive_summary,
                key_themes_json=brief_data.key_themes,
                notable_risks_json=brief_data.notable_risks,
                notable_opportunities_json=brief_data.notable_opportunities,
                watchlist_summary_json=brief_data.watchlist_summary,
                change_summary_json=brief_data.change_summary,
            )
        )
        session.add(
            PublicationRun(
                newsletter_id=newsletter.id,
                publication_version="draft-1",
                status="draft",
                manifest_json={
                    "week_ended": newsletter.week_ended.isoformat(),
                    "entry_count": len(current_entries),
                },
            )
        )

        return {
            "status": "ingested",
            "week_ended": parsed.week_ended.isoformat(),
            "source_file": str(parsed.source_file),
            "watchlist_rows": len(parsed.watchlist_rows),
            "sections": len(parsed.section_summaries),
            "has_watchlist_reference": parsed.watchlist_reference is not None,
            "issue_status": newsletter.issue_status,
            "parser_run_status": parser_run.status,
            "delta_summary": None if previous_newsletter is None else delta_summary,
        }


def _resolve_pdf_path(pdf_path: str | None) -> Path:
    if pdf_path:
        path = Path(pdf_path)
        return path if path.is_absolute() else settings.data_dir / path
    pdf_files = sorted(settings.data_dir.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"No PDFs found in {settings.data_dir}")
    return pdf_files[-1]


def _parse_issue_date(value: str) -> date:
    return date.fromisoformat(value)


def _refresh_issue_records(session: Any, week_ended: str) -> tuple[Newsletter, dict[str, Any]]:
    newsletter = session.execute(
        select(Newsletter).where(Newsletter.week_ended == _parse_issue_date(week_ended))
    ).scalar_one_or_none()
    if newsletter is None:
        raise ValueError(f"No newsletter found for {week_ended}")
    seeded = _seed_phase1_records(session, newsletter)
    return newsletter, seeded


@mcp.tool()
def ingest_newsletter(pdf_path: str | None = None) -> dict[str, Any]:
    """Parse a newsletter PDF and store issue metadata, summaries, and watchlist rows."""
    path = _resolve_pdf_path(pdf_path)
    parsed = parse_newsletter(path)
    return _save_parsed_newsletter(parsed)


@mcp.tool()
def ingest_pending_newsletters() -> dict[str, Any]:
    """Scan the data folder and ingest all PDFs not already present in the database."""
    results: list[dict[str, Any]] = []
    for pdf_path in sorted(settings.data_dir.glob("*.pdf")):
        parsed = parse_newsletter(pdf_path)
        results.append(_save_parsed_newsletter(parsed))

    ingested = [result for result in results if result["status"] == "ingested"]
    skipped = [result for result in results if result["status"] == "skipped"]
    return {
        "data_dir": str(settings.data_dir),
        "ingested_count": len(ingested),
        "skipped_count": len(skipped),
        "results": results,
    }


@mcp.tool()
def backfill_phase1_intelligence() -> dict[str, Any]:
    """Backfill Phase 1 parser, brief, delta, and publication records for existing issues."""
    with database.session() as session:
        newsletters = session.execute(
            select(Newsletter).order_by(Newsletter.week_ended)
        ).scalars().all()
        results: list[dict[str, Any]] = []
        for newsletter in newsletters:
            seeded = _seed_phase1_records(session, newsletter)
            results.append(
                {
                    "week_ended": newsletter.week_ended.isoformat(),
                    "parser_run_id": seeded["parser_run_id"],
                    "delta_summary": seeded["delta_summary"],
                }
            )

        return {
            "issue_count": len(newsletters),
            "results": results,
        }


@mcp.tool()
def refresh_and_publish_issue(
    week_ended: str,
    output_dir: str | None = None,
    publication_version: str | None = None,
    published_by: str | None = None,
) -> dict[str, Any]:
    """Refresh stored Phase 1 intelligence for an issue, then publish the latest artifacts."""
    with database.session() as session:
        newsletter, seeded = _refresh_issue_records(session, week_ended)
        refreshed_summary = {
            "week_ended": newsletter.week_ended.isoformat(),
            "parser_run_id": seeded["parser_run_id"],
            "delta_summary": seeded["delta_summary"],
            "issue_status": newsletter.issue_status,
        }

    published = publish_issue(
        week_ended=week_ended,
        output_dir=output_dir,
        publication_version=publication_version,
        published_by=published_by,
    )
    return {
        "refreshed": refreshed_summary,
        "published": published,
    }


@mcp.tool()
def list_issues(limit: int = 10) -> list[dict[str, Any]]:
    """List newsletter issues already imported into the database."""
    with database.session() as session:
        stmt = select(Newsletter).order_by(desc(Newsletter.week_ended)).limit(limit)
        records = session.execute(stmt).scalars().all()
        return [
            {
                "week_ended": record.week_ended.isoformat(),
                "title": record.title,
                "source_file": record.source_file,
                "summary": record.overall_summary,
            }
            for record in records
        ]


@mcp.tool()
def import_schwab_futures_catalog(csv_path: str | None = None) -> dict[str, Any]:
    """Import the Schwab futures symbol catalog from a CSV export into the database."""
    source_path = Path(csv_path) if csv_path else DEFAULT_SCHWAB_CATALOG_CSV
    if not source_path.exists():
        raise ValueError(f"Schwab futures catalog CSV not found at {source_path}")

    parsed_rows = _extract_schwab_catalog_rows(source_path)
    if not parsed_rows:
        raise ValueError(f"No Schwab futures catalog rows were parsed from {source_path}")

    source_modified_at = datetime.fromtimestamp(source_path.stat().st_mtime, tz=UTC)
    imported = 0
    updated = 0
    seen_roots = {row["symbol_root"] for row in parsed_rows}

    with database.session() as session:
        existing_rows = {
            record.symbol_root: record
            for record in session.execute(select(SchwabFuturesCatalog)).scalars().all()
        }

        for row in parsed_rows:
            existing = existing_rows.get(row["symbol_root"])
            if existing is None:
                session.add(
                    SchwabFuturesCatalog(
                        symbol_root=row["symbol_root"],
                        display_name=row["display_name"],
                        category=row["category"],
                        options_tradable=row["options_tradable"],
                        multiplier=row["multiplier"],
                        minimum_tick_size=row["minimum_tick_size"],
                        settlement_type=row["settlement_type"],
                        trading_hours=row["trading_hours"],
                        is_micro=row["is_micro"],
                        stream_supported=row["stream_supported"],
                        source_file=str(source_path),
                        source_modified_at=source_modified_at,
                        is_active=True,
                        metadata_json={},
                    )
                )
                imported += 1
                continue

            existing.display_name = row["display_name"]
            existing.category = row["category"]
            existing.options_tradable = row["options_tradable"]
            existing.multiplier = row["multiplier"]
            existing.minimum_tick_size = row["minimum_tick_size"]
            existing.settlement_type = row["settlement_type"]
            existing.trading_hours = row["trading_hours"]
            existing.is_micro = row["is_micro"]
            existing.source_file = str(source_path)
            existing.source_modified_at = source_modified_at
            existing.is_active = True
            updated += 1

        for symbol_root, record in existing_rows.items():
            if record.source_file == str(source_path) and symbol_root not in seen_roots:
                record.is_active = False

        category_counts = Counter(row["category"] for row in parsed_rows)

    return {
        "csv_path": str(source_path),
        "source_modified_at": source_modified_at.isoformat(),
        "row_count": len(parsed_rows),
        "imported_count": imported,
        "updated_count": updated,
        "category_counts": dict(category_counts),
        "sample_symbols": sorted(seen_roots)[:10],
    }


@mcp.tool()
def list_schwab_futures_catalog(limit: int = 25, category: str | None = None) -> dict[str, Any]:
    """List rows from the imported Schwab futures symbol catalog."""
    with database.session() as session:
        stmt = select(SchwabFuturesCatalog).where(SchwabFuturesCatalog.is_active.is_(True))
        if category:
            stmt = stmt.where(SchwabFuturesCatalog.category == category)
        stmt = stmt.order_by(SchwabFuturesCatalog.category, SchwabFuturesCatalog.symbol_root).limit(limit)
        rows = session.execute(stmt).scalars().all()

        categories = Counter(
            session.execute(
                select(SchwabFuturesCatalog.category).where(SchwabFuturesCatalog.is_active.is_(True))
            ).scalars().all()
        )

        return {
            "count": len(rows),
            "categories": dict(categories),
            "rows": [_serialize_schwab_catalog_row(row) for row in rows],
        }


def _serialize_newsletter_commodity_mapping(record: NewsletterCommodityCatalog) -> dict[str, Any]:
    return {
        "newsletter_root": record.newsletter_root,
        "commodity_name": record.commodity_name,
        "category": record.category,
        "exchange": record.exchange,
        "preferred_schwab_root": record.preferred_schwab_root,
        "alternate_schwab_roots": record.alternate_schwab_roots_json,
        "is_tradeable_by_policy": record.is_tradeable_by_policy,
        "policy_block_reason": record.policy_block_reason,
        "mapping_confidence": record.mapping_confidence,
        "mapping_notes": record.mapping_notes,
        "source_issue_week": record.source_issue_week.isoformat() if record.source_issue_week else None,
        "source_page_number": record.source_page_number,
    }


@mcp.tool()
def upsert_newsletter_commodity_mapping(
    newsletter_root: str,
    commodity_name: str,
    preferred_schwab_root: str | None = None,
    category: str | None = None,
    exchange: str | None = None,
    alternate_schwab_roots: list[str] | None = None,
    is_tradeable_by_policy: bool | None = None,
    policy_block_reason: str | None = None,
    mapping_confidence: float | None = None,
    mapping_notes: str | None = None,
) -> dict[str, Any]:
    """Create or update a newsletter commodity to Schwab root mapping."""
    root = newsletter_root.strip().upper()
    preferred_root = preferred_schwab_root.strip().upper() if preferred_schwab_root else None
    if preferred_root and not preferred_root.startswith("/"):
        preferred_root = f"/{preferred_root.lstrip('/')}"

    alternate_roots = [value.strip().upper() for value in (alternate_schwab_roots or []) if value.strip()]
    alternate_roots = [value if value.startswith("/") else f"/{value.lstrip('/')}" for value in alternate_roots]

    with database.session() as session:
        existing = session.execute(
            select(NewsletterCommodityCatalog).where(NewsletterCommodityCatalog.newsletter_root == root)
        ).scalar_one_or_none()

        if existing is None:
            record = NewsletterCommodityCatalog(
                newsletter_root=root,
                commodity_name=commodity_name,
                category=category,
                exchange=exchange,
                preferred_schwab_root=preferred_root,
                alternate_schwab_roots_json=alternate_roots,
                is_tradeable_by_policy=is_tradeable_by_policy,
                policy_block_reason=policy_block_reason,
                mapping_confidence=mapping_confidence,
                mapping_notes=mapping_notes,
                metadata_json={},
            )
            session.add(record)
            session.flush()
            action = "created"
        else:
            existing.commodity_name = commodity_name
            existing.category = category
            existing.exchange = exchange
            existing.preferred_schwab_root = preferred_root
            existing.alternate_schwab_roots_json = alternate_roots
            existing.is_tradeable_by_policy = is_tradeable_by_policy
            existing.policy_block_reason = policy_block_reason
            existing.mapping_confidence = mapping_confidence
            existing.mapping_notes = mapping_notes
            record = existing
            action = "updated"

        return {
            "action": action,
            "mapping": _serialize_newsletter_commodity_mapping(record),
        }


@mcp.tool()
def list_newsletter_commodity_catalog(limit: int = 50) -> dict[str, Any]:
    """List newsletter commodity mappings currently stored in the database."""
    with database.session() as session:
        rows = session.execute(
            select(NewsletterCommodityCatalog)
            .order_by(NewsletterCommodityCatalog.newsletter_root)
            .limit(limit)
        ).scalars().all()
        return {
            "count": len(rows),
            "rows": [_serialize_newsletter_commodity_mapping(row) for row in rows],
        }


@mcp.tool()
def get_issue_summary(week_ended: str) -> dict[str, Any]:
    """Return the issue summary and section summaries for a specific week ended date."""
    with database.session() as session:
        stmt = select(Newsletter).where(Newsletter.week_ended == _parse_issue_date(week_ended))
        newsletter = session.execute(stmt).scalar_one_or_none()
        if newsletter is None:
            raise ValueError(f"No newsletter found for {week_ended}")

        sections_stmt = (
            select(NewsletterSection)
            .where(NewsletterSection.newsletter_id == newsletter.id)
            .order_by(NewsletterSection.page_start)
        )
        sections = session.execute(sections_stmt).scalars().all()
        brief = session.execute(
            select(IssueBrief).where(IssueBrief.newsletter_id == newsletter.id)
        ).scalar_one_or_none()
        delta = session.execute(
            select(IssueDelta).where(IssueDelta.newsletter_id == newsletter.id)
        ).scalar_one_or_none()
        reference = session.execute(
            select(WatchlistReferenceRecord).where(
                WatchlistReferenceRecord.newsletter_id == newsletter.id
            )
        ).scalar_one_or_none()
        entries = session.execute(
            select(WatchlistEntry)
            .where(WatchlistEntry.newsletter_id == newsletter.id)
            .order_by(WatchlistEntry.page_number, WatchlistEntry.id)
        ).scalars().all()
        brief_data = _issue_brief_fallback(newsletter, entries, delta, reference, brief)

        return {
            "week_ended": newsletter.week_ended.isoformat(),
            "title": newsletter.title,
            "summary": newsletter.overall_summary,
            "issue_brief": {
                "headline": brief_data.headline,
                "executive_summary": brief_data.executive_summary,
                "key_themes": brief_data.key_themes,
                "notable_risks": brief_data.notable_risks,
                "notable_opportunities": brief_data.notable_opportunities,
                "watchlist_summary": brief_data.watchlist_summary,
                "change_summary": brief_data.change_summary,
            },
            "issue_delta": {
                "summary_text": delta.summary_text if delta is not None else None,
                "added_entries": delta.added_entries_json if delta is not None else [],
                "removed_entries": delta.removed_entries_json if delta is not None else [],
                "changed_entries": delta.changed_entries_json if delta is not None else [],
            },
            "watchlist_reference": _serialize_watchlist_reference(reference),
            "sections": [
                {
                    "name": section.name,
                    "page_start": section.page_start,
                    "page_end": section.page_end,
                    "summary": section.summary_text,
                }
                for section in sections
            ],
        }


def _serialize_watchlist_reference(reference: WatchlistReferenceRecord | None) -> dict[str, Any] | None:
    if reference is None:
        return None

    return {
        "page_number": reference.page_number,
        "summary": reference.summary_text,
        "column_definitions": reference.column_definitions_json,
        "trading_rules": reference.trading_rules_json,
        "classification_rules": reference.classification_rules_json,
    }


def _serialize_watchlist_entry(entry: WatchlistEntry) -> dict[str, Any]:
    return {
        "commodity_name": entry.commodity_name,
        "spread_code": entry.spread_code,
        "side": entry.side,
        "legs": entry.legs,
        "category": entry.category,
        "enter_date": entry.enter_date.isoformat(),
        "exit_date": entry.exit_date.isoformat(),
        "win_pct": entry.win_pct,
        "avg_profit": entry.avg_profit,
        "avg_best_profit": entry.avg_best_profit,
        "avg_worst_loss": entry.avg_worst_loss,
        "avg_draw_down": entry.avg_draw_down,
        "apw_pct": entry.apw_pct,
        "ridx": entry.ridx,
        "five_year_corr": entry.five_year_corr,
        "portfolio": entry.portfolio,
        "risk_level": entry.risk_level,
        "trade_quality": entry.trade_quality,
        "volatility_structure": entry.volatility_structure,
        "section_name": entry.section_name,
        "page_number": entry.page_number,
    }


WATCHLIST_CSV_FIELDNAMES = [
    "commodity_name",
    "spread_code",
    "side",
    "legs",
    "category",
    "enter_date",
    "exit_date",
    "win_pct",
    "avg_profit",
    "avg_best_profit",
    "avg_worst_loss",
    "avg_draw_down",
    "apw_pct",
    "ridx",
    "five_year_corr",
    "portfolio",
    "risk_level",
    "trade_quality",
    "volatility_structure",
    "section_name",
    "page_number",
]


def _build_watchlist_csv(entries: list[dict[str, Any]]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=WATCHLIST_CSV_FIELDNAMES, lineterminator="\n")
    writer.writeheader()
    writer.writerows(entries)
    return output.getvalue()


def _write_text_file(path_str: str, content: str) -> str:
    path = Path(path_str)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")
    return str(path)


def _get_issue_bundle(session: Any, week_ended: str) -> tuple[Newsletter, list[WatchlistEntry], WatchlistReferenceRecord | None, IssueBrief | None, IssueDelta | None]:
    newsletter = session.execute(
        select(Newsletter).where(Newsletter.week_ended == _parse_issue_date(week_ended))
    ).scalar_one_or_none()
    if newsletter is None:
        raise ValueError(f"No newsletter found for {week_ended}")

    entries = session.execute(
        select(WatchlistEntry)
        .where(WatchlistEntry.newsletter_id == newsletter.id)
        .order_by(WatchlistEntry.page_number, WatchlistEntry.id)
    ).scalars().all()
    reference = session.execute(
        select(WatchlistReferenceRecord).where(WatchlistReferenceRecord.newsletter_id == newsletter.id)
    ).scalar_one_or_none()
    brief = session.execute(
        select(IssueBrief).where(IssueBrief.newsletter_id == newsletter.id)
    ).scalar_one_or_none()
    delta = session.execute(
        select(IssueDelta).where(IssueDelta.newsletter_id == newsletter.id)
    ).scalar_one_or_none()
    return newsletter, entries, reference, brief, delta


@mcp.tool()
def get_watchlist(
    week_ended: str,
    min_trade_quality: str | None = None,
    include_reference: bool = True,
) -> dict[str, Any]:
    """Return watchlist rows for a given issue date, optionally filtered by trade quality tier."""
    with database.session() as session:
        newsletter = session.execute(
            select(Newsletter).where(Newsletter.week_ended == _parse_issue_date(week_ended))
        ).scalar_one_or_none()
        if newsletter is None:
            raise ValueError(f"No newsletter found for {week_ended}")

        stmt = (
            select(WatchlistEntry)
            .where(WatchlistEntry.newsletter_id == newsletter.id)
            .order_by(WatchlistEntry.page_number, WatchlistEntry.id)
        )
        entries = session.execute(stmt).scalars().all()

        if min_trade_quality:
            threshold = int(min_trade_quality.split()[-1])
            entries = [
                entry
                for entry in entries
                if entry.trade_quality and int(entry.trade_quality.split()[-1]) <= threshold
            ]

        counts = Counter((entry.trade_quality or entry.portfolio or "unclassified") for entry in entries)
        response = {
            "week_ended": newsletter.week_ended.isoformat(),
            "entry_count": len(entries),
            "watchlist_bucket_counts": dict(counts),
            "entries": [_serialize_watchlist_entry(entry) for entry in entries],
        }

        if include_reference:
            reference = session.execute(
                select(WatchlistReferenceRecord).where(
                    WatchlistReferenceRecord.newsletter_id == newsletter.id
                )
            ).scalar_one_or_none()
            response["watchlist_reference"] = _serialize_watchlist_reference(reference)

        return response


@mcp.tool()
def export_watchlist_csv(
    week_ended: str,
    section_name: str | None = None,
    min_trade_quality: str | None = None,
    include_reference: bool = True,
    output_path: str | None = None,
    reference_output_path: str | None = None,
) -> dict[str, Any]:
    """Export watchlist rows as CSV, optionally filtered by section and trade quality."""
    result = get_watchlist(
        week_ended=week_ended,
        min_trade_quality=min_trade_quality,
        include_reference=include_reference,
    )
    entries = result["entries"]

    if section_name is not None:
        entries = [entry for entry in entries if entry["section_name"] == section_name]

    csv_content = _build_watchlist_csv(entries)
    written_files: dict[str, str] = {}

    if output_path is not None:
        written_files["csv"] = _write_text_file(output_path, csv_content)

    if include_reference and reference_output_path is not None:
        reference_json = json.dumps(result.get("watchlist_reference"), indent=2)
        written_files["reference"] = _write_text_file(reference_output_path, reference_json)

    response = {
        "week_ended": result["week_ended"],
        "section_name": section_name,
        "entry_count": len(entries),
        "csv": csv_content,
        "watchlist_reference": result.get("watchlist_reference"),
    }
    if written_files:
        response["written_files"] = written_files

    return response


@mcp.tool()
def export_watchlist_package(
    week_ended: str,
    section_name: str | None = None,
    min_trade_quality: str | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Export one issue as paired rows.csv and reference.json outputs."""
    result = export_watchlist_csv(
        week_ended=week_ended,
        section_name=section_name,
        min_trade_quality=min_trade_quality,
        include_reference=True,
    )
    reference = result.get("watchlist_reference")
    package = {
        "week_ended": result["week_ended"],
        "section_name": section_name,
        "entry_count": result["entry_count"],
        "rows_csv": result["csv"],
        "reference_json": json.dumps(reference, indent=2),
        "watchlist_reference": reference,
    }

    if output_dir is not None:
        base_dir = Path(output_dir)
        if not base_dir.is_absolute():
            base_dir = Path.cwd() / base_dir
        base_dir.mkdir(parents=True, exist_ok=True)
        rows_path = _write_text_file(str(base_dir / "rows.csv"), package["rows_csv"])
        reference_path = _write_text_file(str(base_dir / "reference.json"), package["reference_json"])
        package["written_files"] = {
            "rows_csv": rows_path,
            "reference_json": reference_path,
        }

    return package


@mcp.tool()
def export_all_watchlists_csv(
    date_from: str,
    date_to: str,
    section_name: str | None = None,
    min_trade_quality: str | None = None,
    include_reference: bool = True,
    output_path: str | None = None,
    reference_output_path: str | None = None,
) -> dict[str, Any]:
    """Export watchlists across a date range as one CSV, with optional reference bundle."""
    start_date = _parse_issue_date(date_from)
    end_date = _parse_issue_date(date_to)

    with database.session() as session:
        newsletters = session.execute(
            select(Newsletter)
            .where(Newsletter.week_ended >= start_date, Newsletter.week_ended <= end_date)
            .order_by(Newsletter.week_ended)
        ).scalars().all()

        rows: list[dict[str, Any]] = []
        references: list[dict[str, Any]] = []

        for newsletter in newsletters:
            result = get_watchlist(
                week_ended=newsletter.week_ended.isoformat(),
                min_trade_quality=min_trade_quality,
                include_reference=include_reference,
            )
            issue_entries = result["entries"]
            if section_name is not None:
                issue_entries = [
                    entry for entry in issue_entries if entry["section_name"] == section_name
                ]

            for entry in issue_entries:
                rows.append(
                    {
                        "week_ended": newsletter.week_ended.isoformat(),
                        **entry,
                    }
                )

            if include_reference and result.get("watchlist_reference") is not None:
                references.append(
                    {
                        "week_ended": newsletter.week_ended.isoformat(),
                        **result["watchlist_reference"],
                    }
                )

    combined_fieldnames = ["week_ended", *WATCHLIST_CSV_FIELDNAMES]
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=combined_fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    csv_content = output.getvalue()

    written_files: dict[str, str] = {}
    if output_path is not None:
        written_files["csv"] = _write_text_file(output_path, csv_content)
    if include_reference and reference_output_path is not None:
        written_files["references"] = _write_text_file(
            reference_output_path,
            json.dumps(references, indent=2),
        )

    response = {
        "date_from": start_date.isoformat(),
        "date_to": end_date.isoformat(),
        "issue_count": len(newsletters),
        "entry_count": len(rows),
        "section_name": section_name,
        "csv": csv_content,
    }
    if include_reference:
        response["watchlist_references"] = references
    if written_files:
        response["written_files"] = written_files

    return response


@mcp.tool()
def export_watchlist_bundle(
    date_from: str,
    date_to: str,
    output_dir: str,
    include_issue_packages: bool = True,
    include_consolidated: bool = True,
    include_reference_bundle: bool = True,
) -> dict[str, Any]:
    """Export a folder bundle with per-issue watchlists and consolidated CSVs."""
    start_date = _parse_issue_date(date_from)
    end_date = _parse_issue_date(date_to)
    base_dir = Path(output_dir)
    if not base_dir.is_absolute():
        base_dir = Path.cwd() / base_dir
    base_dir.mkdir(parents=True, exist_ok=True)

    with database.session() as session:
        newsletters = session.execute(
            select(Newsletter)
            .where(Newsletter.week_ended >= start_date, Newsletter.week_ended <= end_date)
            .order_by(Newsletter.week_ended)
        ).scalars().all()

    issue_packages: list[dict[str, Any]] = []
    consolidated_outputs: dict[str, Any] = {}

    if include_issue_packages:
        issues_dir = base_dir / "issues"
        issues_dir.mkdir(parents=True, exist_ok=True)
        for newsletter in newsletters:
            issue_date = newsletter.week_ended.isoformat()
            issue_dir = issues_dir / issue_date
            issue_dir.mkdir(parents=True, exist_ok=True)

            intra = export_watchlist_package(
                week_ended=issue_date,
                section_name="intra_commodity",
                output_dir=str(issue_dir / "intra_commodity"),
            )
            inter = export_watchlist_package(
                week_ended=issue_date,
                section_name="inter_commodity",
                output_dir=str(issue_dir / "inter_commodity"),
            )

            issue_packages.append(
                {
                    "week_ended": issue_date,
                    "issue_dir": str(issue_dir),
                    "intra_entry_count": intra["entry_count"],
                    "inter_entry_count": inter["entry_count"],
                    "written_files": {
                        "intra": intra.get("written_files"),
                        "inter": inter.get("written_files"),
                    },
                }
            )

    if include_consolidated:
        consolidated_dir = base_dir / "consolidated"
        consolidated_dir.mkdir(parents=True, exist_ok=True)

        intra = export_all_watchlists_csv(
            date_from=start_date.isoformat(),
            date_to=end_date.isoformat(),
            section_name="intra_commodity",
            include_reference=include_reference_bundle,
            output_path=str(consolidated_dir / "intra_commodity.csv"),
            reference_output_path=(
                str(consolidated_dir / "intra_commodity_references.json")
                if include_reference_bundle
                else None
            ),
        )
        inter = export_all_watchlists_csv(
            date_from=start_date.isoformat(),
            date_to=end_date.isoformat(),
            section_name="inter_commodity",
            include_reference=include_reference_bundle,
            output_path=str(consolidated_dir / "inter_commodity.csv"),
            reference_output_path=(
                str(consolidated_dir / "inter_commodity_references.json")
                if include_reference_bundle
                else None
            ),
        )

        consolidated_outputs = {
            "dir": str(consolidated_dir),
            "intra_entry_count": intra["entry_count"],
            "inter_entry_count": inter["entry_count"],
            "written_files": {
                "intra": intra.get("written_files"),
                "inter": inter.get("written_files"),
            },
        }

    return {
        "date_from": start_date.isoformat(),
        "date_to": end_date.isoformat(),
        "issue_count": len(newsletters),
        "output_dir": str(base_dir),
        "issue_packages": issue_packages,
        "consolidated": consolidated_outputs,
    }


@mcp.tool()
def publish_issue(
    week_ended: str,
    output_dir: str | None = None,
    publication_version: str | None = None,
    published_by: str | None = None,
) -> dict[str, Any]:
    """Publish one issue into file-based Phase 1 artifacts under the published folder."""
    base_dir = Path(output_dir) if output_dir is not None else Path.cwd() / "published"
    if not base_dir.is_absolute():
        base_dir = Path.cwd() / base_dir
    base_dir.mkdir(parents=True, exist_ok=True)

    with database.session() as session:
        newsletter, entries, reference, brief, delta = _get_issue_bundle(session, week_ended)
        if not entries:
            raise ValueError(f"No watchlist entries found for {week_ended}")

        existing_publication_count = session.execute(
            select(PublicationRun).where(PublicationRun.newsletter_id == newsletter.id)
        ).scalars().all()
        resolved_version = publication_version or f"published-{len(existing_publication_count) + 1}"

        publication_run = PublicationRun(
            newsletter_id=newsletter.id,
            publication_version=resolved_version,
            status="published",
            published_by=published_by,
            published_at=_utcnow(),
            output_root=str(base_dir),
            manifest_json={},
            notes=None,
        )
        session.add(publication_run)
        session.flush()

        watchlist_payload = {
            "schema_version": PUBLICATION_SCHEMA_VERSION,
            "publication_version": resolved_version,
            "published_at": publication_run.published_at.isoformat() if publication_run.published_at else _utcnow().isoformat(),
            "week_ended": newsletter.week_ended.isoformat(),
            "newsletter_id": newsletter.id,
            "title": newsletter.title,
            "source_file": newsletter.source_file,
            "watchlist": [
                _build_watchlist_publication_entry(newsletter, entry)
                for entry in entries
            ],
        }
        weekly_intelligence = _build_weekly_intelligence_payload(newsletter, entries, brief, delta, reference)
        issue_brief_markdown = _build_issue_brief_markdown(newsletter, brief, delta, reference, entries)

        watchlist_yaml_path = _write_text_file(str(base_dir / "watchlist.yaml"), _serialize_publication_yaml(watchlist_payload))
        intelligence_path = _write_text_file(
            str(base_dir / "weekly_intelligence.json"),
            json.dumps(weekly_intelligence, indent=2),
        )
        issue_brief_path = _write_text_file(str(base_dir / "issue_brief.md"), issue_brief_markdown)

        manifest_files = {
            "watchlist_yaml": watchlist_yaml_path,
            "weekly_intelligence_json": intelligence_path,
            "issue_brief_md": issue_brief_path,
        }
        manifest = _build_publication_manifest(
            newsletter=newsletter,
            publication_version=resolved_version,
            publication_run_id=publication_run.id,
            output_root=base_dir,
            files=manifest_files,
            watchlist_payload=watchlist_payload,
        )
        manifest_path = str(base_dir / "publication_manifest.json")
        manifest_files["publication_manifest_json"] = manifest_path
        manifest["files"]["publication_manifest_json"] = manifest_path
        _write_text_file(
            manifest_path,
            json.dumps(manifest, indent=2),
        )
        publication_run.manifest_json = manifest

        artifact_specs = [
            ("watchlist_yaml", watchlist_yaml_path, _serialize_publication_yaml(watchlist_payload), len(watchlist_payload["watchlist"])),
            ("weekly_intelligence_json", intelligence_path, json.dumps(weekly_intelligence, indent=2), len(entries)),
            ("issue_brief_md", issue_brief_path, issue_brief_markdown, None),
            ("publication_manifest_json", manifest_path, json.dumps(manifest, indent=2), None),
        ]
        for artifact_type, file_path, content, row_count in artifact_specs:
            session.add(
                PublicationArtifact(
                    publication_run_id=publication_run.id,
                    artifact_type=artifact_type,
                    file_path=file_path,
                    file_hash=_sha256_text(content),
                    row_count=row_count,
                    metadata_json={},
                )
            )

        for entry in entries:
            entry.tradeable, entry.blocked_reason = _derive_entry_tradeability(entry, _parse_spread_legs(entry.spread_code))
            entry.publication_state = "published"

        newsletter.issue_status = "published"
        newsletter.published_at = publication_run.published_at

        return {
            "week_ended": newsletter.week_ended.isoformat(),
            "publication_version": resolved_version,
            "publication_run_id": publication_run.id,
            "output_dir": str(base_dir),
            "files": manifest_files,
            "watchlist_count": len(watchlist_payload["watchlist"]),
        }


@mcp.tool()
def get_watchlist_reference(week_ended: str) -> dict[str, Any]:
    """Return the watchlist overview/reference rules for a specific newsletter issue."""
    with database.session() as session:
        newsletter = session.execute(
            select(Newsletter).where(Newsletter.week_ended == _parse_issue_date(week_ended))
        ).scalar_one_or_none()
        if newsletter is None:
            raise ValueError(f"No newsletter found for {week_ended}")

        reference = session.execute(
            select(WatchlistReferenceRecord).where(
                WatchlistReferenceRecord.newsletter_id == newsletter.id
            )
        ).scalar_one_or_none()
        if reference is None:
            return {
                "week_ended": newsletter.week_ended.isoformat(),
                "has_watchlist_reference": False,
            }

        return {
            "week_ended": newsletter.week_ended.isoformat(),
            "has_watchlist_reference": True,
            "page_number": reference.page_number,
            "summary": reference.summary_text,
            "column_definitions": reference.column_definitions_json,
            "trading_rules": reference.trading_rules_json,
            "classification_rules": reference.classification_rules_json,
        }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
